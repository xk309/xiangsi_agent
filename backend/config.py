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
    agent_model_name: str = os.getenv('AGENT_MODEL_NAME', os.getenv('MODEL_NAME', 'qwen3.8-max'))
    model_api_key: str = os.getenv('MODEL_API_KEY', '')
    model_timeout_seconds: float = float(os.getenv('MODEL_TIMEOUT_SECONDS', '120'))
    model_max_tokens: int = int(os.getenv('MODEL_MAX_TOKENS', '6000'))
    embedding_model: str = os.getenv('EMBEDDING_MODEL', '')
    reranker_model: str = os.getenv('RERANKER_MODEL', '')
    agent_model_enabled: bool = os.getenv('AGENT_MODEL_ENABLED', 'true').lower() == 'true'
    agent_checkpoint_database_url: str = os.getenv('AGENT_CHECKPOINT_DATABASE_URL', '')
    agent_checkpoint_auto_setup: bool = os.getenv('AGENT_CHECKPOINT_AUTO_SETUP', 'false').lower() == 'true'
    mcp_server_url: str = os.getenv('MCP_SERVER_URL', 'http://127.0.0.1:8010/mcp')
    mcp_host: str = os.getenv('MCP_HOST', '127.0.0.1')
    mcp_port: int = int(os.getenv('MCP_PORT', '8010'))
    data_platform_mode: str = os.getenv('DATA_PLATFORM_MODE', 'mock')
    data_platform_base_url: str = os.getenv('DATA_PLATFORM_BASE_URL', '').rstrip('/')
    data_platform_api_key: str = os.getenv('DATA_PLATFORM_API_KEY', '')
    agent_store_path: Path = ROOT / os.getenv('AGENT_STORE_PATH', '.runtime/agent.sqlite3')
    agent_max_rounds: int = int(os.getenv('AGENT_MAX_ROUNDS', '4'))
    agent_max_tool_calls: int = int(os.getenv('AGENT_MAX_TOOL_CALLS', '12'))
    agent_max_model_calls: int = int(os.getenv('AGENT_MAX_MODEL_CALLS', '16'))
    agent_timeout_seconds: float = float(os.getenv('AGENT_TIMEOUT_SECONDS', '90'))
    agent_tool_timeout_seconds: float = float(os.getenv('AGENT_TOOL_TIMEOUT_SECONDS', '15'))
    agent_context_characters: int = int(os.getenv('AGENT_CONTEXT_CHARACTERS', '24000'))
    agent_max_active_runs: int = int(os.getenv('AGENT_MAX_ACTIVE_RUNS', '4'))
    knowledge_enabled: bool = os.getenv('KNOWLEDGE_ENABLED', 'false').lower() == 'true'
    knowledge_use_vectors: bool = os.getenv('KNOWLEDGE_USE_VECTORS', 'false').lower() == 'true'
    embedding_dimensions: int = int(os.getenv('EMBEDDING_DIMENSIONS', '1024'))
    reranker_url: str = os.getenv('RERANKER_URL', '')
    circulation_rules_path: str = os.getenv('CIRCULATION_RULES_PATH', '')


settings = Settings()
