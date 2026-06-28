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


def test_to_data_urls_rejects_traversal_url(tmp_path, monkeypatch):
    """反斜杠路径穿越攻击（Windows）必须被 _stored_path_for 拦下。

    为什么重要：basename 旧实现 url.rsplit('/',1)[-1] 不处理反斜杠，攻击者用
    `http://x/..\\..\\secret` 可越出 storage_root_dir 读任意文件并内联给视觉模型。
    断言 ValueError 且绝不读取目录外文件（Fail Loud）。
    """
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    # 在 tmp_path 内放一个真文件，确保即便解析穿越也能区分"读到了"vs"被拦下"
    (tmp_path / "legit.png").write_bytes(PNG)
    traversal_url = r"http://x/..\..\secret"
    with pytest.raises(ValueError):
        image_service.to_data_urls([traversal_url])


def test_to_data_urls_strips_query_string(tmp_path, monkeypatch):
    """url 带 query string 时应剥离，按基础名读盘并返回有效 data URL。

    为什么重要：客户端引用常带 ?w=100 等缩略参数，旧实现把 query 当文件名一部分，
    导致 FileNotFoundError。_stored_path_for 经 urlparse 仅取 path 段，正确读盘。
    """
    monkeypatch.setattr(image_service.settings, "storage_root_dir", tmp_path)
    monkeypatch.setattr(image_service.settings, "storage_base_url", "http://x/up")
    ref = image_service.save_upload("cat.png", PNG, "image/png")

    [du] = image_service.to_data_urls([ref.url + "?w=100"])

    assert du.startswith("data:image/png;base64,")
    assert base64.b64decode(du.split("base64,", 1)[1]) == PNG


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
