# 系统提示词生成功能 — 设计文档（Spec）

> 版本：1.0.0 | 日期：2026-06-21 | 所属项目：acgagent-ai
> 状态：待评审 → 通过后进入 writing-plans

---

## 1. 目标与背景

为 acgagent-ai 增加一个「系统提示词生成」能力：让用户用零散的自然语言要求，自动组装成一段可用的 Agent `system_prompt`，并对生成产物做内容合规校验、消耗估算、用户偏好记录。

本功能服务两条产品线，由 **mode 开关**切换约束强度：

- **ACG 模式（`acg`）**：拥抱二次元/动漫风格，只挡暴力违法/超能力。
- **合规模式（`compliant`）**：中性专业，额外限制二次元风格。

### 1.1 关键边界决策（已与用户确认）

| # | 决策 | 选择 |
|---|---|---|
| 1 | 产品定位 | **双模式**，可配置开关；限制规则按 `mode` 参数化 |
| 2 | 存储 / 后台 CRUD 位置 | **Java acgagent 侧**管模板 CRUD + MySQL + 后台；**Python 侧**只暴露生成/校验/估算/偏好能力。Python **不引入 MySQL** |
| 3 | 实施方案 | **方案 A（MVP 分期）**：一期做生成+单裁判校验+生成前估算+偏好写入；二期升级多裁判投票+生成后真实 usage+推荐接口 |
| 4 | 生成/校验用哪个 LLM | **settings 级 meta-LLM**（环境变量 `ACG_AI_META_LLM_*`），不在请求中传 `llm_config` |
| 5 | moderation 不通过返回 | `Result(code=403, message="blocked", data=ModerationVerdict)` |
| 6 | 一期校验对象 | 只校验**生成出来的 system_prompt**，不预筛用户原始输入（预筛留二期） |
| 7 | 偏好写入失败 | best-effort，记 warning，**不阻断**主流程 |
| 8 | 消耗评估口径 | 估「模板自身将来每次对话多吃多少 prompt token」+ 用户 hints token；`est_completion_tokens` 一期=0 |

---

## 2. 范围

### 2.1 一期范围（本 spec 覆盖，Python 侧）

1. **生成（b）**：元提示词 → meta-LLM → `system_prompt`
2. **单裁判 moderation（c）**：按 `mode` 注入规则，structured output 裁决，不通过返回 403
3. **生成前消耗估算（d）**：tiktoken 复用 `count_tokens`
4. **偏好写入（f）**：ChromaDB collection `user_preferences`，按 `user_id` 索引

### 2.2 二期范围（本 spec 不实现，仅留接口/钩子）

- moderation 从单裁判升级为 **3 裁判投票、2/3 多数通过**（钩子：`confidence` 字段）
- 消耗评估补充**生成后真实 usage**（`est_completion_tokens` 有值）
- `GET /prompts/recommendations` 偏好推荐接口
- 预筛用户原始 hints（省一次 LLM 调用）

### 2.3 明确不在本 spec 范围

- 前端模板选择 UI（a）、MySQL 表结构、后台管理系统（e）—— 均归 **Java 侧**，Python 仅以 HTTP 契约对接
- 模板的持久化 `template_id` —— 由 Java 落库；Python 的 `generate` 响应不带 `template_id`

---

## 3. 架构

### 3.1 分层（严格沿用现有项目结构）

```
API      app/api/v1/prompt.py           （新；复用 verify_api_key + Result<T>）
Service  app/services/prompt_service.py （新；编排 generate→moderate→estimate→record）
Core     app/core/prompt_builder.py     （新；组装元提示词）
         app/core/moderator.py          （新；单裁判，structured output）
         app/core/cost_estimator.py     （新；复用 core/memory.count_tokens）
Storage  app/db/preference_store.py     （新；ChromaDB collection user_preferences）
Models   app/models/prompt.py           （新；请求/响应/枚举/裁决结构）
Config   app/config.py                  （改；加 meta_llm_* 字段）
Router   app/api/v1/router.py           （改；挂载 prompt_router）
```

### 3.2 Java / Python 边界

```
Java acgagent                         Python acgagent-ai
  │                                     │
  │  POST /api/v1/prompts/generate      │  generate(): builder→moderator→estimator→preference
  │ ─────────────────────────────────>  │  （2 次 LLM 调用 + 纯计算 + ChromaDB 写）
  │  {system_prompt, moderation,        │
  │   estimate}                         │
  │ <─────────────────────────────────  │
  │                                     │
  │  Java 落库为 template（MySQL）       │
```

Python 不持有模板，只产出「提示词文本 + 校验结果 + 估算」。

### 3.3 meta-LLM 配置（settings 级）

