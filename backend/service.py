from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime,timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo
import json
import logging
import threading
from uuid import uuid4
import numpy as np
from backend.config import settings
from backend.database import query,execute,as_json,save_task,save_image,json_default
from backend.data_source import list_batches,load_inputs,historical_residuals
from backend.matching import validate_window,rank_windows,finalize_candidates
from backend.model_review import review_images
from backend.weather import WeatherStore,RENDER_VERSION

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=1,thread_name_prefix='similarity')
job_lock = threading.Lock()
weather_store = None
WARNING = '固定2025数据联调：气象为合成日均场，污染物为时刻值派生项目统计量；不是规范AQI评价、09:00预报匹配或无未来数据历史回放。'


def get_weather():
    global weather_store
    file_stat = settings.weather_file.stat()
    if weather_store is None or weather_store.file_signature != (file_stat.st_size,file_stat.st_mtime_ns):
        if weather_store is not None:
            weather_store.dataset.close()
        weather_store = WeatherStore()
    return weather_store


def create_task(batch,start,end,should_review=True):
    batches = list_batches()
    chosen = next((item for item in batches if item['forecast_start_time'] == batch),None)
    if chosen is None:
        raise ValueError('预测批次不存在')
    dates = validate_window(start,end,chosen['dates'])
    if not job_lock.acquire(blocking=False):
        raise ValueError('已有匹配任务执行中，请等待完成')
    task_id = str(uuid4())
    try:
        evidence = {'task_id':task_id,'warning':WARNING,'stage':'等待执行','progress':0,'dates':dates,
                    'forecast_start_time':batch,'should_review':should_review,'candidates':[],
                    'model_name':settings.model_name,'rule_version':'LABEL_RETRIEVAL_V2.1_FIXED2025',
                    'created_at':datetime.now(ZoneInfo('Asia/Shanghai')),'review_failures':[],
                    'final_weights':{'pollutant':.6,'meteorology':.2,'image':.2}}
        from backend.database import connection
        with connection() as database,database.cursor() as cursor:
            cursor.execute('INSERT INTO similarity_match_task VALUES(%s,%s,%s,%s,%s)',(task_id,start,end,batch,'RUNNING'))
            cursor.execute('INSERT INTO match_task_evidence(task_id,stage,evidence) VALUES(%s,%s,%s)',(task_id,'等待执行',as_json(evidence)))
        executor.submit(run_task,task_id,batch,dates,should_review,evidence)
    except Exception:
        job_lock.release()
        raise
    return task_id


def persist_candidates(task_id,candidates):
    from backend.database import connection
    with connection() as database,database.cursor() as cursor:
        for candidate in candidates:
            cursor.execute('''INSERT INTO similarity_match_candidate
                (task_id,history_start_date,coarse_score,pollutant_score,meteorology_score,image_score,final_score,final_rank,history_forecast_start_time)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(task_id,history_start_date) DO UPDATE SET
                image_score=EXCLUDED.image_score,final_score=EXCLUDED.final_score,final_rank=EXCLUDED.final_rank,
                history_forecast_start_time=EXCLUDED.history_forecast_start_time''',
                (task_id,candidate['history_start_date'],candidate['coarse_score'],candidate['fine_pollutant_score'],
                 candidate['meteorology_score'],candidate.get('image_score'),candidate.get('final_score'),candidate.get('final_rank'),candidate.get('history_forecast_start_time')))


def render_images(store,dates):
    metadata = {'dates':[str(day) for day in dates],'render_version':RENDER_VERSION,'source_hash':store.source_hash}
    saved = query('SELECT image_hash,metadata FROM match_image WHERE metadata @> %s',(as_json(metadata),))
    images = {row['metadata']['product']:row['image_hash'] for row in saved}
    if len(images) == 4:
        return images
    return {product:save_image(png,{**metadata,'product':product}) for product,png in store.render(dates).items()}


