# 对话 LLM api_key 环境变量解析（方案 B）

> 日期：2026-06-27 | 类型：feature | 关联代码：`app/core/llm.py`

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
| `tests/test_llm.py` | **新增** 5 个测试（TDD：先 RED `ImportError`，后 GREEN） |
| `scripts/seed.py` | 旧名 `DEEPSEEK_API_KEY` → agent `api_key` 留空，运行时走 `ACG_AI_LLM_KEY_DEEPSEEK` |
| `docx/local-startup-guide.md` | 第 4 节补多 provider key 说明（ini 示例 + 表格行） |
| `.env` | 补 4 个 `ACG_AI_LLM_KEY_<PROVIDER>` 占位 + 注释（gitignore，不入库） |

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

- 新测试 5/5 通过（覆盖优先 / env 回退 / 两处皆空抛错 / 大小写 / `create_chat_model` 接线）；
- 全量 `pytest`：**93 passed**（88 原有 + 5 新增），无回归、无 warning；
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
