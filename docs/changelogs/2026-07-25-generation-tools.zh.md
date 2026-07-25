# 媒体生成 Agent 工具注册 + env 模板补全

> 日期：2026-07-25 | 类型：feat（工具注册 + 配置模板）| 关联 spec：`docs/superpowers/specs/2026-07-25-generation-tools-design.md` | 关联 plan：`docs/superpowers/plans/2026-07-25-generation-tools.md`

---

## 1. 背景

文生图 / 图生视频能力已于 2026-07-11 以独立 REST API 落地（`POST /api/v1/generations/images|videos` + 任务轮询 `GET /api/v1/generations/tasks/{task_id}`，dashscope 通义万相 `wanx2.1-t2i-turbo` / `wan2.1-i2v-turbo`），但**未注册为 Agent 内置工具**——LLM 在对话中无法自主决定调用生成；且 `.env.example` / `.env` 均缺 `ACG_AI_GENERATION_*`，部署后不配 key 则提交返 500。

本次：将两项能力注册为内置工具（方案 A：元数据注册），补全 env 模板，顺带补齐 `tool_service` 既有遗漏的 `knowledge_entry_lookup` 元数据。

## 2. 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/tools/image_generation.py`（新） | `ImageGenerationTool`：execute 复用 `generation_service`，只 submit 返 task_id + 轮询引导；`asyncio.run` 桥接 sync→async |
| `app/tools/video_generation.py`（新） | `VideoGenerationTool`：同上，必填公网 `image_url` |
| `app/tools/__init__.py` | `BUILTIN_TOOLS` +2 映射 |
| `app/services/tool_service.py` | `_builtin_ids` +3、`_get_builtins` +3 `ToolVO`（含补齐 `knowledge_entry_lookup`） |
| `.env.example` / `.env` | 各补 4 项 `ACG_AI_GENERATION_*`（`API_KEY` 留空，其余默认值；`.env` gitignored） |
| `tests/test_image_generation_tool.py`（新） | 4 测试：成功 / 缺 prompt / 失败透传 / 缺 task_id fail-loud |
| `tests/test_video_generation_tool.py`（新） | 5 测试：成功 / 缺 prompt / 缺 image_url / 失败透传 / 缺 task_id fail-loud |
| `tests/test_generation_tool_registration.py`（新） | 3 测试：BUILTIN_TOOLS 含新工具 / list_all 含三者 / 参数 required schema |
| `tests/test_chat_service_tools.py` | L22 期望集合 4→6（Task 3 扩展 BUILTIN_TOOLS 的连带回归更新） |

## 3. 设计要点

- **方案 A（元数据注册）**：本项目工具执行回路是「前端编排」——后端把 LLM 的 `tool_call` 作 SSE 事件转给前端（`chat_service.py:98-102`），Python 侧不执行工具。故「注册成 tool」=让 LLM 能决策调用 + 工具列表 API 能展示；`execute()` 作工具能力实现 + 可独立测试 + 备未来后端直连。
- **execute 只 submit、不轮询至完成**：复杂轮询当前为死代码，留二期。
- **asyncio.run 桥接 sync→async**：当前 chat 流程不调 execute，故「已有 loop」限制不触发；未来接入 async 执行回路需改为直接 await（模块 docstring 已注明）。
- **task_id None-guard**：`Result.data` 为 `Optional[T]`，用 `(result.data or {}).get("task_id")` + fail-loud 中文提示，消除 Pyright `reportOptionalSubscript` 并防御服务异常路径。
- **补齐 knowledge_entry_lookup 元数据**：消除「BUILTIN_TOOLS 有 4 项 / tool_service 只列 3 项」的既有不一致，零行为变更。

## 4. 验证

- 全量 `pytest -q` → **223 passed**，无回归（基线含媒体生成 REST API 既有测试）。
- Pyright `reportOptionalSubscript ✘` 已消除；`★` hint（`kwargs` / `user_id` / `req` 未使用，mock 签名既有模式）保留不阻断。

## 5. 范围（未做 / 二期）

- 未改 `chat_service` 工具执行回路——真正「对话内生成」需二期接入后端工具执行回路（届时 `execute` 的 `asyncio.run` 限制需重新评估）。
- execute 仅 submit，前端仍需自行轮询 REST API 取资产。
- `app/docx/` 业务文档未更新。
