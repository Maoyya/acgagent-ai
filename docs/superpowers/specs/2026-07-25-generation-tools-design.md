# 媒体生成 Agent 工具注册 + env 模板补全 — 设计

- 版本：1.0.0
- 日期：2026-07-25
- 分支：aiagent_dev
- 状态：待用户 review → 通过后进入 writing-plans

## 1. 背景与目标

文生图 / 图生视频能力已于 2026-07-11 以独立 REST API 形式落地（`POST /api/v1/generations/images|videos` + 异步任务轮询 `GET /api/v1/generations/tasks/{task_id}`），走 dashscope 通义万相（`wanx2.1-t2i-turbo` / `wan2.1-i2v-turbo`），完整链路（service / client / store / model / tests）均已提交。

但该能力**未注册为 Agent 内置工具**——`app/tools/__init__.py` 的 `BUILTIN_TOOLS` 只有 calculator / web_search / knowledge_search / knowledge_entry_lookup，LLM 在对话中无法「自主决定」调用生成。

本设计目标：
1. 将文生图 / 图生视频注册为内置工具，使 LLM 可在对话中决策调用（方案 A：元数据注册）。
2. 补全 generation 相关环境变量模板（`.env.example` / `.env`），当前两者均缺 `ACG_AI_GENERATION_*`，部署后不配 key 则提交返 500。
3. 顺带补齐 `tool_service` 中遗漏的 `knowledge_entry_lookup` 元数据（既有不一致，零风险）。

## 2. 关键架构事实（约束本设计）

项目的工具执行回路是「前端编排」型：

- `chat_service._get_tools` 把内置工具 bind 给 LLM（`bind_tools`），让 LLM 知道有哪些工具可调。
- LLM 决定调用工具时，后端**仅把 `tool_call` 作为 SSE 事件转发给前端**（`chat_service.py:98-102`），**Python 侧不执行工具**。
- `execute()` 在整个代码库仅被 `app/tools/base.py:27`（LangChain `@tool` 包装器）引用，**无 AgentExecutor、无工具执行循环**——当前 `execute()` 实际不参与运行。

因此「注册成 tool」的实际作用 = 让 LLM 能决策调用 + 工具列表 API 能展示；真正执行仍由前端收到 `tool_call` 事件后调 REST API 完成。`execute()` 作为工具能力实现存在，便于独立测试与未来后端直连，但当前不被 chat 流程调用。

## 3. 范围

### 3.1 做
- 新增 `ImageGenerationTool` / `VideoGenerationTool`（`BaseAgentTool` 子类）。
- `execute()` 复用 `generation_service`，**只 submit**（不做轮询至完成）。
- 注册到 `BUILTIN_TOOLS` 与 `tool_service`（`_builtin_ids` + `_get_builtins`）。
- 补齐 `knowledge_entry_lookup` 元数据。
- 补全 `.env.example` 与 `.env` 的 generation 配置块。
- 两个工具的单元测试。

### 3.2 不做（YAGNI）
- 不改 `chat_service` 工具执行回路（属二期，需独立设计）。
- `execute()` 不做「submit + 轮询至完成直接返回资产 URL」（用户确认不做；复杂逻辑且当前为死代码，留待后端执行回路接入时在回路层处理）。
- 不真实调 dashscope（测试一律 monkeypatch service）。

## 4. 详细设计

### 4.1 工具类

**`app/tools/image_generation.py` → `ImageGenerationTool`**
- `tool_id` / `name` = `"image_generation"`
- `description` = `"根据文字描述生成图片。传入 prompt（必填），可选 size（如 1024*1024）、n（生成数量）。提交后返回任务 task_id，需轮询取结果。"`

**`app/tools/video_generation.py` → `VideoGenerationTool`**
- `tool_id` / `name` = `"video_generation"`
- `description` = `"根据一张公网可达的图片 URL 生成视频。必须传入 image_url（公网可达，dashscope 需能拉取）与 prompt，可选 duration（秒，默认 5）。提交后返回任务 task_id，需轮询取结果。"`

两者均无构造参数（`chat_service._get_tools` 走 `else` 分支 `cls()` 实例化，与 calculator / knowledge_entry_lookup 一致）。

### 4.2 `execute()` 行为（只 submit）

同步 `execute` 内用 `asyncio.run()` 调用 async 的 `generation_service`。`Result` 信封（`code` / `message` / `data`）沿用 `app/models/common.py`。

**ImageGenerationTool.execute**
```
参数：prompt, size="1024*1024", n=1
1. prompt 为空 → return "请提供文生图提示词"
2. req = ImageGenerationRequest(prompt=prompt, size=size, n=n)
3. result = asyncio.run(generation_service.submit_image(req, user_id=None))
4. result.code != 200 → return f"文生图提交失败：{result.message}"
   （含 generation_api_key 未配置时的 "generation api key not configured" 透传，Fail Loud）
5. return f"已提交文生图任务，task_id={result.data['task_id']}。"
        f"用 GET /api/v1/generations/tasks/{task_id} 轮询获取结果。"
```

