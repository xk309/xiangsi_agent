import base64
from hashlib import sha256
import json
import math
from datetime import datetime,timezone
import httpx
from backend.config import settings
from backend.database import query,execute,as_json
from backend.weather import PRODUCTS

PROMPT_VERSION = 'four-fields-v2.1-fixed2025-2-exact-dates'


def validate_review(raw, historical_start, length):
    if not isinstance(raw,dict) or raw.get('history_start_date') != str(historical_start):
        raise ValueError('模型响应的历史候选身份不匹配')
    days = raw.get('days')
    if not isinstance(days,list) or len(days) != length:
        raise ValueError('模型响应未覆盖每个相对日')
    def score(value):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError('模型分项必须是0—100的有效数字，无法判断时不能补分')
        return float(value)
    daily_scores = []
    for index,day in enumerate(days,1):
        if not isinstance(day,dict) or day.get('relative_day') != index:
            raise ValueError('模型响应相对日顺序不匹配')
        values = [score(day.get(field)) for field in ('wind_score','pressure_score','temperature_humidity_score','circulation_500_score')]
        for field in ('similarities','differences','shanghai_position'):
            if not isinstance(day.get(field),str) or not day[field].strip():
                raise ValueError('图像评分缺少必要的文字证据')
        daily_scores.append(sum(a*b for a,b in zip(values,[.3,.2,.2,.3])))
    if not isinstance(raw.get('summary'),str) or not raw['summary'].strip():
        raise ValueError('图像复核缺少总结证据')
    if length == 1:
        image_score = daily_scores[0]
        raw['evolution_score'] = None
    else:
        image_score = .9*sum(daily_scores)/length + .1*score(raw.get('evolution_score'))
    return {**raw,'daily_scores':daily_scores,'image_score':image_score}


def review_images(current_images,historical_images,historical_start,current_dates,historical_dates):
    if not settings.model_api_key:
        raise ValueError('尚未配置模型密钥')
    metadata = {'model':settings.model_name,'base_url':settings.model_base_url,'prompt_version':PROMPT_VERSION,
                'current_images':current_images,'historical_images':historical_images,
                'history_start_date':str(historical_start),'current_dates':[str(x) for x in current_dates],
                'historical_dates':[str(x) for x in historical_dates]}
    cache_key = sha256(json.dumps(metadata,sort_keys=True).encode()).hexdigest()
    image_rows = {}
    for side, images, dates in [('当前', current_images, current_dates), ('历史', historical_images, historical_dates)]:
        for product in PRODUCTS:
            rows = query('SELECT image_bytes,metadata FROM match_image WHERE image_hash=%s', (images[product],))
            if not rows:
                raise ValueError('复核图片不存在')
            if rows[0]['metadata'].get('dates') != [str(day) for day in dates] or rows[0]['metadata'].get('product') != product:
                raise ValueError('复核图片的日期或图层与任务不一致')
            image_rows[(side, product)] = rows[0]
    cached = query('SELECT validated_review FROM match_image_review WHERE cache_key=%s',(cache_key,))
    if cached and cached[0]['validated_review']:
        return cached[0]['validated_review'], cache_key, True
    instructions = '''你是气象空间场比较助手。这些都是合成日均测试场，不是真实09:00预报。
比较每类当前图与历史图中相同相对日。星号标记上海。只能根据可见空间结构给分，不推断污染源或全天持续过程。
只返回JSON：{"history_start_date":"指定历史首日","days":[{"relative_day":1,"wind_score":0到100,
"pressure_score":0到100,"temperature_humidity_score":0到100,"circulation_500_score":0到100,
"similarities":"相同结构的中文证据","differences":"不同结构的中文证据","shanghai_position":"结构相对上海的位置"}],
"evolution_score":多日演变一致性0到100或单日null,"summary":"中文综合解释"}。
days必须按相对日覆盖每一天。分数越高代表越相似，不能输出最终综合分或替程序排序。
任何必需图无法判断时，对应分数返回null并说明原因，不能捏造分数。''' 
    content = [{'type':'text','text':instructions+'\n任务信息：'+json.dumps(metadata,ensure_ascii=False)}]
    for side,images in [('当前',current_images),('历史',historical_images)]:
        for product in PRODUCTS:
            encoded = base64.b64encode(bytes(image_rows[(side, product)]['image_bytes'])).decode()
            content.extend([{'type':'text','text':f'{side} / {product}'},
                            {'type':'image_url','image_url':{'url':'data:image/png;base64,'+encoded}}])
    payload = {'model':settings.model_name,'messages':[{'role':'user','content':content}],
               'temperature':0,'max_tokens':settings.model_max_tokens,'enable_thinking':False,
               'response_format':{'type':'json_object'}}
    # HTTP and malformed-model failures are handled by the task's one retry policy.
    with httpx.Client(timeout=settings.model_timeout_seconds) as client:
        response = client.post(settings.model_base_url+'/chat/completions',json=payload,
                               headers={'Authorization':'Bearer '+settings.model_api_key})
    try:
        raw_response = response.json()
    except ValueError:
        raw_response = {'unparsed_body':response.text[:20000]}
    attempt = {'received_at':datetime.now(timezone.utc).isoformat(),'http_status':response.status_code,'response':raw_response}
    execute('''INSERT INTO match_image_review(cache_key,model_name,request_metadata,raw_response,response_history)
               VALUES(%s,%s,%s,%s,%s) ON CONFLICT(cache_key) DO UPDATE SET
               raw_response=EXCLUDED.raw_response,
               response_history=CASE WHEN match_image_review.response_history='[]'::jsonb
                   THEN jsonb_build_array(jsonb_build_object('response',match_image_review.raw_response,'legacy',true))
                   ELSE match_image_review.response_history END || EXCLUDED.response_history''',
            (cache_key,settings.model_name,as_json(metadata),as_json(raw_response),as_json([attempt])))
    if response.status_code >= 400:
        raise ValueError(f'模型接口返回HTTP {response.status_code}，请核验模型权限、接口兼容性及配额')
    try:
        text = raw_response['choices'][0]['message']['content'].strip()
        if text.startswith('```'):
            text = text.split('\n',1)[1].rsplit('```',1)[0].strip()
        validated = validate_review(json.loads(text),str(historical_start),len(current_dates))
    except (KeyError,IndexError,TypeError,json.JSONDecodeError) as error:
        raise ValueError('模型响应格式无效；原始响应已保留') from error
    execute('UPDATE match_image_review SET validated_review=%s WHERE cache_key=%s',(as_json(validated),cache_key))
    return validated, cache_key, False
