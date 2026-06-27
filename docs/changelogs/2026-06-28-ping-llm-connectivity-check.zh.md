# 新增 ping_llm 连通性校验函数

> 日期：2026-06-28 | 类型：feat | 关联代码：`app/core/llm.py`、`tests/test_llm.py`
> 承接：Agent 可用性验证实施计划 Task 2（后续 Task 4 `agent_service` 将 `from app.core.llm import ping_llm` 消费）

---

## 1. 背景

Agent 创建/更新时需要验证「配置的 LLM 真的能跑通」（key 有效 + base_url 可达 + model 名正确）。当前 `create_chat_model` 只构造实例、不做连通性探测，且其 `streaming=True`、无超时，不适合做一次性探活。

本 task 新增 `ping_llm(config, timeout)`：发一次 `max_tokens=1`、非流式的最小 completion，成功即返回；失败按 `openai` 异常类型翻译成**中文、可操作**的 `ValueError`（告诉用户该检查哪个字段）。

---

## 2. 方案

```
ping_llm(config, timeout=15.0) -> None
  api_key = resolve_api_key(...)         # 复用方案 B 的 key 解析；缺失抛 ValueError（原样传播）
  model = ChatOpenAI(max_tokens=1, temperature=0, streaming=False, timeout=...)  # 独立实例，不复用对话模型
  try: model.invoke([HumanMessage("ping")])
  except openai.AuthenticationError → ValueError("鉴权失败…检查 api_key / ACG_AI_LLM_KEY_<PROVIDER>")
  except openai.NotFoundError         → ValueError("模型 '<name>' 不存在…检查 model")
  except openai.RateLimitError        → return  # 已证明可达，视为可用
  except openai.APIConnectionError    → ValueError("无法连接 base_url（或超时）…检查 base_url")  # 含 APITimeoutError
  except Exception as e               → ValueError("LLM 校验失败: <e>")  # Fail Loud，不静默放行
```

- **RateLimitError 视为可用**：能触发限流说明 key/base_url/model 都对，已成功触达 provider。
- **APITimeoutError 归入连接错误**：它是 `APIConnectionError` 的子类，单 except 覆盖。

---

## 3. 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/core/llm.py` | 顶部 import 块新增 `import openai`、`from langchain_core.messages import HumanMessage`；末尾新增 `ping_llm(config, timeout=15.0) -> None` 函数 |
| `tests/test_llm.py` | 新增 `ping_llm` 测试组（7 用例）：成功 / 鉴权失败 / 模型未找到 / 连接错误 / 限流视为可用 / 未知异常包装 / key 缺失原样传播 |

---

## 4. 设计决定

| 决定 | 理由 |
| --- | --- |
| 独立构造 `ChatOpenAI`，不复用 `create_chat_model` | 后者为对话用（streaming=True、无超时）；探活要的是非流式、`max_tokens=1`、显式 timeout，目标不同（Rule 2）。 |
| 异常分支按 `openai.*` 类型翻译 | 给出「该检查哪个字段」的可操作中文提示，便于前端/用户定位；未知异常仍包装成 `ValueError` 不静默放行（Rule 12 Fail Loud）。 |
| `RateLimitError` 直接 return | 已证明可联通，把限流当不可用会让用户误判配置错。 |
| `resolve_api_key` 的 `ValueError` 原样传播 | key 缺失与连通性失败是两类问题，提示信息已足够明确（含环境变量名），不应被通用 `except Exception` 吞成「LLM 校验失败」。 |
| import 提到文件顶部（偏离 brief 的「末尾追加」字面位置） | brief 原文写「追加 import 与函数」，但 `app/core/` 全部模块均把 import 放顶部（Rule 11 一致性 / Rule 7 不混模式）。code-review 阶段发现后把 `import openai` / `HumanMessage` 上移并入既有 import 块；brief 的「末尾追加」意图是「和函数一起加」，不排斥放顶部。 |

---

## 5. 验证

- TDD：先 RED（`ImportError: cannot import name 'ping_llm' from app.core.llm`）→ 实现 → GREEN（7/7 passed）。
- 全量 `pytest`：**109 passed**，无回归、无 warning。

### 运行时签名调整（forced adjustment）

brief 的测试用例 `test_ping_llm_translates_connection_error` 原样照抄时，`openai.APIConnectionError(message="conn")` 在 `openai==2.38.0` 抛 `TypeError: missing 1 required keyword-only argument: 'request'`（`request: httpx.Request` 为必填）。

- 调整范围：**仅测试夹具**，给该异常补 `request=_http_resp(500).request`（复用文件内已有的 `_http_resp` helper 构造 `httpx.Request`）。
- **未改 `ping_llm` 实现**：其 `except openai.APIConnectionError` 分支结构保持 brief 原样（符合「异常分支结构必须保持」的约束）。

---

## 6. 范围（未做）

- `ping_llm` 尚未被任何业务路径调用；Task 4 的 `agent_service` 将在 Agent create/update 时消费它。
- 未覆盖 `openai` 其它具体异常（如 `PermissionDeniedError`、`UnprocessableEntityError`）——它们会落到通用 `except Exception` 分支，仍以 `ValueError` 上报，符合 Fail Loud。
