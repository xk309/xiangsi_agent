from datetime import date
from typing import Any
from uuid import UUID
from hashlib import sha256
import json
import numpy as np

from backend.data_source import list_batches
from backend.database import query
from backend.matching import GRID_IDS, POLLUTANTS, WEATHER_FIELDS


def _valid_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as error:
        raise ValueError('task_id必须是有效UUID') from error


def _task(task_id: str) -> dict[str, Any]:
    rows = query(
        '''SELECT t.status,e.stage,e.evidence,e.created_at,e.updated_at
           FROM similarity_match_task t JOIN match_task_evidence e USING(task_id)
           WHERE task_id=%s''',
        (_valid_uuid(task_id),),
    )
    if not rows:
        raise ValueError('匹配任务不存在')
    return rows[0]


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: candidate.get(key) for key in (
            'history_start_date', 'history_end_date', 'coarse_rank', 'fine_rank', 'final_rank',
            'coarse_score', 'fine_score', 'fine_pollutant_score', 'meteorology_score',
            'image_score', 'final_score', 'review_cache_key', 'is_low_similarity',
        ) if candidate.get(key) is not None
    }


def _formal_top3(task_status, candidates):
    selected = [item for item in candidates if item.get('final_rank') in (1, 2, 3)]
    if task_status != 'SUCCEEDED' or len(selected) != 3 or {item['final_rank'] for item in selected} != {1, 2, 3}:
        return []
    if not all(item.get('review') and item.get('image_score') is not None for item in selected):
        return []
    return sorted(selected, key=lambda item: item['final_rank'])


def list_forecast_batches(limit: int, offset: int) -> dict[str, Any]:
    batches = list_batches()
    items = batches[offset:offset + limit]
    return {
        'status': 'ok', 'total_count': len(batches), 'count': len(items), 'offset': offset,
        'has_more': offset + len(items) < len(batches),
        'next_offset': offset + len(items) if offset + len(items) < len(batches) else None,
        'items': items,
    }


def get_task_result(task_id: str) -> dict[str, Any]:
    row = _task(task_id)
    evidence = row['evidence']
    candidates = sorted(
        evidence.get('candidates', []),
        key=lambda item: (item.get('final_rank') is None, item.get('final_rank', 9999)),
    )
    return {
        'status': 'ok',
        'task_id': task_id,
        'task_status': row['status'],
        'stage': row['stage'],
        'progress': evidence.get('progress'),
        'forecast_start_time': evidence.get('forecast_start_time'),
        'dates': evidence.get('dates', []),
        'result_message': evidence.get('result_message'),
        'warning': evidence.get('warning'),
        'final_weights': evidence.get('final_weights'),
        'top3': [_candidate_summary(item) for item in _formal_top3(row['status'], candidates)],
        'provisional_candidates': [_candidate_summary(item) for item in candidates[:3]],
        'updated_at': row['updated_at'],
    }


def search_historical_candidates(task_id: str, limit: int, offset: int) -> dict[str, Any]:
    candidates = _task(task_id)['evidence'].get('candidates', [])
    candidates = sorted(
        candidates,
        key=lambda item: (
            item.get('final_rank') is None,
            item.get('final_rank', item.get('fine_rank', 9999)),
        ),
    )
    items = candidates[offset:offset + limit]
    return {
        'status': 'ok', 'total_count': len(candidates), 'count': len(items), 'offset': offset,
        'has_more': offset + len(items) < len(candidates),
        'next_offset': offset + len(items) if offset + len(items) < len(candidates) else None,
        'items': [_candidate_summary(item) for item in items],
    }


def get_candidate_metrics(task_id: str, history_start_date: date) -> dict[str, Any]:
    candidates = _task(task_id)['evidence'].get('candidates', [])
    candidate = next(
        (item for item in candidates if str(item.get('history_start_date')) == history_start_date.isoformat()),
        None,
    )
    if candidate is None:
        raise ValueError('任务中不存在该历史候选')
    allowed = (
        'history_start_date', 'history_end_date', 'coarse_rank', 'fine_rank', 'final_rank',
        'coarse_score', 'fine_score', 'coarse_pollutant_score', 'fine_pollutant_score',
        'meteorology_label_score', 'meteorology_score', 'image_score', 'final_score',
        'pollutant_details', 'meteorology_details', 'review', 'is_low_similarity',
    )
    return {'status': 'ok', 'candidate': {key: candidate.get(key) for key in allowed if key in candidate}}


