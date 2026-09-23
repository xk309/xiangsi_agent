import unittest
import numpy as np
from backend.circulation import classify_circulation, extract_field_features


class CirculationTests(unittest.TestCase):
    def test_reviewed_policy_boundary_and_multiple_labels(self):
        policy = {'version': 'test-v1', 'source': 'test-only', 'rules': [
            {'label': '地面偏高测试标签', 'conditions': [{'feature': 'pressure_departure_hpa', 'operator': 'ge', 'threshold': 2}]},
            {'label': '偏北风测试标签', 'conditions': [{'feature': 'northward_wind_10m', 'operator': 'lt', 'threshold': 0}]}]}
        result = classify_circulation({'pressure_departure_hpa': 2, 'northward_wind_10m': -1}, policy)
        self.assertEqual(len(result['labels']), 2)
        self.assertEqual(len(result['rule_hash']), 64)
        self.assertEqual(classify_circulation({}, policy)['status'], 'missing')
        self.assertEqual(classify_circulation({}, None)['status'], 'not_configured')

    def test_spatial_features_are_computed_not_invented_labels(self):
        pressure = np.array([[1000., 1004.], [1000., 1000.]])
        height = np.full((2, 2), 5600.)
        winds = (np.ones((2, 2)), -np.ones((2, 2)))
        features = extract_field_features(pressure, height, winds, winds, (0, 1), (0, 0))
        self.assertEqual(features['pressure_departure_hpa'], 3)
        self.assertEqual(features['height_departure_500_m'], 0)
        self.assertEqual(features['northward_wind_10m'], -1)

    def test_unknown_feature_and_code_operator_rejected(self):
        policy = {'version': 'test-v1', 'source': 'test-only', 'rules': [
            {'label': '错误规则', 'conditions': [{'feature': '__import__', 'operator': 'gt', 'threshold': 0}]}]}
        with self.assertRaises(ValueError):
            classify_circulation({}, policy)
