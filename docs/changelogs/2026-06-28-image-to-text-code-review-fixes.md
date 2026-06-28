# 图生文链路 code-review 修复（路径穿越 / 上传 DoS / 错误信封）

> 日期：2026-06-28 | 类型：fix（安全 + 健壮性）| 关联代码：`app/services/image_service.py`、`app/api/v1/chat.py`、`app/services/chat_service.py`
> 承接：图生文功能已提交代码的 /code-review 4 项发现

---

## 1. 背景

图生文链路（图片上传 → url 引用 → base64 内联给视觉模型）落地后，/code-review 发现 4 项问题：

- **Fix A（CRITICAL）**：`to_data_urls` 用 `url.rsplit('/', 1)[-1]` 取 basename，**不处理反斜杠**。Windows 上客户端可控的 `images` URL 如 `http://x/..\..\Windows\win.ini` 会让 `root / name` 解析到 `storage_root_dir` 之外，**任意文件读取并 base64 内联给视觉模型**（已在 win32 验证）。
- **Fix B（IMPORTANT）**：`upload_image` 先 `await file.read()` 把整个上传缓冲进内存，**再**做大小校验——超大请求即可 DoS 内存。
- **Fix C（IMPORTANT）**：`save_upload` 的 `write_bytes` 可能抛 `OSError`（盘满/权限），旧实现未捕获 → 裸奔成无信封 500。Folded into Fix B。
- **Fix D（IMPORTANT）**：`_build_messages(...)` 在 `_stream_plain` / `_stream_with_tools` / `sync_chat` 的 `try:` **之外**调用，图解析错误（Fix A 的 `FileNotFoundError`/`ValueError`）会逃逸成裸 500 或 SSE 中途崩溃，而非受控错误。

---

## 2. 改动

| 文件 | 改动 |
| --- | --- |
| `app/services/image_service.py` | 新增 `_stored_path_for(url)`：`urlparse` 取 path 段（去 query/fragment），basename 含反斜杠/`/`/`..`/`.` 即视为穿越企图 → `ValueError`（Fail Loud，不静默归一化）；`resolve` 后必须仍在 `storage_root_dir` 内（兜底）；`to_data_urls` 改用之 |
| `app/api/v1/chat.py` | `upload_image` 改为 **1MB 分块读取 + running cap**，累计超限提前 400（内存有界）；捕获 `OSError` → `Result.error(500)`；sync 分支 `chat_completions` 包 `try/except` → `Result.error(500)`，避免 `_build_messages` 失败裸奔（stream 分支不动，错误已由服务内 SSE error-event 路径处理） |
| `app/services/chat_service.py` | `_stream_plain` / `_stream_with_tools` / `sync_chat` 的 `messages = self._build_messages(...)` 移入各自既有 `try:`，图解析错误路由到既有 `except → error SSE`（流式）或 re-raise（sync，由 chat.py 信封化） |
| `tests/test_image_service.py` | 新增 `test_to_data_urls_rejects_traversal_url`（反斜杠穿越 → ValueError）、`test_to_data_urls_strips_query_string`（`?w=100` 剥离后正常读盘） |
| `tests/test_chat.py` | 新增 `test_upload_rejects_oversize_via_streaming`（分块超限 → 400）、`test_upload_returns_500_on_storage_error`（OSError → 500 信封）、`test_chat_sync_missing_image_returns_500_envelope`（sync 缺图 → 500 信封，锁定 Fix D 意图） |

---

## 3. 设计决定

- **拒绝而非归一化穿越输入**：spec 给的 snippet 会把 `..\..\secret` 静默归一化成 `secret`（虽安全但吞掉攻击信号）。改为对含分隔符/`..` 的 basename 直接 `ValueError`——合法落盘名（`uuid.hex + 扩展名`）永不会带这些字符，带即是攻击，符合 Rule 12 fail-loud。
- **分块读取深度**：在 `upload_image` 而非 `save_upload` 做流式 cap——`save_upload` 仍保留 `len(content) > MAX_IMAGE_BYTES` 校验作为 defense-in-depth（chunked 路径已先拦，但 `save_upload` 也可被其他调用方直接命中）。
- **sync 信封化在 `chat.py`**：`sync_chat` 内部 `try` 仍 re-raise（保持服务层纯度），由路由层包成 `Result.error(500)`，与既有 `resolve_api_key` 预检信封化风格一致。stream 分支不改——SSE 已发 200 头，错误只能走 async generator 内的 error-event。

---

## 4. 验证

- 定向：`pytest tests/test_image_service.py tests/test_chat.py tests/test_chat_service_images.py -v` → **23 passed**（18 原有 + 5 新增）。
- 全量：`pytest -q` → **138 passed**，无回归、无 warning。
- 5 个新测试均 TDD（先确认 RED 意图再 GREEN）。
- 自检：穿越确实被拦（ValueError，不读目录外文件）；分块读取内存有界（1MB chunk + running cap）；既有测试全绿；图错误无裸 500 残留路径。

---

## 5. 范围（未做）

- workflow / RAG 路径本轮不支持图（spec §7），未改动。
- 未对 `storage_root_dir` 本身做符号链接审计（`resolve()` 已消解 symlink，且目录由运维控制）。
