# docx 文档同步代码现状：补 prompt 模块 + 修正路由/配置漂移

> 日期：2026-06-27 | 类型：docs | 关联代码：`docx/technical-architecture.md`、`docx/business-flow.md`

---

## 1. 背景

近期两块能力相继落地，但 `docx/` 下的技术架构与业务流程两篇文档停在 v1.1.0（2026-06-21），未同步：

- **prompt 生成模块**（`/api/v1/prompts/*`，含 `generate`/`moderate`/`estimate`，编排组件 `PromptBuilder`/`Moderator`/`CostEstimator`/`PreferenceStore`，双模式 `PromptMode`）。
- **对话 LLM 密钥按 provider 分键**（`ACG_AI_LLM_KEY_<PROVIDER>`）与 **meta-LLM 配置**（`ACG_AI_META_LLM_*`）。

具体漂移：
- `technical-architecture.md` 的 API 路由表、分层/职责、存储表、环境变量表整体缺 prompt 模块；路由表另遗漏 2 个端点，路径变量名与代码不一致。
- `business-flow.md` 完全没有 prompt 生成流程；角色/异常/配置表未覆盖 meta-LLM 与新密钥机制。

用户要求"全面对齐代码现状"，便于了解项目功能。

---

## 2. 改动清单

| 文件 | 改动 |
| --- | --- |
| `docx/technical-architecture.md` | v1.1.0 → v2.0.0。§1 概述补"系统提示词生成"；§3.1 分层图 + §3.2 职责补 `PromptService`/`PromptBuilder`/`Moderator`/`CostEstimator`/`PreferenceStore`；§4.3 新增 prompt 数据模型表；§7 存储表补 `user_preferences`；§8.2 环境变量表补 `ACG_AI_META_LLM_*` + `ACG_AI_LLM_KEY_<PROVIDER>`；§9 路由表补 `GET /knowledge-bases/{kb_id}`、`GET /knowledge-bases/{kb_id}/documents/{doc_id}`、3 个 `/prompts/*`，并统一路径变量名（`{id}`→`{agent_id}`/`{kb_id}`/`{tool_id}`） |
| `docx/business-flow.md` | v1.1.0 → v2.0.0。§2 角色表补 meta-LLM；§3.6 新增"系统提示词生成流程"（generate 编排图 + 双模式 + moderate + estimate）；§4 异常表补 403/500/偏好写入；§6 配置速查补 meta-LLM + LLM_KEY 分键 |
| `docx/local-startup-guide.md` | **无改动**（v1.2.0 已最新；FAQ 对 `generate`/`moderate` 返回 500 的说明准确，`estimate` 为纯计算不报 500，无需补） |

---

## 3. 设计决定

- **方案 1（一次到位）而非分轮 / 重生成关键表**：两篇规模可控，prompt 是整体缺失而非局部错，融入式补齐比单写更连贯，一次到位避免中间态。
- **不单独写 spec/plan 文件**：本次改动即文档本身、低风险可逆（git），按 CLAUDE.md token 预算（规则 6）与简单优先（规则 2）精简流程，以"改动清单"充当设计与计划。
- **路由表变量名统一**：`{id}` 改为代码实际的 `{agent_id}`/`{kb_id}`/`{tool_id}`，虽不影响路由匹配，但属"全面对齐代码现状"范围。

---

## 4. 验证

- 逐条核对代码事实源：`app/api/v1/*.py`（grep 全部路由装饰器）、`app/config.py`（Settings 全字段）、`app/services/prompt_service.py`（generate 编排链 + 403/500 分支）、`app/db/preference_store.py`（`user_preferences` collection）、`app/models/prompt.py`（模型族）。
- 本次为纯文档变更，无单测；提交前按项目约定跑 `/code-review` 复核 diff。

---

## 5. 范围（未做）

- `local-startup-guide.md` 未改（已最新）。
- 未为 prompt 模块单开专项文档（未选该方案）。
- 现有流程章节（Agent/对话/RAG/工具/健康）仅通读未见明显漂移，**未逐项数字核对**（如 `top_k=5`、12 位 hex ID、分块 500/50 等）；如需可后续专项核对。
- 文档版本号（v2.0.0）与代码内 `app_version=1.0.0`（health 回显）是不同概念，未动后者。
