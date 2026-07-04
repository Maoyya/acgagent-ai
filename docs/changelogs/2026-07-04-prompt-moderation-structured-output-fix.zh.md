# 提示词生成 moderation 结构化输出稳定性修复（function_calling + mode 入参回填）

> 日期：2026-07-04 | 类型：fix（健壮性 / provider 可移植性）| 关联代码：`app/core/moderator.py`、`app/models/prompt.py`
> 承接：提示词生成功能接入阿里云百炼（qwen）专属实例时的实跑验证

---

## 1. 背景

提示词生成功能（`/api/v1/prompts/generate`、`/moderate`）的 moderation 阶段用 `with_structured_output(ModerationVerdict)` 强制结构化裁决。该功能此前仅在 deepseek 上验证通过；接入阿里云百炼 qwen 专属实例后，**同一代码同一请求多次结果不一致**：

| 运行 | qwen 实际返回 | 结果 |
| --- | --- | --- |
| 第 1 次 | 400 `'messages' must contain the word 'json' ... response_format json_object` | 失败 |
| 第 2 次 | `{"passed": true, "violated_rules": [], "reasons": []}`（漏 `mode`） | 解析失败 |
| 第 3 次 | 同上（恰巧通过） | 200 |
| 第 4 次 | `{"violation": false, ...}`（字段名漂移 + 漏 `passed`） | 解析失败 |

**根因**：langchain-openai 的 `with_structured_output(schema)` 在未被识别的模型 / 自定义 `base_url` 下，默认 method 会回落到 **json_object 响应格式**。OpenAI 的 json_object 模式**只要求模型"返回点 JSON"，不下发 schema**——模型全凭猜测命名与字段取舍。deepseek 恰好猜得稳定，qwen 不稳定（`passed`↔`violation` 漂移、随机漏字段）。

附加约束：qwen3.7-plus 是 **thinking 模型**，阿里云兼容层禁止在 thinking 模式下设置 `tool_choice=required/object`，导致 `function_calling` 强制工具调用会被 400。

---

## 2. 方案

让结构化输出**走带 schema 的模式**，把字段契约真正下发给模型；同时把"已知入参"（`mode`）从 LLM 回显路径中剥离。

- moderator 强制 `method="function_calling"`：schema 作为 tool 定义下发，字段名/存在性由契约约束，不再依赖模型自觉。
- 部署侧选用**非 thinking** 的 qwen 型号（如 `qwen-plus`），避开 thinking 模式对 `tool_choice` 的限制（属 `.env` 配置，见 §5）。
- `ModerationVerdict.mode` 不再要求 LLM 回显：给默认值让漏字段能解析，moderator 用**入参**回填——`mode` 是请求参数，本不该由 LLM 当事实来源。

---

## 3. 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/core/moderator.py` | `with_structured_output(ModerationVerdict)` → `with_structured_output(ModerationVerdict, method="function_calling")`，并附根因注释；解析成功后 `verdict.mode = mode`（入参回填，不信任 LLM 回显） |
| `app/models/prompt.py` | `ModerationVerdict.mode: PromptMode` → `mode: PromptMode = PromptMode.acg`（默认值仅为让 LLM 漏字段时解析不崩；运行时由 moderator 按入参覆盖） |

---

## 4. 设计决定

| 决定 | 理由 | 备选（为何不选） |
| --- | --- | --- |
| `method="function_calling"` | tool 定义下发 schema，字段稳定；deepseek/智谱/qwen/doubao 等 OpenAI 兼容端均支持工具调用，跨 provider 安全 | `method="json_schema"`：依赖端点支持 json_schema response_format，qwen 部分型号不确定；`json_mode`（默认）：不下发 schema，根因未除 |
| `mode` 入参回填 | `mode` 是请求参数、非 LLM 产出，从入参取才是事实来源；与 method 选择正交，属 provider 无关的健壮性兜底 | 在 prompt 里要求 LLM 回显 `mode`：依赖模型自觉，仍脆弱 |
| 部署侧换非 thinking 型号 | thinking 模型与强制 `tool_choice` 在阿里云端互斥；且 thinking 对 `temperature=0` 的结构化裁决无增益、徒增延迟（~38s/次） | 给 meta-LLM 加 `enable_thinking=False`：专属 MaaS 实例是否认该参数未验证，且型号本身可能仍带其他 thinking 限制 |

---

## 5. 验证

- **deepseek（本次选定 provider）**：真实 `deepseek-chat` 端点连跑 2 次 `prompt_service.moderate` → 均 `code=200, passed=True, mode=acg`；`prompt_service.generate`（compliant）`code=200`（**5.0s**，209 字 system_prompt，moderation 通过，mode=compliant，estimate 186 tokens @ deepseek-chat）。
- **qwen（修复发现地）**：真实 `qwen-plus`（非 thinking）端点连跑 3 次 `moderate` → 字段稳定不漂移；`generate` 中性请求 `code=200`、含超能力幻觉请求 `code=403 'blocked'`（裁判正确命中"不得承诺 knowledge_search 之外的能力"，护栏履职）。注：`qwen3.7-plus`（thinking 模型）与 `tool_choice=required` 不兼容，qwen 须用非 thinking 型号。
- **回归**：`pytest -q` → **138 passed**，无回归。
- **覆盖缺口（如实记录）**：单测用 `FakeLLM` mock `with_structured_output`，**不触达真实 provider 行为**，function_calling 字段稳定性只能靠对真实端点的手动冒烟验证。后续若引入各 provider 的集成测试再补。

---

## 6. 范围（未做）

- `.env` 的 meta-LLM 配置属**部署配置**，不入 git。本次选定 **deepseek**（`deepseek-chat` @ `api.deepseek.com/v1`，`META_LLM_API_KEY` 复用 `LLM_KEY_DEEPSEEK`）。若改用 qwen，须选**非 thinking** 型号（如 `qwen-plus`，**不可用** `qwen3.7-plus`）且 `base_url` 正确无误。
- retry 逻辑仍按 spec §8 留二期。
- 未新增 provider 非确定性的回归单测（FakeLLM 无法复现，见 §5 覆盖缺口）。
