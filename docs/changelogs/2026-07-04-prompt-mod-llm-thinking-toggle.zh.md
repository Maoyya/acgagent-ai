# moderation LLM 支持 extra_body 配置（关 thinking，适配 deepseek-v4-pro）

> 日期：2026-07-04 | 类型：fix（provider 兼容 / 可配置性）| 关联代码：`app/config.py`、`app/services/prompt_service.py`、`.env.example`、`tests/test_config.py`
> 承接：`2026-07-04-prompt-moderation-structured-output-fix.zh.md`（moderation 已强制 `function_calling`）

---

## 1. 背景

deepseek-chat 月底将被弃用，meta-LLM 需迁移到 **deepseek-v4-pro**。但 v4-pro 是 **thinking 模型**，与上一轮强制 `function_calling`（`tool_choice=required`）冲突：

```
openai.BadRequestError: 400 - 'Thinking mode does not support this tool_choice'
```

DeepSeek 官方文档（[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)）明确：thinking 模式**支持** tool 调用，但**不支持**强制 `tool_choice`；关思考的参数是 `extra_body={"thinking":{"type":"disabled"}}`（结构体，非 `{"thinking":false}`）。

moderation 是 `temperature=0` 的确定性裁决，本不需要思考；而生成（builder）反而能从思考中受益。因此只需在 **mod LLM** 关思考即可。

---

## 2. 方案

新增**可配置**的 mod-LLM `extra_body`（JSON），按 provider 透传 vendor 选项；`_build_mod_llm` 消费，`_build_gen_llm` 不动（保留思考）。

- 配置项 `meta_llm_mod_extra_body`：env 里是 JSON 字符串，启动时 pydantic `field_validator(mode="before")` 解析为 dict；空串→`{}`；**非法 JSON → 启动即 ValidationError**（Rule 12 fail-loud，不让错误配置静默流到运行时 500）。
- deepseek-v4-pro 关思考值：`{"thinking":{"type":"disabled"}}`。

---

## 3. 改动清单

| 文件 | 改动 |
| --- | --- |
| `app/config.py` | 新增 `meta_llm_mod_extra_body: dict` 字段 + `@field_validator` 把 env 的 JSON 字符串解析为 dict（空→`{}`、非法→报错）；新增 `json`、`Field`、`field_validator` 导入 |
| `app/services/prompt_service.py` | `_build_mod_llm` 透传 `extra_body=settings.meta_llm_mod_extra_body or None`；`_build_gen_llm` 不动 |
| `.env.example` | 新增 `ACG_AI_META_LLM_MOD_EXTRA_BODY=` 占位 + 说明（thinking 模型必填、deepseek 关思考值、非 thinking 模型留空） |
| `tests/test_config.py` | 新增 3 个用例锁定解析意图：空串→`{}`、合法 JSON→dict、非法 JSON→ValidationError |

---

## 4. 设计决定

| 决定 | 理由 | 备选（为何不选） |
| --- | --- | --- |
| 配置化（settings 字段）而非硬编码 | `{"thinking":{"type":"disabled"}}` 是 **deepseek 专有语法**（qwen 用 `enable_thinking`、OpenAI 用 `reasoning_effort`）。硬编码 = 给换 provider 埋坑。放配置，换 provider 改 `.env` 即可，代码不动 | 硬编码在 `_build_mod_llm`：1 行更省事，但把 vendor 语法写死，违背上一轮可移植性修复的初衷 |
| 只作用于 mod_llm | mod 必须关思考（tool_choice 冲突）；gen（builder）保留思考以利用 v4-pro 的生成质量 | gen/mod 都关：更简单但浪费 v4-pro 的思考能力 |
| `field_validator` 启动期解析 | 错误的 JSON 配置**启动即挂**，符合 Rule 12 fail-loud | 运行时惰性解析：错误会变成笼统的 500 "generation failed"，难排查 |

---

## 5. 验证

- **端到端（deepseek-v4-pro）**：`prompt_service.moderate` 连跑 2 次 → 均 `code=200, passed=True`；`prompt_service.generate`（compliant）`code=200`（**6.1s**，moderation 通过，135 tokens）。思考关闭后 function_calling 稳定。
- **回归**：`pytest -q` → **141 passed**（138 原有 + 3 个新 config 用例）。
- **fail-loud**：`meta_llm_mod_extra_body="not-json{"` → 启动 ValidationError（被 `test_mod_extra_body_invalid_json_raises_validation_error` 锁定）。
- **覆盖缺口（沿用上轮）**：单测用 FakeLLM，仍无法在 CI 覆盖真实 provider 的 thinking 行为，只能手动冒烟。

---

## 6. 范围（未做）

- gen_llm 仍保留思考（provider 默认 `enabled`），不额外配置；若日后需要按 provider 调 gen 的 vendor 选项，再加 `meta_llm_gen_extra_body`。
- 其他 provider 的关思考语法各异，换 provider 时由 `.env` 的 `ACG_AI_META_LLM_MOD_EXTRA_BODY` 给出对应值（如 qwen3 系 `{"enable_thinking":false}`）。
