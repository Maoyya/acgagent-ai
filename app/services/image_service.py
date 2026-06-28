"""
图片服务 —— 图生文能力的存储与编码唯一真相源。

- save_upload：校验 mime/大小，落盘到 settings.storage_root_dir，返回 ImageRef(url, filename)。
- to_data_urls：把存储 url 映射回本地文件，读字节转 base64 data URL（发送时内联，spec ①）。
- build_message_content：组装 HumanMessage.content——无图返回纯字符串（零回归），
  有图返回多模态 list（标准 OpenAI image_url 格式）。

云端模型不通过 HTTP 拉图（无法访问本机 URL），base_url 仅作「DB/前端引用」。
mime 由落盘文件名扩展名推断（落盘名保留原扩展名）。
"""
import base64
import uuid
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel

from app.config import settings

# 单张图片大小上限（spec §6：模块常量，本轮不做配置项）。
MAX_IMAGE_BYTES = 10 * 1024 * 1024

_EXT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


class ImageRef(BaseModel):
    url: str          # settings.storage_base_url + "/" + filename，存入对话引用
    filename: str     # 落盘文件名（uuid + 原扩展名）


def _ext_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def _mime_for(filename: str) -> str:
    return _EXT_MIME.get(_ext_of(filename), "image/jpeg")


def save_upload(filename: str, content: bytes, content_type: str) -> ImageRef:
    """保存上传图片到 storage_root_dir，返回引用。

    content_type 不以 image/ 开头、或 content 超过 MAX_IMAGE_BYTES → ValueError（Fail Loud）。
    落盘名 = uuid.hex + 原扩展名（防碰撞、保扩展名以推断 mime）。
    """
    if not content_type or not content_type.startswith("image/"):
        raise ValueError(f"unsupported image content_type: {content_type!r} (must be image/*)")
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError(f"image too large: {len(content)} bytes > {MAX_IMAGE_BYTES}")

    ext = _ext_of(filename) or ".png"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    root = Path(settings.storage_root_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / stored_name).write_bytes(content)
    return ImageRef(url=f"{settings.storage_base_url.rstrip('/')}/{stored_name}", filename=stored_name)


def _stored_path_for(url: str) -> Path:
    """从 url 安全解析 storage_root_dir 内的落盘文件路径。

    - urlparse 取 path 再取最后一段（去掉 query/fragment）。
    - basename 含反斜杠或父目录段（..）即视为路径穿越企图 → ValueError（Fail Loud）。
      不做静默归一化：合法落盘名不会带分隔符或 ..，带即是攻击。
    - resolve 后必须仍在 storage_root_dir 内，否则 ValueError（兜底防线）。
    """
    raw_name = urlparse(url).path.rsplit("/", 1)[-1]
    if "\\" in raw_name or raw_name in ("..", ".") or "/" in raw_name:
        raise ValueError(f"image url escapes storage root: {url!r}")
    root = Path(settings.storage_root_dir).resolve()
    path = (root / raw_name).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"image url escapes storage root: {url!r}")
    return path


def to_data_urls(urls: list[str]) -> list[str]:
    """把存储 url 列表转成 base64 data URL 列表（发送时内联）。

    通过 _stored_path_for 安全定位文件（防穿越/去 query）；文件缺失抛 FileNotFoundError。
    """
    out = []
    for url in urls:
        path = _stored_path_for(url)
        if not path.is_file():
            raise FileNotFoundError(f"image file not found for url: {url}")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        out.append(f"data:{_mime_for(path.name)};base64,{b64}")
    return out


def build_message_content(text: str, image_urls: list[str] | None) -> str | list:
    """组装 HumanMessage.content。

    image_urls 为空 → 返回原 text（零回归，行为与改造前逐字一致）。
    非空 → 返回 [{type:text}, {type:image_url}...]（标准 OpenAI 多模态格式）。
    """
    if not image_urls:
        return text
    data_urls = to_data_urls(image_urls)
    content = [{"type": "text", "text": text}]
    content.extend({"type": "image_url", "image_url": {"url": du}} for du in data_urls)
    return content
