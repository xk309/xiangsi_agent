import unittest
from datetime import date
from unittest.mock import patch

from mcp_server import tools


TASK_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'


class McpToolTests(unittest.TestCase):
    def test_formal_top3_requires_complete_ranks_and_reviewed_images(self):
        candidates = [{'final_rank': index, 'image_score': 80, 'review': {'summary': 'checked'}} for index in (1, 2, 3)]
        self.assertEqual(len(tools._formal_top3('SUCCEEDED', candidates)), 3)
        self.assertEqual(tools._formal_top3('RUNNING', candidates), [])
        candidates[2]['final_rank'] = 2
        self.assertEqual(tools._formal_top3('SUCCEEDED', candidates), [])

    @patch('mcp_server.tools.query')
    def test_task_result_is_compact_and_does_not_return_raw_arrays(self, database_query):
        database_query.return_value = [{
            'status': 'SUCCEEDED',
            'stage': '匹配完成',
            'created_at': '2026-01-01',
            'updated_at': '2026-01-01',
            'evidence': {
                'progress': 100,
                'current_values': [[[1]]],
                'candidates': [{
                    'history_start_date': '2024-01-01',
                    'final_rank': 1,
                    'final_score': 88.5,
                    'historical_values': [[[2]]],
                }],
            },
        }]
        result = tools.get_task_result(TASK_ID)
        self.assertEqual(result['top3'], [])
        self.assertEqual(result['provisional_candidates'][0]['final_score'], 88.5)
        self.assertNotIn('current_values', result)
        self.assertNotIn('historical_values', result['provisional_candidates'][0])

    @patch('mcp_server.tools.query')
    def test_candidate_metrics_requires_candidate_in_task(self, database_query):
        database_query.return_value = [{
            'status': 'SUCCEEDED', 'stage': '完成', 'created_at': '', 'updated_at': '',
            'evidence': {'candidates': []},
        }]
        with self.assertRaisesRegex(ValueError, '不存在'):
            tools.get_candidate_metrics(TASK_ID, date(2024, 1, 1))

    def test_invalid_task_id_is_rejected_before_database_query(self):
        with self.assertRaisesRegex(ValueError, 'UUID'):
            tools.get_task_result('not-a-task')


if __name__ == '__main__':
    unittest.main()