def run_task(task_id,batch,dates,should_review,evidence):
    def update(stage,progress,status='RUNNING'):
        evidence.update(stage=stage,progress=progress)
        save_task(task_id,status,stage,evidence)
    try:
        update('核验数据与四图基础场',5)
        current,observations,weather,labels = load_inputs(batch)
        store = get_weather()
        for day in dates:
            if day not in current or day not in weather or day not in store.valid_dates:
                raise ValueError(f'{day} 缺少污染物、气象或四图基础场')
        current_values = np.stack([current[day] for day in dates])
        current_weather = np.stack([weather[day] for day in dates])
        current_labels = [labels[day] for day in dates]
        update('联合检索与九宫格数值精排',15)
        candidates,baseline = rank_windows(current_values,current_weather,current_labels,observations,weather,labels,
                                           dates[0],store.valid_dates,datetime.now(ZoneInfo('Asia/Shanghai')).date())
        if not candidates:
            raise ValueError('没有满足日期、完整性、基准和图像基础场要求的历史候选')
        evidence.update(candidates=candidates,baseline=baseline,current_values=current_values.tolist(),
                        current_weather=current_weather.tolist(),current_weather_labels=current_labels,
                        current_features=candidates[0]['current_features'],current_labels=candidates[0]['current_labels'],
                        source_hash=store.source_hash,
                        input_hash=sha256(json.dumps({'current':current_values.tolist(),'observations':{str(k):v.tolist() for k,v in observations.items()},
                                                     'weather':{str(k):v.tolist() for k,v in weather.items()}},sort_keys=True).encode()).hexdigest())
        for candidate in candidates:
            candidate.pop('current_features')
            candidate.pop('current_labels')
        persist_candidates(task_id,candidates)
        update(f'已检索{len(candidates)}个独立窗口；生成当前四图',35)
        evidence['current_images'] = render_images(store,dates)
        target_count = min(10,len(candidates))
        if not should_review:
            for index,candidate in enumerate(candidates[:target_count]):
                history_dates = [candidate['history_start_date']+timedelta(days=i) for i in range(len(dates))]
                candidate['images'] = render_images(store,history_dates)
                update(f'生成候选四图 {index+1}/{target_count}',40+50*(index+1)/target_count)
            evidence['result_message'] = '已完成数值检索与四图；本次未启用模型复核，不输出正式Top1。'
            update('数值与四图完成',100,'PARTIALLY_COMPLETED')
            return
        if not settings.model_api_key:
            evidence['result_message'] = '模型密钥未配置；数值候选已保存，不输出正式Top1。'
            update('等待模型配置',100,'PARTIALLY_COMPLETED')
            return
        successful = []
        for index,candidate in enumerate(candidates):
            if len(successful) >= target_count:
                break
            history_dates = [candidate['history_start_date']+timedelta(days=i) for i in range(len(dates))]
            update(f'四图复核：数值第{index+1}名，已完成{len(successful)}/{target_count}',40+55*len(successful)/target_count)
            try:
                candidate['images'] = render_images(store,history_dates)
                for attempt in range(2):
                    try:
                        review,cache_key,is_cached = review_images(evidence['current_images'],candidate['images'],candidate['history_start_date'],dates,history_dates)
                        candidate.update(review=review,review_cache_key=cache_key,is_cached=is_cached,image_score=review['image_score'],
                                         final_score=.6*candidate['fine_pollutant_score']+.2*candidate['meteorology_score']+.2*review['image_score'])
                        successful.append(candidate)
                        break
                    except Exception as error:
                        # Do not expose provider request headers, credentials or local connection strings.
                        reason = str(error) if isinstance(error,ValueError) else type(error).__name__
                        evidence['review_failures'].append({'history_start_date':candidate['history_start_date'],'attempt':attempt+1,'reason':reason})
                        if attempt == 1:
                            candidate['review_error'] = reason
            except Exception as error:
                candidate['review_error'] = str(error) if isinstance(error,ValueError) else type(error).__name__
            persist_candidates(task_id,candidates)
            update(f'已复核{len(successful)}/{target_count}个候选',40+55*len(successful)/target_count)
        ranked = finalize_candidates(candidates)
        if ranked:
            successful = ranked
            top = successful[0]
            evidence['residuals'] = historical_residuals(batch,dates,top['history_start_date'])
            top['history_forecast_start_time'] = evidence['residuals']['historical_forecast_start_time']
            evidence['top_history_dates'] = [item['history_start_date'] for item in successful[:3]]
            evidence['result_message'] = f'完成{len(successful)}个候选的图像复核，已形成Top3和Top1。'
            persist_candidates(task_id,candidates)
            update('匹配完成',100,'SUCCEEDED')
        else:
            evidence['result_message'] = f'仅{len(successful)}个候选完成图像复核，未形成完整Top3；不输出正式Top1。'
            update('部分完成',100,'PARTIALLY_COMPLETED')
    except Exception as error:
        logger.exception('Task %s failed',task_id)
        evidence['error'] = str(error) if isinstance(error,ValueError) else f'任务执行失败（{type(error).__name__}），请检查服务日志'
        update('任务失败',100,'FAILED')
    finally:
        job_lock.release()
