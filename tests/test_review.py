import unittest
from backend.model_review import validate_review


class ReviewTests(unittest.TestCase):
    def test_single_day_composition_and_identity(self):
        raw = {'history_start_date':'2025-01-01','days':[{'relative_day':1,'wind_score':80,
            'pressure_score':70,'temperature_humidity_score':90,'circulation_500_score':60,
            'similarities':'风向相近','differences':'气压位置不同','shanghai_position':'位于高压东侧'}],
            'evolution_score':None,'summary':'合成场结构相近'}
        result = validate_review(raw,'2025-01-01',1)
        self.assertEqual(result['image_score'],74)
        with self.assertRaises(ValueError):
            validate_review(raw,'2025-01-02',1)
        raw['days'][0]['wind_score'] = 101
        with self.assertRaises(ValueError):
            validate_review(raw,'2025-01-01',1)


if __name__ == '__main__':
    unittest.main()
