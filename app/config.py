"""
应用配置。

使用 pydantic-settings 从环境变量或 .env 文件加载配置。
所有环境变量前缀为 ACG_AI_（如 ACG_AI_PORT → port）。
"""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    app_name: str = "acgagent-ai"
    app_version: str = "1.0.0"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8100

    api_key: str = "dev-api-key"   # API 认证密钥，生产环境务必修改

    data_dir: Path = Path("./data")  # 所有持久化数据的根目录

    log_level: str = "INFO"

    model_config = {"env_prefix": "ACG_AI_", "env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
