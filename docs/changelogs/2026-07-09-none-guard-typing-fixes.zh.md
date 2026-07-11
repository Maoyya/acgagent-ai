# 三处 None 边界类型警告修复（chromadb Optional + UploadFile.filename）

> 日期：2026-07-09 | 类型：fix（健壮性 / 类型安全）| 关联代码：`app/db/memory_store.py`、`app/db/preference_store.py`、`app/api/v1/document.py`

---

## 1. 背景

Pyright 在三处报 `Optional` 类型不匹配，均为边界 None 未处理：

| 位置 | 警告 |
| --- | --- |
| `memory_store.py` `load_history` | `zip(result["documents"], result["metadatas"])`：chromadb `get()` 返回的 documents/metadatas 类型为 `List | None` |
| `preference_store.py` `list_by_user` | 同上，`zip(res["documents"], res["metadatas"])` |
| `api/v1/document.py` `upload_document` | `file.filename: str | None` 传给 `upload_document(file_name: str)` |

---

## 2. 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/db/memory_store.py` | `zip(result["documents"], result["metadatas"])` → `zip(result["documents"] or [], result["metadatas"] or [])` |
| `app/db/preference_store.py` | 同上，`res["documents"]` / `res["metadatas"]` 各加 `or []` |
| `app/api/v1/document.py` | 新增 `if file.filename is None: return Result.error(code=400, ...)` 边界拒绝；其后 `file.filename` 类型收窄为 `str` |

---

## 3. 设计决定

| 决定 | 理由 | 备选（为何不选） |
| --- | --- | --- |
| chromadb 两处用 `or []` | 上游已有 `count==0 → return []` 守卫，None 属 Pyright 对 chromadb 返回的保守标注、非上游 bug 信号；`or []` 正常路径被短路、行为不变，None 边界返回空与既有契约一致 | `# type: ignore`：掩盖类型且不防御真实 None |
| `file.filename is None` → 400 拒绝 | 无 filename 几乎必为客户端异常输入，应 fail-loud 明确拒绝 | 见下一行 |
| ~~`file.filename or "upload"`~~（初版，**被 review 否决**） | — | 默认名无扩展名，`document_service._read_file` 按 `path.suffix` 分派会命中 else 抛 `Unsupported file type`，导致上传返回 200 但异步任务必失败、`status`→`failed`、错误不可读；比改前传 `None` 在 `DocumentVO(file_name=None)` 快失败更隐蔽。若要兜底也应以 `content_type` 推断扩展名，但 MIME 映射维护成本高且 content_type 亦可能缺失 |

---

## 4. 验证

- `pytest -q` → **149 passed**，无回归。
- 三处 Pyright `Optional` 警告：`or []` 与 `is None` 类型收窄后消除。
- **覆盖缺口（如实记录）**：`upload_document` 的 `filename=None → 400` 分支未补单测（需 mock `UploadFile(filename=None)`）；chromadb 两处 None 路径依赖真实 chromadb 返回，单测难复现。后续按需补集成测试。

---

## 5. 范围（未做）

- 未新增针对 400 分支与 chromadb None 路径的单测（见 §4 覆盖缺口）。
- 仅修这三处既有警告；项目其它潜在 Pyright 警告未做全量扫查。
