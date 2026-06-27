"""image_service 测试 —— 图生文存储与编码的唯一真相源。

锁定意图（Rule 9）：
- save_upload 只接受 image/* 并落盘，返回 base_url+filename 的 url；
- to_data_urls 真实读盘转 base64；文件缺失 Fail Loud；
- build_message_content 无图=纯字符串（零回归），有图=多模态 list。
"""
import base64

import pytest

from app.services import image_service
from app.services.image_service import MAX_IMAGE_BYTES, ImageRef


PNG = b"\x89PNG\r\n\x1a\n"


def test_save_upload_writes_file_and_returns_url(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")

    ref = image_service.save_upload("cat.png", PNG, "image/png")

    assert isinstance(ref, ImageRef)
    assert ref.url == f"http://x/up/{ref.filename}"
    assert ref.filename.endswith(".png")
    assert (tmp_path / ref.filename).read_bytes() == PNG


def test_save_upload_rejects_non_image(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    with pytest.raises(ValueError):
        image_service.save_upload("a.txt", b"hello", "text/plain")


def test_save_upload_rejects_oversize(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    with pytest.raises(ValueError):
        image_service.save_upload("big.png", b"x" * (MAX_IMAGE_BYTES + 1), "image/png")


def test_to_data_urls_encodes_file_as_data_url(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", PNG, "image/png")

    [du] = image_service.to_data_urls([ref.url])

    assert du.startswith("data:image/png;base64,")
    assert base64.b64decode(du.split("base64,", 1)[1]) == PNG


def test_to_data_urls_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    with pytest.raises(FileNotFoundError):
        image_service.to_data_urls(["http://x/up/nope.png"])


def test_build_message_content_no_images_returns_plain_string():
    assert image_service.build_message_content("hi", None) == "hi"
    assert image_service.build_message_content("hi", []) == "hi"


def test_build_message_content_with_images_returns_multimodal_list(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", PNG, "image/png")

    content = image_service.build_message_content("describe", [ref.url])

    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
