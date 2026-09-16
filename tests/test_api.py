import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_invalid_window_is_rejected_without_creating_task(self):
        with patch('backend.service.list_batches',return_value=[]):
            response = self.client.post('/api/tasks',json={'forecast_start_time':'2025-01-01T00:00:00',
                'window_start_date':'2025-01-01','window_end_date':'2025-01-09'})
        self.assertEqual(response.status_code,422)

    def test_health_does_not_expose_credentials(self):
        with patch('backend.main.query',return_value=[{'ok':1}]):
            response = self.client.get('/api/health')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['database_ready'])
        self.assertNotIn('model_api_key',response.json())
        self.assertNotIn('PGPASSWORD',response.text)

    def test_cross_site_task_creation_is_blocked(self):
        response = self.client.post('/api/tasks',headers={'Origin':'https://external.example'},json={})
        self.assertEqual(response.status_code,403)

    def test_missing_task_and_invalid_image(self):
        with patch('backend.main.query',return_value=[]):
            self.assertEqual(self.client.get('/api/tasks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa').status_code,404)
        self.assertEqual(self.client.get('/api/images/not-a-hash').status_code,404)
