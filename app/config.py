"""
应用配置。

使用 pydantic-settings 从环境变量或 .env 文件加载配置。
所有环境变量前缀为 ACG_AI_（如 ACG_AI_PORT → port）。

取值规则（每个字段通用）：代码里的 "= 默认值" 仅在 .env / 环境变量未设置对应项时生效；
设置 ACG_AI_<字段名大写>（如 storage_root_dir → ACG_AI_STORAGE_ROOT_DIR）即覆盖默认值。
未声明的 ACG_AI_* 变量会触发 ValidationError（下方 model_config extra="forbid"，防拼错）。
"""
import json
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


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

    # moderator 专用 extra_body（JSON）：按 provider 关 thinking 等。
    # deepseek-v4-pro 等 thinking 模型与 function_calling 的 tool_choice=required 冲突，
    # 需在此关思考（如 {"thinking":{"type":"disabled"}}）。仅 _build_mod_llm 消费。
    meta_llm_mod_extra_body: dict = Field(default_factory=dict)

    @field_validator("meta_llm_mod_extra_body", mode="before")
    @classmethod
    def _parse_mod_extra_body(cls, v):
        """env 里是 JSON 字符串 → dict；空串→{}；非法 JSON→启动即 ValidationError（Rule 12 fail-loud）。"""
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return {}
            try:
                return json.loads(s)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"ACG_AI_META_LLM_MOD_EXTRA_BODY 不是合法 JSON: {e}"
                ) from e
        return v

    # 外部模型 API 密钥（按 provider 分键）：对话/Agent LLM 由 app/core/llm.py 的 resolve_api_key 消费，
    # RAG embedding 由 app/core/embeddings.py 的 resolve_embedding_key 消费——同一 provider 的 chat 与
    # embedding 共用此 key（智谱/dashscope/火山/openai 均如此）。
    # 对应环境变量 ACG_AI_LLM_KEY_<PROVIDER 大写>。新增 provider 需在此声明字段（fail-loud，防拼错）。
    llm_key_deepseek: str = ""
    llm_key_zhipu: str = ""
    llm_key_doubao: str = ""
    llm_key_qwen: str = ""

    # 图片存储（图生文）：物理落盘根目录 + 对外/DB 引用 URL 前缀。均可由 .env 覆盖（不锁死）。
    # 发送时转 base64 内联，云端模型不真的拉图——base_url 仅作引用。
    storage_root_dir: Path = Path("D:/acgagent-ai/uploads")   # env: ACG_AI_STORAGE_ROOT_DIR
    storage_base_url: str = "http://localhost:8100/uploads"   # env: ACG_AI_STORAGE_BASE_URL

    # 媒体生成（dashscope 通义万相）：文生图 + 图生视频，异步任务。
    # 各字段均可由 .env 覆盖（前缀 ACG_AI_GENERATION_*，字段名大写）。
    generation_api_key: str = ""   # env: ACG_AI_GENERATION_API_KEY；dashscope key，缺失 → 提交/查询返回 500
    generation_base_url: str = "https://dashscope.aliyuncs.com/api/v1"   # env: ACG_AI_GENERATION_BASE_URL
    generation_image_model: str = "wanx2.1-t2i-turbo"   # env: ACG_AI_GENERATION_IMAGE_MODEL
    generation_video_model: str = "wan2.1-i2v-turbo"   # env: ACG_AI_GENERATION_VIDEO_MODEL

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