在 `app/config.py` 新增字段（前缀沿用 `ACG_AI_`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `ACG_AI_META_LLM_PROVIDER` | `deepseek` | 生成/校验用的元模型供应商 |
| `ACG_AI_META_LLM_MODEL` | `deepseek-chat` | 模型名 |
| `ACG_AI_META_LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容 base_url |
| `ACG_AI_META_LLM_API_KEY` | `` | API Key；缺失时 `generate`/`moderate` 返回 500 |

`prompt_service` 用这些字段构造一个 `LLMConfig`，复用现有 `app/core/llm.create_chat_model(config)` 得到 `ChatOpenAI` 实例。**温度处理（定死，避免歧义）：由同一份 `LLMConfig` 派生两个实例**——生成用 `temperature=0.7`、校验用 `temperature=0`，二者仅温度不同，其余配置相同。在 `prompt_service` 初始化时创建并缓存这两个实例。

---

## 4. 数据模型（`app/models/prompt.py`）

```python
from enum import Enum
from pydantic import BaseModel, Field


class PromptMode(str, Enum):
    acg = "acg"
    compliant = "compliant"


class PromptGenerateRequest(BaseModel):
    user_hints: list[str] = Field(description="用户零散要求")
    mode: PromptMode = PromptMode.acg
    target_capabilities: list[str] = Field(
        default_factory=list,
        description="可选；Agent 能力标签，用于'不超能力'约束",
    )


class ModerateRequest(BaseModel):
    system_prompt: str
    mode: PromptMode
    target_capabilities: list[str] = Field(default_factory=list)


class EstimateRequest(BaseModel):
    system_prompt: str
    user_hints: list[str] = Field(default_factory=list)


class ModerationVerdict(BaseModel):
    passed: bool
    violated_rules: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    mode: PromptMode


class CostEstimate(BaseModel):
    prompt_tokens: int
    est_completion_tokens: int = 0  # 一期恒为 0；二期接 LLM 真实 usage
    model: str


class PromptGenerateResponse(BaseModel):
    system_prompt: str
    mode: PromptMode
    moderation: ModerationVerdict
    estimate: CostEstimate
```

> `Result<T>` 信封沿用 `app/models/common.py`，不在本文件重复定义。

---

## 5. 核心逻辑

### 5.1 生成（`prompt_builder.py`）

构造一段**元提示词**交给 meta-LLM（非流式 `ainvoke`，temperature ≈ 0.7），产出 `system_prompt` 正文：

```
[元提示词结构]
角色：你是一名提示词工程师
任务：根据下面的「用户要求」，写一段 Agent 的系统提示词（system_prompt）正文
用户要求：{user_hints}
风格约束（按 mode）：
  - acg       → 可使用二次元/动漫人设语气，但仍保持专业
  - compliant → 中性专业，避免二次元风格与夸张人设
能力约束：若提供 target_capabilities，生成的提示词不得宣称这些能力之外的承诺
输出：只输出 system_prompt 正文，不要解释、不要前缀
```

### 5.2 单裁判 moderation（`moderator.py`）

规则是一个数据结构，按 `mode` 取用：

```python
RULES: dict[PromptMode, list[str]] = {
    PromptMode.acg: [
        "禁止暴力 / 违法犯罪 / 自残 / 色情内容",
        "禁止超出 target_capabilities 的能力承诺",
        # 二次元风格：允许
    ],
    PromptMode.compliant: [
        "禁止暴力 / 违法犯罪 / 自残 / 色情内容",
        "禁止二次元 / 动漫风格、夸张人设",
        "禁止超出 target_capabilities 的能力承诺",
    ],
}
```

裁判流程：
1. 取 `RULES[mode]`（含 `target_capabilities` 拼接能力边界）
2. 构造裁判提示词：列出规则 + 候选 `system_prompt`，要求逐条判断
3. **structured output**：`meta_llm.with_structured_output(ModerationVerdict)`，`temperature=0`
4. 返回 `ModerationVerdict`

### 5.3 消耗估算（`cost_estimator.py`）

```python
def estimate(system_prompt: str, user_hints: list[str], model: str) -> CostEstimate:
    prompt_tokens = count_tokens(system_prompt) + sum(count_tokens(h) for h in user_hints)
    return CostEstimate(prompt_tokens=prompt_tokens, est_completion_tokens=0, model=model)
```

复用 `app/core/memory.count_tokens`（tiktoken）。纯计算，无 LLM 调用。

### 5.4 编排（`prompt_service.generate`）

```
generate(req, user_id):
  1) candidate = builder.build(req.user_hints, req.mode, req.target_capabilities)   # LLM #1
  2) verdict   = moderator.moderate(candidate, req.mode, req.target_capabilities)   # LLM #2 (structured)
     if not verdict.passed:
        return Result(code=403, message="blocked", data=verdict)
  3) estimate  = cost_estimator.estimate(candidate, req.user_hints, meta_model)     # 纯计算
  4) try: preference_store.record(user_id, req.mode, req.user_hints, candidate)     # ChromaDB
     except: logger.warning(...)   # best-effort，不阻断
  5) return Result.success(PromptGenerateResponse(system_prompt=candidate, mode=req.mode,
                                                   moderation=verdict, estimate=estimate))
