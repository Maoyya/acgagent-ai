"""
启动期默认 API Key 告警的单元测试。
"""
import logging

from app import main
from app.config import settings


def test_warn_default_key_logs_when_default(caplog, monkeypatch):
    """api_key 仍为默认值时，打印 WARNING。"""
    monkeypatch.setattr(settings, "api_key", "dev-api-key")
    caplog.set_level(logging.WARNING)
    main._warn_default_api_key()
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


def test_warn_default_key_silent_when_real(caplog, monkeypatch):
    """api_key 已改为真实值时，不打印 WARNING。"""
    monkeypatch.setattr(settings, "api_key", "some-real-key-xyz")
    caplog.set_level(logging.WARNING)
    main._warn_default_api_key()
    assert not [rec for rec in caplog.records if rec.levelno == logging.WARNING]
