import unittest

from workflows.data_platform import MockDataPlatformAdapter, create_data_platform_adapter
from workflows.ingestion import validate_batches


class IngestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_adapter_returns_no_invented_batches(self):
        adapter = create_data_platform_adapter()
        self.assertIsInstance(adapter, MockDataPlatformAdapter)
        self.assertEqual(await adapter.fetch_incremental(None), [])

    def test_duplicate_batch_id_is_rejected(self):
        from datetime import datetime
        from workflows.data_platform import DataPlatformBatch
        batch = DataPlatformBatch('same', datetime(2026, 1, 1), 'model', 'v1', {})
        with self.assertRaisesRegex(ValueError, '重复'):
            validate_batches.fn([batch, batch])


if __name__ == '__main__':
    unittest.main()
