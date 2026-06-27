# 对话 LLM api_key 环境变量解析（方案 B）

> 日期：2026-06-27 | 类型：feature | 关联代码：`app/core/llm.py`
> ⚠️ **已被同日"方案 C"取代**：LLM 密钥改为已声明 Settings 字段（不再 `os.getenv`）、`extra` 回退 `forbid`、移除 `load_dotenv`，并新增 C1/C2/A1/B4 修复。下文 §2–§8 为方案 B 的历史记录，最终状态见 §9 与 `docs/changelogs/2026-06-27-llm-apikey-env-resolution.md`。

---

## 1. 背景

此前每个 Agent 的 `llm_config.api_key` 直接明文存于 `data/agents/*.json`（如 `"api_key": "sk-test"`）。问题：

- N 个 Agent 各存一份密钥，轮换需改 N 个文件；
- 明文 JSON（`data/` 虽被 gitignore，但备份/迁移会带走）；
- 与 meta-LLM 的 `ACG_AI_META_LLM_API_KEY` 重复管理。

meta-LLM 走 `.env`，对话/Agent LLM 却散落在 JSON——密钥应集中、配置应分散。

---

## 2. 方案（B：按 provider 分键）

保留 per-agent 的 `provider/model/base_url/temperature/...`（**不丢多模型多 Agent 能力**），仅把 `api_key` 改为"agent 自带非空 → 用自带；为空 → 按 provider 从 env 取"。

**解析优先级**：

```
explicit（agent 配置 api_key）非空 → 用它（覆盖，向后兼容）
        ↓ 为空
env: ACG_AI_LLM_KEY_<PROVIDER 大写>   （DEEPSEEK / ZHIPU / DOUBAO / QWEN …）
        ↓ 也为空
抛 ValueError（fail loud，消息含应设的变量名）
```

---

## 3. 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/core/llm.py` | 新增纯函数 `resolve_api_key(provider, explicit)`；`create_chat_model` 改用它。**签名不变**，3 个调用方（`workflow.py`、`chat_service.py` ×2）零改动 |
| `app/config.py` | `Settings.model_config` 加 `extra="ignore"`——否则用户在 `.env` 填非空 `ACG_AI_LLM_KEY_*` 时启动即 `ValidationError` 崩溃（见 §8） |
| `tests/test_llm.py` | **新增** 6 个测试（5 个 `resolve_api_key` + 1 个 Settings 容忍 LLM key 的 `.env` 文件路径测试，均 TDD） |
| `scripts/seed.py` | 旧名 `DEEPSEEK_API_KEY` → agent `api_key` 留空，运行时走 `ACG_AI_LLM_KEY_DEEPSEEK` |
| `docx/local-startup-guide.md` | 第 4 节补多 provider key 说明 + 行内注释坑提醒（注释独占行） |
| `.env.example` | **新增**可入库的配置模板（仅占位符/默认值）；`cp .env.example .env` 即用 |
| `.env` | 补 4 个 `ACG_AI_LLM_KEY_<PROVIDER>` 占位（gitignore，不入库） |

---

## 4. 设计决定

| 项 | 决定 | 理由 |
| --- | --- | --- |
| env 命名 | `ACG_AI_LLM_KEY_<PROVIDER>` | 沿用项目 `ACG_AI_` 前缀 |
| 优先级 | agent api_key 非空→覆盖；为空→env | 向后兼容，现有 13 个 Agent **零影响、无需迁移** |
| 两处皆空 | 抛 `ValueError`（消息含变量名） | fail loud，提前给可操作提示，而非让 provider 报晦涩 401 |
| 实现形态 | 提取纯函数 `resolve_api_key` | 不依赖构造 ChatOpenAI，易单测 |

---

## 5. 验证

- `resolve_api_key` 5 个用例 + Settings 容忍 LLM key 1 个用例，均 TDD（先 RED 后 GREEN）；
- 全量 `pytest`：**94 passed**（88 原有 + 6 新增），无回归、无 warning；
- `.env.example` 可被 Settings 加载、值无行内注释泄漏；`from app.main import app` 正常；
- 向后兼容：`LLMConfig` 结构未变，`test_agent_config.py` / `test_chat.py` 等不受影响。

---

## 6. 用法

1. `.env` 填 `ACG_AI_LLM_KEY_ZHIPU=sk-...`；
2. 建对话 Agent：`provider="zhipu"`、`base_url=https://open.bigmodel.cn/api/paas/v4/`、`model=glm-4.5`、`api_key` **留空**；
3. 运行时自动取对应 provider 的 key；未填又无 env → 提前抛 `ValueError`。

---

## 7. 范围（本次未做）

- **embedding / 知识库密钥**（`app/models/knowledge_base.py` 同模式）—— 说的"对话/图文"先不扩，留作后续；
- **图文/视觉**：当前无独立 vision pipeline，本质是建一个多模态模型的 Agent，照样走 per-agent 配置 + env 取 key。

---

## 8. 配套修复与踩坑（2026-06-27 补）

落地验证时发现两个必处理的问题：

1. **`Settings` 的 `extra` 原为 `forbid`** → 用户在 `.env` 填入非空 `ACG_AI_LLM_KEY_*`（真实 key）后，启动加载 `Settings()` 即 `ValidationError`，整个应用起不来。**已修**：`app/config.py` 的 `model_config` 加 `extra="ignore"`（这些变量本就由 `os.getenv` 读、不属于 Settings 字段）。注意：该崩溃**只经 `.env` 文件源触发**，经 `os.environ` 源不会——所以测试必须在文件路径上复现（`Settings(_env_file=...)`）。
2. **`.env` 行内注释会泄漏进值**：python-dotenv 不剥离 `KEY=  # 注释`，`# 注释` 会被当成值的一部分。**已规避**：`.env.example` / 指南示例的注释一律独占一行，值行不带行内注释。

---

## 9. 方案 C 演进（2026-06-27，取代上文）

落地 + code-review 后，方案 B 的机制被彻底重构（详见 `docs/changelogs/2026-06-27-llm-apikey-env-resolution.md`）：

1. **密钥改为 Settings 字段**：`llm_key_<provider>` 在 `Settings` 显式声明，`resolve_api_key` 经 `settings.llm_key_for(provider)` 取用——不再 `os.getenv`，消除".env 不进 os.environ"根因（§8.1 的 `load_dotenv` 桥接随之移除）。
2. **`extra` 回退 `forbid`**：恢复 fail-loud（§8.1 的 `extra="ignore"` 被回退）；LLM key 已是声明字段，不再触发启动崩溃。
3. **C1/C2**：`app/api/v1/chat.py` 分流前预检 `resolve_api_key`，缺 key 返回 `Result.error(500)`，覆盖 sync/stream/workflow 三路径。
4. **C3/A1/B4**：`explicit` 改 `.strip()` 判空；`llm_key_for` 加 `isinstance` 防属性碰撞；错误消息加"需声明字段"说明（不绕圈）。
5. 验证：全量 `pytest` **98 passed**。
