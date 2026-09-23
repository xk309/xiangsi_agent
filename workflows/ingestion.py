import asyncio
import os
from pathlib import Path
from tempfile import gettempdir
from typing import Any

os.environ.setdefault('PREFECT_SERVER_ANALYTICS_ENABLED', 'false')
os.environ.setdefault('PREFECT_HOME', str(Path(gettempdir()) / 'xiangsi-prefect'))

from prefect import flow, task

from workflows.data_platform import DataPlatformBatch, create_data_platform_adapter


@task(retries=2, retry_delay_seconds=30)
async def fetch_incremental_batches(after_batch_id: str | None) -> list[DataPlatformBatch]:
    adapter = create_data_platform_adapter()
    return await adapter.fetch_incremental(after_batch_id)


@task
def validate_batches(batches: list[DataPlatformBatch]) -> list[DataPlatformBatch]:
    identifiers = [batch.batch_id for batch in batches]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('数据中台返回了重复batch_id')
    return batches


@task
def persist_batches(batches: list[DataPlatformBatch]) -> dict[str, Any]:
    if batches:
        raise RuntimeError('真实入库映射尚未确认，禁止把模拟契约写入业务表')
    return {
        'mode': 'mock',
        'received_count': 0,
        'persisted_count': 0,
        'status': 'waiting_for_data_platform_contract',
    }


@flow(name='similarity-data-platform-ingestion', log_prints=True)
async def run_incremental_ingestion(after_batch_id: str | None = None) -> dict[str, Any]:
    batches = await fetch_incremental_batches(after_batch_id)
    validated = validate_batches(batches)
    return persist_batches(validated)


if __name__ == '__main__':
    asyncio.run(run_incremental_ingestion())
