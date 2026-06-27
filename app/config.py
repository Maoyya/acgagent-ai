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

    # meta-LLM：用于提示词生成与合规校验（服务级基础设施任务，不绑定具体 Agent）
    meta_llm_provider: str = "deepseek"
    meta_llm_model: str = "deepseek-chat"
    meta_llm_base_url: str = "https://api.deepseek.com/v1"
    meta_llm_api_key: str = ""   # 缺失时 generate/moderate 返回 500

    # 对话 / Agent LLM 密钥（方案 B：按 provider 分键，由 app/core/llm.py 的 resolve_api_key 消费）。
    # 对应环境变量 ACG_AI_LLM_KEY_<PROVIDER 大写>。新增 provider 需在此声明字段（fail-loud）。
    llm_key_deepseek: str = ""
    llm_key_zhipu: str = ""
    llm_key_doubao: str = ""
    llm_key_qwen: str = ""

    # 图片存储（图生文）：物理落盘根目录 + 对外/DB 引用 URL 前缀。均可由 .env 覆盖（不锁死）。
    # 发送时转 base64 内联，云端模型不真的拉图——base_url 仅作引用。
    storage_root_dir: Path = Path("D:/acgagent-ai/uploads")
    storage_base_url: str = "http://localhost:8100/uploads"

    model_config = {
        "env_prefix": "ACG_AI_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        # 未知 ACG_AI_* 变量启动即 ValidationError（fail loud，Rule 12）。
        # ACG_AI_LLM_KEY_<PROVIDER> 已声明为上面的字段，不会被当作 extra。
        "extra": "forbid",
    }

    def llm_key_for(self, provider: str) -> str:
        """按 provider 名取对话 LLM 密钥（对应 ACG_AI_LLM_KEY_<PROVIDER>）。

        未知 provider（无对应字段）返回 ""，由 resolve_api_key 判定"未配置"并抛错。
        """
        key = getattr(self, f"llm_key_{provider.lower()}", "")
        # 防御属性碰撞（A1）：provider 名若等于某已存在属性的后缀（如方法名 'for'），
        # getattr 会返回该属性/方法（truthy）而非 ""，会被 resolve_api_key 误当 key。
        return key if isinstance(key, str) else ""


settings = Settings()