def get_weather_images(task_id: str) -> dict[str, Any]:
    evidence = _task(task_id)['evidence']
    ranked = sorted(
        (item for item in evidence.get('candidates', []) if item.get('images')),
        key=lambda item: (item.get('final_rank') is None, item.get('final_rank', item.get('fine_rank', 9999))),
    )
    return {
        'status': 'ok',
        'current': evidence.get('current_images', {}),
        'top3': [
            {'history_start_date': item.get('history_start_date'), 'images': item['images']}
            for item in ranked[:3]
        ],
        'image_endpoint': '/api/images/{image_hash}',
    }


def get_review_evidence(cache_key: str) -> dict[str, Any]:
    if len(cache_key) != 64 or any(character not in '0123456789abcdef' for character in cache_key):
        raise ValueError('cache_key格式无效')
    rows = query(
        'SELECT model_name,request_metadata,validated_review,created_at FROM match_image_review WHERE cache_key=%s',
        (cache_key,),
    )
    if not rows:
        raise ValueError('模型复核证据不存在')
    return {'status': 'ok', **rows[0]}


def get_analysis_snapshot(task_id: str) -> dict[str, Any]:
    """One database read freezes all evidence used by an analysis run."""
    row = _task(task_id)
    data = row['evidence']
    version = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    candidates = sorted(data.get('candidates', []), key=lambda item: item.get('final_rank') or item.get('fine_rank') or 9999)
    formal = _formal_top3(row['status'], candidates)
    is_formal = len(formal) == 3
    dates = data.get('dates', [])
    pollution = []
    values = np.asarray(data.get('current_values', []), dtype=float)
    if values.shape == (len(dates), 9, 4) and len(dates) and np.isfinite(values).all():
        for day, grids in zip(dates, values):
            pollution.append({'date': day, 'grids': [
                {'grid': grid, **dict(zip(POLLUTANTS, map(float, concentrations)))}
                for grid, concentrations in zip(GRID_IDS, grids)
            ]})
    weather = []
    values = np.asarray(data.get('current_weather', []), dtype=float)
    if values.shape == (len(dates), 9, 6) and len(dates) and np.isfinite(values).all():
        for day, grids in zip(dates, values):
            weather.append({'date': day, 'grid_mean': dict(zip(WEATHER_FIELDS, map(float, grids.mean(axis=0))))})
    residuals = data.get('residuals', {})
    rows = residuals.get('rows', [])
    residual_summary = []
    for pollutant in POLLUTANTS:
        selected = [float(item['residual']) for item in rows if item.get('pollutant_name') == pollutant and item.get('residual') is not None]
        if selected:
            residual_summary.append({'pollutant': pollutant, 'count': len(selected), 'mean_residual': sum(selected) / len(selected)})
    return {
        'status': 'ok', 'task_id': task_id, 'snapshot_version': version,
        'task': {'task_status': row['status'], 'stage': row['stage'], 'dates': dates,
                 'forecast_start_time': data.get('forecast_start_time'), 'is_formal_top3': is_formal,
                 'warning': data.get('warning'), 'final_weights': data.get('final_weights'),
                 'top3': [_candidate_summary(item) for item in formal] if is_formal else [],
                 'result_message': data.get('result_message')},
        'pollution': {'status': 'ok' if pollution else 'missing', 'daily_grids': pollution,
                      'unit': 'μg/m³', 'limitation': '九宫格不是行政区；固定联调统计不是正式AQI。'},
        'weather': {'status': 'ok' if weather else 'missing', 'daily_grid_means': weather,
                    'daily_labels': data.get('current_weather_labels', []),
                    'circulation_rules': data.get('current_circulation', []),
                    'limitation': data.get('warning', '需确认气象来源与空间范围。')},
        'candidates': {'status': 'ok', 'is_formal_top3': is_formal,
                       'items': [_candidate_summary(item) for item in candidates[:10]]},
        'reviews': {'status': 'ok' if any(item.get('review') for item in candidates[:3]) else 'missing',
                    'score_definition': 'review.image_score仅是气象图像分，不是final_score最终综合分。正式排名和综合分见task.top3。',
                    'items': [{'history_start_date': item.get('history_start_date'),
                               'review': item['review'], 'images': item.get('images', {}),
                               'review_cache_key': item.get('review_cache_key')}
                              for item in candidates[:3] if item.get('review')],
                    'current_images': data.get('current_images', {})},
        'residuals': {'status': 'ok' if residual_summary else 'missing', 'items': residual_summary,
                      'is_adjustment_enabled': False, 'sign': '历史实况−历史预测',
                      'reason': residuals.get('reason', '缺少同口径历史预测与实况。'),
                      'comparability_assumption': residuals.get('comparability_assumption')},
    }
