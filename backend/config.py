from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


@dataclass(frozen=True)
class Settings:
    database_schema: str = os.getenv('DATABASE_SCHEMA', 'similarity_match')
    weather_file: Path = (ROOT / os.getenv('WEATHER_FILE', '../数据处理与建表/mock_qixiang/synthetic_meteorology_20250101_20251231.nc')).resolve()
    model_base_url: str = os.getenv('MODEL_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1').rstrip('/')
    model_name: str = os.getenv('MODEL_NAME', 'qwen3.8-max')
    model_api_key: str = os.getenv('MODEL_API_KEY', '')
    model_timeout_seconds: float = float(os.getenv('MODEL_TIMEOUT_SECONDS', '120'))
    model_max_tokens: int = int(os.getenv('MODEL_MAX_TOKENS', '6000'))


settings = Settings()
