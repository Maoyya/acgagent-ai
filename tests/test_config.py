"""
Settings 校验测试。

锁定 meta_llm_mod_extra_body 的 JSON 解析意图：
- 空 → {}（不影响调用）
- 合法 JSON 字符串 → dict
- 非法 JSON → 启动即 ValidationError（Rule 12 fail-loud，不让错误配置静默流到运行时）
"""
import pytest
from pydantic import ValidationError

from app.config import Settings


def _settings(**kw) -> Settings:
    # _env_file=None：测试不读 .env，只验传入值（隔离本地配置）
    return Settings(_env_file=None, **kw)


def test_mod_extra_body_empty_string_becomes_empty_dict():
    s = _settings(meta_llm_mod_extra_body="")
    assert s.meta_llm_mod_extra_body == {}


def test_mod_extra_body_valid_json_parsed_to_dict():
    s = _settings(meta_llm_mod_extra_body='{"thinking":{"type":"disabled"}}')
    assert s.meta_llm_mod_extra_body == {"thinking": {"type": "disabled"}}


def test_mod_extra_body_invalid_json_raises_validation_error():
    # 业务意图：错误的 extra_body 配置必须启动即挂，不能等运行时 500 才暴露
    with pytest.raises(ValidationError):
        _settings(meta_llm_mod_extra_body="not-json{")