**VideoGenerationTool.execute**
```
参数：prompt, image_url, duration=5
1. prompt 为空 → return "请提供图生视频提示词"
2. image_url 为空 → return "请提供公网可达的首帧图 URL"
3. req = VideoGenerationRequest(prompt=prompt, image_url=image_url, duration=duration)
4. result = asyncio.run(generation_service.submit_video(req, user_id=None))
5. result.code != 200 → return f"图生视频提交失败：{result.message}"
6. return f"已提交图生视频任务，task_id={result.data['task_id']}。"
        f"用 GET /api/v1/generations/tasks/{task_id} 轮询获取结果。"
```

**`asyncio.run()` 限制（注释说明）**：若 `execute` 在已有 event loop 内被调用会抛 `RuntimeError`。当前 chat 流程不调 `execute`，故无影响；未来若接入后端执行回路（运行在 async 上下文），需改为在该回路内直接 await service，或引入 `nest_asyncio`。本设计不预先处理（YAGNI）。

### 4.3 注册点

**`app/tools/__init__.py`**：`BUILTIN_TOOLS` 增加两个映射
```
"image_generation": ImageGenerationTool,
"video_generation": VideoGenerationTool,
```

**`app/services/tool_service.py`**：
- `_builtin_ids` 增加 `"image_generation"`、`"video_generation"`、`"knowledge_entry_lookup"`（补齐既有遗漏）。
- `_get_builtins` 增加三个 `ToolVO`：

| id | name | description | parameters.properties | required |
|---|---|---|---|---|
| image_generation | 文生图 | 根据文字描述生成图片 | prompt(string), size(string), n(integer) | [prompt] |
| video_generation | 图生视频 | 根据公网图片 URL 生成视频 | prompt(string), image_url(string), duration(integer) | [prompt, image_url] |
| knowledge_entry_lookup | 设定库检索 | 在公共设定库中搜索风格/角色/故事等参考设定 | query(string), entry_type(string, enum: style/character/story) | [query] |

> `knowledge_entry_lookup` 补齐仅为消除「BUILTIN_TOOLS 有 4 项 / tool_service 只列 3 项」的既有不一致，属元数据修正，不改其执行逻辑。

### 4.4 env 补全

**`.env.example`** 新增 generation 配置块（接在「图片存储」段之后）：
```
# —— 媒体生成（文生图 / 图生视频，依赖阿里 dashscope 通义万相）——
# 必填：缺失时 POST /api/v1/generations/* 提交返 500。
ACG_AI_GENERATION_API_KEY=
# 以下均有默认值（见 app/config.py），按需取消注释覆盖。
# ACG_AI_GENERATION_BASE_URL=https://dashscope.aliyuncs.com/api/v1
# ACG_AI_GENERATION_IMAGE_MODEL=wanx2.1-t2i-turbo
# ACG_AI_GENERATION_VIDEO_MODEL=wan2.1-i2v-turbo
```

**`.env`**：追加同样 4 行（`ACG_AI_GENERATION_API_KEY=` 留空，由用户填入真实 dashscope key；其余以注释形式给出默认值）。

### 4.5 测试

**`tests/test_image_generation_tool.py`**（monkeypatch `generation_service.submit_image`）：
- submit 返回 `Result.success({"task_id": "tid123"})` → `execute` 返回串含 `tid123` 与轮询引导。
- `prompt` 为空 → 返回「请提供文生图提示词」。
- submit 返回 `Result.error(500, "generation api key not configured")` → 返回串含失败信息（Fail Loud 透传）。

**`tests/test_video_generation_tool.py`**（monkeypatch `generation_service.submit_video`）：
- submit 成功 → 返回串含 task_id。
- `prompt` 空 / `image_url` 空 → 各自的中文提示。
- submit 报错 → 错误透传。

可选断言：`from app.tools import BUILTIN_TOOLS` 含 `image_generation` / `video_generation`。

测试不真实调 dashscope，也不依赖 `settings.generation_api_key`（monkeypatch 在 service 层之上，绕过 key 校验）。

## 5. 文件清单

**新增**
- `app/tools/image_generation.py`
- `app/tools/video_generation.py`
- `tests/test_image_generation_tool.py`
- `tests/test_video_generation_tool.py`
- `tests/test_generation_tool_registration.py`

**修改**
- `app/tools/__init__.py`（`BUILTIN_TOOLS` +2）
- `app/services/tool_service.py`（`_builtin_ids` +3、`_get_builtins` +3 `ToolVO`）
- `.env.example`（generation 配置块）
- `.env`（generation 配置块，key 留空）

## 6. 成功标准

- `BUILTIN_TOOLS` 含 `image_generation` / `video_generation`；`tool_service.list_all()` 返回含两者 + `knowledge_entry_lookup` 的完整元数据。
- 两工具 `execute()` 在 service mock 下行为符合 4.2（成功返回 task_id、缺参提示、错误透传）。
- `.env.example` / `.env` 含 4 个 `ACG_AI_GENERATION_*` 项。
- 全量 `pytest` 通过，不破坏既有 176 个测试。

## 7. 遗留 / 后续

- `execute()` 当前不被 chat 流程调用；真正「对话内生成」需二期接入工具执行回路（届时 `execute` 的 `asyncio.run` 限制需重新评估）。
- `execute()` 仅 submit，不轮询；前端仍需自行轮询 REST API 取资产。
- `app/docx/` 业务文档与 `docs/changelogs/` 媒体生成 changelog 的补齐不在本设计范围。
