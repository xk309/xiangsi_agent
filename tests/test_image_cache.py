from datetime import date
from dataclasses import replace
from unittest.mock import Mock, patch
import unittest
from backend.service import render_images
from backend.weather import PRODUCTS
from backend.model_review import review_images
from backend.config import settings


class ImageCacheTests(unittest.TestCase):
    @patch('backend.model_review.httpx.Client')
    @patch('backend.model_review.query')
    def test_wrong_image_dates_are_rejected_before_cache_or_model(self, query, client):
        query.return_value = [{'image_bytes': b'png', 'metadata': {'dates': ['2025-01-01', '2025-01-02'], 'product': 'temperature'}}]
        with patch('backend.model_review.settings', replace(settings, model_api_key='test-key')):
            with self.assertRaisesRegex(ValueError, '日期或图层'):
                review_images({product: product for product in PRODUCTS}, {product: product for product in PRODUCTS},
                              date(2024, 1, 1), [date(2025, 1, 2)], [date(2024, 1, 1)])
        client.assert_not_called()
        self.assertEqual(query.call_count, 1)

    @patch('backend.service.save_image', side_effect=lambda png, metadata: metadata['product'] + '-new')
    @patch('backend.service.query')
    def test_single_day_does_not_reuse_containing_multi_day_window(self, query, save_image):
        query.return_value = [{'image_hash': product + '-old', 'metadata': {'product': product,
            'dates': ['2025-01-01', '2025-01-02']}} for product in PRODUCTS]
        store = Mock(source_hash='source')
        store.render.return_value = {product: b'png' for product in PRODUCTS}
        images = render_images(store, [date(2025, 1, 2)])
        store.render.assert_called_once()
        self.assertTrue(all(value.endswith('-new') for value in images.values()))
        self.assertIn("metadata->'dates' = %s", query.call_args.args[0])

    @patch('backend.service.query')
    def test_exact_window_reuses_four_cached_images(self, query):
        query.return_value = [{'image_hash': product, 'metadata': {'product': product,
            'dates': ['2025-01-02']}} for product in PRODUCTS]
        store = Mock(source_hash='source')
        images = render_images(store, [date(2025, 1, 2)])
        store.render.assert_not_called()
        self.assertEqual(set(images), set(PRODUCTS))
