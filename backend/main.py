from contextlib import asynccontextmanager
from datetime import date,datetime
from pathlib import Path
from uuid import UUID
import logging
from fastapi import FastAPI,HTTPException,Response,Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend.config import settings,ROOT
from backend.database import query,migrate,execute
from backend.data_source import list_batches
from backend.service import create_task,WARNING,executor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    try:
        migrate()
        # A single server process owns jobs. Restarted in-flight tasks are explicit failures.
        execute('''UPDATE match_task_evidence e SET stage='服务重启，任务已中断',
            evidence=evidence || '{"error":"服务重启导致执行中断，请新建任务","progress":100}'::jsonb,updated_at=now()
            FROM similarity_match_task t WHERE t.task_id=e.task_id AND t.status='RUNNING' ''')
        execute("UPDATE similarity_match_task SET status='FAILED' WHERE status='RUNNING' AND task_id IN (SELECT task_id FROM match_task_evidence)")
    except Exception:
        logger.exception('Database startup verification failed')
    yield
    executor.shutdown(wait=True)


app = FastAPI(title='上海污染过程相似度匹配',version='0.1.0',lifespan=lifespan)


@app.middleware('http')
async def local_mutations_only(request:Request,call_next):
    if request.method in ('POST','PUT','PATCH','DELETE'):
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            return Response('跨站写入请求被拒绝',status_code=403)
    return await call_next(request)


@app.get('/api/health')
def health():
    database_ready = False
    try:
        query('SELECT 1 FROM station LIMIT 1')
        database_ready = True
    except Exception:
        pass
    return {'database_ready':database_ready,'weather_ready':settings.weather_file.is_file(),
            'model_configured':bool(settings.model_api_key),'model_name':settings.model_name,
            'warning':WARNING}


@app.get('/api/batches')
def batches():
    try:
        return list_batches()
    except Exception as error:
        raise HTTPException(503,'无法读取数据库，请检查本地连接配置') from error


@app.get('/api/stations')
def stations():
    return query('SELECT * FROM station ORDER BY station_id')


class MatchRequest(BaseModel):
    forecast_start_time: datetime
    window_start_date: date
    window_end_date: date
    should_review: bool = True


@app.post('/api/tasks',status_code=202)
def start_match(request:MatchRequest):
    if request.forecast_start_time.tzinfo is not None:
        raise HTTPException(422,'预测批次使用数据库中的北京时间，不附加时区偏移')
    try:
        return {'task_id':create_task(request.forecast_start_time,request.window_start_date,request.window_end_date,request.should_review)}
    except ValueError as error:
        raise HTTPException(422,str(error)) from error
    except Exception as error:
        raise HTTPException(503,'无法创建任务，请检查数据库和扩展表') from error


@app.get('/api/tasks')
def list_tasks():
    return query('''SELECT t.*,e.stage,e.created_at,e.updated_at FROM similarity_match_task t
        JOIN match_task_evidence e USING(task_id) ORDER BY e.created_at DESC LIMIT 50''')


@app.get('/api/tasks/{task_id}')
def get_task(task_id:UUID):
    rows = query('''SELECT t.status,e.evidence FROM similarity_match_task t
        JOIN match_task_evidence e USING(task_id) WHERE task_id=%s''',(str(task_id),))
    if not rows:
        raise HTTPException(404,'任务不存在')
    return {**rows[0]['evidence'],'status':rows[0]['status']}


@app.get('/api/images/{image_hash}')
def image(image_hash:str):
    if len(image_hash) != 64 or any(character not in '0123456789abcdef' for character in image_hash):
        raise HTTPException(404,'图片不存在')
    rows = query('SELECT image_bytes FROM match_image WHERE image_hash=%s',(image_hash,))
    if not rows:
        raise HTTPException(404,'图片不存在')
    return Response(bytes(rows[0]['image_bytes']),media_type='image/png',headers={'Cache-Control':'private, max-age=31536000, immutable','ETag':image_hash})


@app.get('/api/reviews/{cache_key}')
def review_evidence(cache_key:str):
    rows = query('SELECT model_name,request_metadata,raw_response,validated_review FROM match_image_review WHERE cache_key=%s',(cache_key,))
    if not rows:
        raise HTTPException(404,'复核记录不存在')
    return rows[0]


frontend_dist = ROOT/'frontend'/'dist'
if frontend_dist.is_dir():
    app.mount('/',StaticFiles(directory=frontend_dist,html=True),name='frontend')
