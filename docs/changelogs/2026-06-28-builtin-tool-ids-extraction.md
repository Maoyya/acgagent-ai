# 提取 BUILTIN_TOOL_IDS 常量 + chat_service._get_tools 去重

> 日期：2026-06-28 | 类型：refactor + fix | 关联代码：`app/tools/__init__.py`、`app/services/chat_service.py`、`app/tools/base.py`
> 承接：Agent 可用性验证实施计划 Task 1（后续 task 将消费 `BUILTIN_TOOL_IDS`）

---

## 1. 背景

内置工具（calculator / web_search / knowledge_search）的 `id→类` 映射此前硬编码在 `chat_service._get_tools` 的 switch 中。即将到来的「Agent 可用性校验」需要同一份清单判断「合法 tool_id」，若两边各硬编码一份将违反 Rule 7（冲突处理）。本 task 把映射提到 `app/tools/__init__.py` 作为单一真相源，`_get_tools` 改为查映射，**对话行为不变**。

落地中发现一处**既有 latent bug**：

- `app/tools/base.py::to_langchain_tool` 生成的 `_tool_func` 无 docstring，新版 langchain-core 要求 `@tool` 函数必须有 docstring 或显式 description，否则 `ValueError`。原 `_get_tools` 也调用该方法，但因无测试覆盖到 LangChain 转换路径而长期未暴露。本 task 顺带加 1 行 docstring 修复（最小改动）。

---

## 2. 改动

| 文件 | 改动 |
| --- | --- |
| `app/tools/__init__.py` | 由空文件改为内置工具注册中心：`BUILTIN_TOOLS: dict[str, type]` 与 `BUILTIN_TOOL_IDS: set[str]`（单一真相源） |
| `app/services/chat_service.py` | `_get_tools` 由 switch 改为查 `BUILTIN_TOOLS` 映射；knowledge_search 仍需 KB 才实例化；自定义/未知 ID 仍忽略（行为不变） |
| `app/tools/base.py` | `to_langchain_tool` 的 `_tool_func` 补 docstring（修既有 latent bug，使 `@tool` 转换不再抛 ValueError） |
| `tests/test_chat_service_tools.py` | **新建**：锁定 `BUILTIN_TOOL_IDS` 三 ID、`_get_tools` 行为与旧版一致（含 KB 依赖、忽略未知/自定义 ID） |

---

## 3. 设计决定

- **映射而非清单**：`BUILTIN_TOOLS`（id→类）同时支撑「校验合法 id」与「实例化」两种用途；`BUILTIN_TOOL_IDS = set(BUILTIN_TOOLS.keys())` 派生自映射，避免两份清单再次分叉（Rule 7）。
- **自定义工具不进映射**：用户 API 工具存于 `app/db/tool_store.py`，`_get_tools` 当前不消费它，仅由 agent 可用性校验保证存在性（YAGNI）。
- **顺带修 base.py docstring**：brief 的成功标准（4 tests PASS）依赖 `to_langchain_tool()` 可用，该 bug 在 pristine master 上即存在，1 行修复即可解锁；不修复则后续 Agent 校验的端到端测试同样无法跑通。

---

## 4. 验证

- TDD：先 RED（`ImportError: cannot import name 'BUILTIN_TOOL_IDS'`）→ 实现 → GREEN（4/4 passed）。
- 全量 `pytest`：**102 passed**，无回归、无 warning。
- 已确认 `to_langchain_tool()` ValueError 在 stash 后的 pristine 代码上同样复现，证明非本 task 引入。

---

## 5. 范围（未做）

- Agent 创建/更新时的 `tool_ids` 引用校验（Task 3 `_validate_references`）尚未接入，`BUILTIN_TOOL_IDS` 当前仅 `_get_tools` 与测试消费。
- 自定义工具的实例化路径未触碰（沿用既有行为）。
