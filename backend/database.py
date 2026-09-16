from contextlib import contextmanager
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
import json
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor, Json
from backend.config import settings


def json_default(value):
    if isinstance(value,(date,datetime)):
        return value.isoformat()
    if hasattr(value,'item'):
        return value.item()
    raise TypeError(type(value).__name__)


def as_json(value):
    return Json(value, dumps=lambda data:json.dumps(data,default=json_default,ensure_ascii=False,allow_nan=False))


@contextmanager
def connection():
    database = psycopg2.connect(connect_timeout=5, application_name='xiangsi_demo')
    try:
        with database.cursor() as cursor:
            cursor.execute(sql.SQL('SET search_path TO {}, public').format(sql.Identifier(settings.database_schema)))
            cursor.execute("SET statement_timeout TO '60s'")
        yield database
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def query(statement, parameters=()):
    with connection() as database, database.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(statement,parameters)
        return [dict(row) for row in cursor.fetchall()]


def execute(statement, parameters=()):
    with connection() as database, database.cursor() as cursor:
        cursor.execute(statement,parameters)


def migrate():
    with connection() as database, database.cursor() as cursor:
        cursor.execute((Path(__file__).parent/'schema.sql').read_text(encoding='utf-8'))


def save_task(task_id, status, stage, evidence):
    with connection() as database, database.cursor() as cursor:
        cursor.execute('UPDATE similarity_match_task SET status=%s WHERE task_id=%s',(status,task_id))
        cursor.execute('UPDATE match_task_evidence SET stage=%s,evidence=%s,updated_at=now() WHERE task_id=%s',
                       (stage,as_json(evidence),task_id))


def save_image(png, metadata):
    image_hash = sha256(png).hexdigest()
    execute('INSERT INTO match_image(image_hash,image_bytes,metadata) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',
            (image_hash,psycopg2.Binary(png),as_json(metadata)))
    return image_hash
