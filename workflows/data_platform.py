from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from backend.config import settings


@dataclass(frozen=True)
class DataPlatformBatch:
    batch_id: str
    forecast_start_time: datetime
    model_name: str
    model_version: str
    payload: dict[str, Any]


class DataPlatformAdapter(Protocol):
    async def fetch_incremental(self, after_batch_id: str | None) -> list[DataPlatformBatch]: ...


class MockDataPlatformAdapter:
    async def fetch_incremental(self, after_batch_id: str | None) -> list[DataPlatformBatch]:
        return []


def create_data_platform_adapter() -> DataPlatformAdapter:
    if settings.data_platform_mode == 'mock':
        return MockDataPlatformAdapter()
    raise RuntimeError('真实数据中台接口契约尚未配置，请保持DATA_PLATFORM_MODE=mock')
