import unittest
import numpy as np

from backend.matching import compare_pollutants, evaluate_concentration, compare_weather, select_nonoverlapping, validate_window, finalize_candidates
from datetime import date


class MatchingTests(unittest.TestCase):
    def test_document_three_day_candidate_b(self):
        # V2.1 的108维独立算例，不能用中心格代替九格。
        center = np.array([[40, 70, 40, 100], [80, 130, 90, 180], [50, 90, 50, 120]])
        current = center[:, None, :] + np.array([-8, -4, 0, -4, 0, 4, 0, 4, 8])[None, :, None]
        result = compare_pollutants(current, current - 5, np.full((9, 4), 10.), np.tile([3, 6, 4, 8], (9, 1)))
        self.assertAlmostEqual(result['numeric_score'], 66.6666667)
        self.assertAlmostEqual(result['daily_band_score'], 94.4444444)
        self.assertAlmostEqual(result['coarse_pollutant_score'], 76.1111111)
        self.assertAlmostEqual(result['fine_pollutant_score'], 76.4444444)

    def test_single_day_boundaries_and_missing_data(self):
        values = np.full((1,9,4), 60.)
        result = compare_pollutants(values, values, np.ones((9,4)), np.ones((9,4)))
        self.assertEqual(result['fine_pollutant_score'], 100)
        self.assertIsNone(result['process_score'])
        self.assertEqual(evaluate_concentration(60.5, 0)['evaluation_concentration'], 60)
        self.assertEqual(evaluate_concentration(61.5, 0)['evaluation_concentration'], 62)
        self.assertEqual(evaluate_concentration(80, 0)['air_quality_subindex'], 119)
        self.assertEqual(evaluate_concentration(801, 3)['air_quality_subindex'], 300)
        values[0,0,0] = np.nan
        with self.assertRaises(ValueError):
            compare_pollutants(values, values, np.ones((9,4)), np.ones((9,4)))

    def test_calm_wind_is_excluded_per_day_and_unknown_fails(self):
        labels = [['正常','高湿','弱风','静风','正常','中'], ['正常','高湿','弱风','北','正常','中']]
        other = [['偏冷','高湿','弱风','北','正常','中'], ['正常','高湿','弱风','西北','正常','中']]
        result = compare_weather(np.ones((2,9,6)),np.ones((2,9,6)), labels, other, np.ones((9,6)))
        self.assertAlmostEqual(result['label_score'], 90.833333333)
        self.assertEqual(result['numeric_score'], 100)
        other[0][0] = '未知'
        with self.assertRaises(ValueError):
            compare_weather(np.ones((2,9,6)),np.ones((2,9,6)), labels, other, np.ones((9,6)))

    def test_window_validation_and_greedy_date_deduplication(self):
        with self.assertRaises(ValueError):
            validate_window(date(2025,1,1),date(2025,1,3),[date(2025,1,1),date(2025,1,3)])
        candidates = [{'history_start_date':date(2025,1,2)}, {'history_start_date':date(2025,1,1)}, {'history_start_date':date(2025,1,5)}]
        self.assertEqual([x['history_start_date'].day for x in select_nonoverlapping(candidates,3)], [2,5])

    def test_seven_day_plateau_and_exact_change_threshold(self):
        values = np.broadcast_to(np.array([40,43,80,80,43,40,40])[:,None,None],(7,9,4)).copy()
        result = compare_pollutants(values, values, np.ones((9,4)), np.full((9,4),3.))
        feature = result['current_features'][0]
        self.assertEqual(feature['directions'],['STABLE','UP','STABLE','DOWN','STABLE','STABLE'])
        self.assertEqual(feature['peak_positions'],[3,4])
        self.assertEqual(feature['pattern'],'先升后降')
        self.assertEqual(feature['exceedance_days'],2)
        self.assertEqual(feature['longest_run'],2)
        self.assertEqual(result['fine_pollutant_score'],100)

    def test_final_rank_is_absent_without_three_valid_reviews(self):
        candidates = [{'history_start_date':date(2025,1,i),'fine_pollutant_score':80.,'meteorology_score':70.,
                       'fine_score':76.,'coarse_score':75.,'image_score':90.} for i in range(1,4)]
        self.assertEqual(finalize_candidates(candidates[:2]),[])
        self.assertTrue(all('final_rank' not in c for c in candidates))
        result = finalize_candidates(candidates)
        self.assertEqual([c['history_start_date'].day for c in result],[1,2,3])
        self.assertEqual(result[0]['final_score'],80.)
        self.assertEqual(result[0]['final_rank'],1)


if __name__ == '__main__':
    unittest.main()
