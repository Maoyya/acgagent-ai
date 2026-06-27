# 对话 LLM api_key 解析重构（方案 C：密钥集中到 Settings 字段）

> 日期：2026-06-27 | 类型：refactor + fix | 关联代码：`app/config.py`、`app/core/llm.py`、`app/api/v1/chat.py`
> 承接：方案 B（已提交）——本次为同根因的彻底重构 + code-review 修复

---

## 1. 背景

方案 B 让对话 LLM 密钥按 provider 从 `ACG_AI_LLM_KEY_<PROVIDER>` 解析。落地后发现**根因问题**：

- pydantic-settings 把 `.env` 读进 `Settings` 对象，**但不写入 `os.environ`**；方案 B 用 `os.getenv` 取 key 永远拿不到 `.env` 里的值（只对真实进程环境变量有效）。
- 曾临时 `load_dotenv()` 桥接 os.environ，并放宽 `extra="ignore"`——后者违反 Rule 12 fail-loud（拼错的 `ACG_AI_*` 被静默吞掉）。

code-review（8 角度召回）另发现：

- **C1/C2**：`resolve_api_key` 抛的 `ValueError` 在 sync 路径裸奔成无信封 500、在 stream 路径于 async generator 中途崩溃。
- **C3**：`if explicit:` 把空白 key 当真值。
- **A1**：`llm_key_for` 用 `getattr(self, f"llm_key_{provider.lower()}", "")`，provider 名碰巧等于已存在属性后缀（如方法名 `for`）时返回方法对象（truthy），当 api_key 用，绕过 fail-loud。
- **B4**：未声明 provider 的错误消息引导去设一个会被 `extra=forbid` 拒绝的变量（绕圈）。

---

## 2. 改动

| 文件 | 改动 |
| --- | --- |
| `app/config.py` | 4 个 provider 密钥改为**已声明 Settings 字段** `llm_key_<provider>`；新增 `llm_key_for(provider)`（带 `isinstance` 防属性碰撞 A1）；`extra` **回退 `forbid`**（恢复 fail-loud）；移除 `load_dotenv` 桥接 |
| `app/core/llm.py` | `resolve_api_key` 改读 `settings.llm_key_for(provider)`（不再 `os.getenv`）；`explicit` 改 `.strip()` 判空（C3）；错误消息加"需声明字段"说明（B4，不绕圈）；移除 `import os` |
| `app/api/v1/chat.py` | 分流前**预检** `resolve_api_key`，缺 key → `Result.error(500)`，覆盖 sync/stream/workflow 三路径（C1/C2） |
| `tests/test_llm.py` | 重写为 Settings 机制；新增根因测试（原生读 .env）、fail-loud 测试（extra=forbid）、防碰撞测试（A1） |
| `tests/test_chat.py` | 新增 C1/C2 测试（缺 key 返回 500 信封）；流式半补 `content-type=application/json` 断言锁定 C2 意图（B6） |
| `.env.example` | **新增**可入库模板（占位符/默认值，注释独占行避免泄漏） |
| `docx/local-startup-guide.md` | 补多 provider key 配置说明 + 行内注释坑提醒 |
| `docs/superpowers/plans/2026-06-27-llm-apikey-env-resolution.zh.md` | 标注已被方案 C 取代，指向本记录 |

---

## 3. 设计决定

- **Settings 字段而非 os.getenv**：pydantic-settings 原生从 `.env` 读声明字段，彻底消除".env 不进 os.environ"根因，无需 `load_dotenv` 桥接。
- **`extra="forbid"`**：未知 `ACG_AI_*` 启动即 `ValidationError`，恢复 Rule 12 fail-loud（LLM key 已是声明字段，不会被当 extra）。
- **预检放在 `chat.py` 分流前**：流式约束下，进入 async generator 后的 `ValueError` 无法回写已发出的 200 信封，必须在分流前拦下——正确深度，非 band-aid。

---

## 4. 验证

- 全量 `pytest`：**98 passed**，无回归、无 warning。
- 新增/重写测试均 TDD（先 RED 后 GREEN）：A1 / 根因 / fail-loud / C1·C2 各有用例。

---

## 5. 迁移 / 注意

- **运维**：`cp .env.example .env` 后填 `ACG_AI_LLM_KEY_<PROVIDER>`；新增 provider 需在 `Settings` 声明对应 `llm_key_<provider>` 字段。
- **⚠️ `extra="forbid"` 含义**：`.env` 里任何拼错的 `ACG_AI_*`（如 `ACG_AI_APIKEY`）会**启动即崩溃**——这是有意的 fail-loud，配置时请对照 `.env.example` 的字段名。
- 向后兼容：agent 自带非空 `api_key` 仍优先（opt-in 集中化）。

---

## 6. 范围（未做）

- embedding / 知识库密钥同模式未扩展；
- latent：`monkeypatch.setattr(settings,...)` 在 pytest-xdist 并发下不安全（当前无 xdist 配置，不触发）。
