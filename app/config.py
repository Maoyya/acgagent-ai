from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_name: str = "acgagent-ai"
    app_version: str = "1.0.0"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8100

    api_key: str = "dev-api-key"

    data_dir: Path = Path("./data")

    log_level: str = "INFO"

    model_config = {"env_prefix": "ACG_AI_", "env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