```

---

## 6. 存储（`preference_store.py`）

复用 `app/db/chroma_client.get_chroma()`，新建 collection：

- 名称：`user_preferences`
- 距离：cosine（与现有 collection 一致）
- 每条记录：
  - `document` = 生成的 `system_prompt` 文本（向量化，供二期相似度推荐）
  - `metadata` = `{user_id, mode, hint_tags, created_at}`
- 方法（一期）：`record(user_id, mode, hints, prompt)`
- 方法（二期预留）：`recommend(user_id, top_k)`，用 `where={"user_id": ...}` 过滤 + 相似度查询

---

## 7. HTTP 契约（Python 暴露给 Java）

所有路由前缀 `/api/v1`，需 `X-API-Key`；`user_id` 由 Java 经 `X-User-Id` 透传。

| 方法 | 路径 | 用途 | 期 |
|---|---|---|---|
| POST | `/api/v1/prompts/generate` | 主入口：组装→校验→估算→写偏好，一次返回 | 一期 |
| POST | `/api/v1/prompts/moderate` | 独立校验（Java 校验用户已保存模板） | 一期 |
| POST | `/api/v1/prompts/estimate` | 独立消耗估算 | 一期 |
| GET | `/api/v1/prompts/recommendations` | 偏好推荐 | 二期 |

### 7.1 `generate` 请求 / 响应示例

请求：
```jsonc
{
  "user_hints": ["要一个毒舌但专业的客服", "回答偏简洁"],
  "mode": "acg",
  "target_capabilities": ["chat", "rag"]
}
// Header: X-API-Key, X-User-Id
```

成功响应（`code=200`）：
```jsonc
{
  "code": 200, "message": "success",
  "data": {
    "system_prompt": "你是一名...",
    "mode": "acg",
    "moderation": { "passed": true, "violated_rules": [], "reasons": [], "confidence": 0.95, "mode": "acg" },
    "estimate": { "prompt_tokens": 120, "est_completion_tokens": 0, "model": "deepseek-chat" }
  }
}
```

不通过响应（`code=403`）：
```jsonc
{
  "code": 403, "message": "blocked",
  "data": { "passed": false, "violated_rules": ["禁止二次元风格..."], "reasons": ["包含动漫夸张人设"], "confidence": 0.9, "mode": "compliant" }
}
```

---

## 8. 错误处理

| 场景 | 处理 |
|---|---|
| moderation 不通过 | `code=403, message="blocked", data=ModerationVerdict` |
| `mode` 非法 | 422（FastAPI Enum 校验自动） |
| meta-LLM 未配置（api_key 缺失）/ 调用失败 | `code=500`，清晰 message（沿用项目「LLM 异常=500」） |
| structured output 解析失败 | **重试一次**；仍失败 → `code=500`（不静默放行，Fail Loud） |
| 偏好写入失败 | warning 日志，不阻断，正常返回提示词 |

---

## 9. 测试（CLAUDE.md 规则 9：验证意图，非仅行为）

每个用例绑定一条业务意义，业务变更时它会失败。复用 `tests/conftest.py` 中 mock LLM 机制，mock meta-LLM。

| 用例 | 验证的意图 |
|---|---|
| `test_moderate_blocks_violence_in_both_modes` | 暴力内容两 mode 都挡 → 底线规则与 mode 无关 |
| `test_anime_blocked_only_in_compliant` | 二次元只在 compliant 挡 → mode 差异生效 |
| `test_generate_blocks_out_of_capability` | 宣称 `target_capabilities` 之外能力被挡 → 「不超能力」约束 |
| `test_estimate_scales_with_prompt_length` | 提示词越长 estimate 越大 → 估算是真实的 |
| `test_preference_recorded_after_successful_generate` | 成功生成后 ChromaDB 多一条 → 偏好写入 |
| `test_preference_failure_does_not_block_generate` | mock 偏好写入抛异常，generate 仍正常返回 → best-effort |
| `test_blocked_returns_403_envelope` | 不通过时 `code=403` 且 data 带原因 → Java 契约 |

---

## 10. 假设与待办

- **假设**：Java 侧会负责模板落库、后台管理、`user_id` 体系；Python 只接受透传的 `X-User-Id`。
- **假设**：meta-LLM 为 OpenAI 兼容接口（与现有 `create_chat_model` 一致）。
- **二期触发条件**：当一期单裁判的误杀/漏放率达到不可接受水平时，再引入多裁判投票（用 `confidence` 决定是否升级）。
