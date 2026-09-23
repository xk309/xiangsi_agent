"""Versioned rule classification; thresholds must come from reviewed business policy."""
from hashlib import sha256
import json
import operator
from typing import Literal
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

FEATURE_NAMES = {'local_pressure_hpa', 'pressure_departure_hpa', 'pressure_spread_hpa',
                 'local_height_500_m', 'height_departure_500_m', 'eastward_wind_10m',
                 'northward_wind_10m', 'eastward_wind_500', 'northward_wind_500'}
OPERATORS = {'gt': operator.gt, 'ge': operator.ge, 'lt': operator.lt, 'le': operator.le}


class Condition(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    feature: str
    operator: Literal['gt', 'ge', 'lt', 'le']
    threshold: float


class CirculationRule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(min_length=1, max_length=100)
    conditions: list[Condition] = Field(min_length=1, max_length=12)


class CirculationPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=200)
    rules: list[CirculationRule] = Field(min_length=1, max_length=50)


def classify_circulation(features, policy):
    if policy is None:
        return {'status': 'not_configured', 'labels': [], 'features': features,
                'message': '已提取地面与500 hPa特征，尚未配置经审核环流分类规则。'}
    policy = CirculationPolicy.model_validate(policy)
    referenced = {condition.feature for rule in policy.rules for condition in rule.conditions}
    if not referenced.issubset(FEATURE_NAMES):
        raise ValueError('环流规则引用未支持的气象特征')
    missing = sorted(name for name in referenced if name not in features or not np.isfinite(features[name]))
    if missing:
        return {'status': 'missing', 'labels': [], 'missing_features': missing, 'rule_version': policy.version}
    labels = []
    for rule in policy.rules:
        if all(OPERATORS[condition.operator](features[condition.feature], condition.threshold) for condition in rule.conditions):
            labels.append({'label': rule.label, 'conditions': [condition.model_dump() for condition in rule.conditions]})
    digest = sha256(json.dumps(policy.model_dump(), sort_keys=True).encode()).hexdigest()
    return {'status': 'ok', 'labels': labels, 'features': features, 'rule_version': policy.version,
            'rule_hash': digest, 'source': policy.source, 'message': '规则诊断，不自动更改相似度权重。'}


def extract_field_features(pressure, height, surface_winds, upper_winds, surface_point, upper_point):
    pressure, height = np.asarray(pressure, float), np.asarray(height, float)
    local_pressure, local_height = float(pressure[surface_point]), float(height[upper_point])
    features = {
        'local_pressure_hpa': local_pressure,
        'pressure_departure_hpa': local_pressure - float(np.nanmean(pressure)),
        'pressure_spread_hpa': float(np.nanstd(pressure)),
        'local_height_500_m': local_height,
        'height_departure_500_m': local_height - float(np.nanmean(height)),
        'eastward_wind_10m': float(surface_winds[0][surface_point]),
        'northward_wind_10m': float(surface_winds[1][surface_point]),
        'eastward_wind_500': float(upper_winds[0][upper_point]),
        'northward_wind_500': float(upper_winds[1][upper_point]),
    }
    return {name: value for name, value in features.items() if np.isfinite(value)}
