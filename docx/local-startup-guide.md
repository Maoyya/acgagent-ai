# acgagent-ai 本地启动指南

> 版本：1.2.0 | 更新日期：2026-06-27 | 命令已于 Python 3.12.6 / Windows 实测通过

---

## 1. 前置条件

| 项目       | 要求                                   | 说明                                  |
| ---------- | -------------------------------------- | ------------------------------------- |
| Python     | 3.11+（项目 venv 实际为 3.12.6）       | `pyproject.toml` 声明 `python = "^3.11"` |
| 虚拟环境   | 已存在 `venv/`，依赖已安装             | 依赖见 `pyproject.toml`               |
| 端口       | 8100 空闲                              | 默认监听端口，可改                    |

> 仓库根目录已自带 `venv/`，FastAPI / Uvicorn / LangChain 等均已就绪，无需重新安装依赖即可直接启动。

---

## 2. 一键启动（推荐）

在项目根目录 `D:\PycharmProjects\pythonProject` 下执行：

```bash
venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8100
```

开发模式（改代码自动热重载）：

```bash
venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8100
```

看到以下日志即代表启动成功：

```
INFO:acgagent-ai:Chroma initialized at data\chroma
INFO:acgagent-ai:acgagent-ai started on port 8100
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8100 (Press CTRL+C to quit)
```

按 `Ctrl+C` 停止服务。

---

## 3. 验证服务

```bash
# 健康检查（无需鉴权，会回显 ChromaDB 连接状态）
curl http://localhost:8100/api/v1/health
# 期望：{"status":"healthy","version":"1.0.0","chroma":"connected",...}
```

也可浏览器打开交互式 API 文档：**http://localhost:8100/docs**

---

## 4. 配置（.env 可选但建议）

配置由 `app/config.py` 经 `pydantic-settings` 加载，**环境变量统一加前缀 `ACG_AI_`**，默认从项目根目录的 `.env` 文件读取。

项目根目录附带 **`.env.example`** 配置模板（可入库，仅含占位符/默认值）。复制为 `.env` 后填入真实值即可：

```bash
cp .env.example .env          # Windows: copy .env.example .env
```

`.env`（已被 `.gitignore`，不会提交）完整示例（与 `.env.example` 一致）：

```ini
# —— 鉴权（API Key） ——
# 生产环境务必改为强随机值；未配置时默认 dev-api-key
ACG_AI_API_KEY=dev-api-key

# —— meta-LLM（提示词生成 generate / 合规校验 moderate 必需，缺失则返回 500）——
ACG_AI_META_LLM_PROVIDER=deepseek
ACG_AI_META_LLM_MODEL=deepseek-chat
ACG_AI_META_LLM_BASE_URL=https://api.deepseek.com/v1
ACG_AI_META_LLM_API_KEY=

# —— 对话 / Agent LLM 密钥（方案 B：按 provider 分键）——
# agent 的 llm_config.api_key 为空时按 provider 从这里取（app/core/llm.py）；
# agent 自带 api_key 非空则优先用自带的。命名：ACG_AI_LLM_KEY_<PROVIDER 大写>。
#   DeepSeek
ACG_AI_LLM_KEY_DEEPSEEK=
#   智谱 GLM（base_url: https://open.bigmodel.cn/api/paas/v4/）
ACG_AI_LLM_KEY_ZHIPU=
#   豆包
ACG_AI_LLM_KEY_DOUBAO=
#   通义千问
ACG_AI_LLM_KEY_QWEN=

# —— 服务 / 运行时（均有默认值，按需取消注释覆盖）——
# ACG_AI_HOST=0.0.0.0
# ACG_AI_PORT=8100
# ACG_AI_LOG_LEVEL=INFO
# ACG_AI_DEBUG=false
# ACG_AI_DATA_DIR=./data
```

> 注意：**值后不要写行内注释**——python-dotenv 会把 `# ...` 当成值的一部分；注释请独占一行（如上）。

| 环境变量                 | 默认值                          | 备注                                   |
| ------------------------ | ------------------------------- | -------------------------------------- |
| `ACG_AI_API_KEY`         | `dev-api-key`                   | 启动时若仍为默认值会打印 WARNING       |
| `ACG_AI_META_LLM_API_KEY`| （空）                          | 必填，否则 `generate`/`moderate` 报 500 |
| `ACG_AI_LLM_KEY_<PROVIDER>`| （空）                        | 对话/Agent LLM 按 provider 分键（DEEPSEEK/ZHIPU/DOUBAO/QWEN），见 ini 注释 |
| `ACG_AI_PORT`            | `8100`                          | 修改后启动命令和访问地址同步改         |
| `ACG_AI_LOG_LEVEL`       | `INFO`                          | 调试可设 `DEBUG`                       |

---

## 5. 关键路径与鉴权

- **入口对象**：`app.main:app`（FastAPI 实例）
- **路由前缀**：所有业务接口挂在 `/api/v1/*` 下
- **鉴权**：除 `GET /api/v1/health` 外，所有 `/api/v1/*` 接口需在请求头携带
  `X-API-Key: <你的 ACG_AI_API_KEY>`
- **数据目录**：`data/`（启动时自动创建 `agents/knowledge_bases/documents/tools/chroma/uploads` 子目录）
- **向量库**：ChromaDB 持久化在 `data/chroma`

---

## 6. 备选启动方式

### 6.1 Poetry

```bash
poetry run uvicorn app.main:app --port 8100
```

> `poetry.toml` 设了 `virtualenvs.create = false`，Poetry 会复用系统/当前激活的解释器。

### 6.2 Docker

```bash
docker build -t acgagent-ai .
docker run -p 8100:8100 -v "$PWD/data:/app/data" acgagent-ai
```

镜像入口与本地一致（`uvicorn app.main:app --host 0.0.0.0 --port 8100`），详见 `Dockerfile`。

---

## 7. 在 PyCharm 中启动

项目可在 PyCharm（Community / Professional 均可）中直接启动与断点调试。仓库已附带现成运行配置：`.idea/runConfigurations/acgagent-ai.xml`。

### 7.1 确认解释器

`Settings → Project: pythonProject → Python Interpreter` 确认指向项目自带 venv：

```
D:\PycharmProjects\pythonProject\venv\Scripts\python.exe   (Python 3.12.6)
```

> `.idea/misc.xml` 中项目 SDK 为 `Python 3.12 (pythonProject)`，与 venv 版本一致，通常开箱即用。

### 7.2 启动（两种方式）

**方式一：直接用附带运行配置（推荐）**

打开 PyCharm 后，右上角运行配置下拉里选 **acgagent-ai (uvicorn)**，点 ▶ Run 或 🐞 Debug 即可。该配置等价于：模块名 `uvicorn`，参数 `app.main:app --port 8100`，工作目录 `$PROJECT_DIR$`。

**方式二：手动新建配置（`Run → Edit Configurations → + Python`）**

| 字段              | 值                                |
| ----------------- | --------------------------------- |
| Module name       | `uvicorn`（**不是** Script path） |
| Parameters        | `app.main:app --port 8100`        |
| Working directory | `$PROJECT_DIR$`（项目根目录）     |
| Python interpreter| 上面的 venv                       |

### 7.3 注意事项

- **`app/main.py` 没有 `if __name__ == "__main__"` 块**，因此不能右键 Run `main.py`；必须用上面的 uvicorn 方式拉起。
- **断点调试**：附带配置**未开启** `--reload`，故 🐞 Debug 断点可正常命中。若想要热重载，在 Parameters 末尾加 `--reload`，但此时断点会失效（reloader 会拉起子进程）。
- **环境变量**：配置未内嵌任何密钥；请在项目根目录放 `.env`（见第 4 节），因 Working directory 是项目根，`pydantic-settings` 会自动读取。
- **版本控制**：`.idea/` 已被 `.gitignore` 忽略，该运行配置仅本地生效。如需团队共享，在根 `.gitignore` 放行 `.idea/runConfigurations/` 后 `git add -f .idea/runConfigurations/` 即可。

---

## 8. 常见问题

| 现象                                              | 原因 / 处理                                                      |
| ------------------------------------------------- | ---------------------------------------------------------------- |
| 启动时 `WARNING: Using default API key 'dev-api-key'` | 未配置 `ACG_AI_API_KEY`，本地开发可忽略，生产必须改             |
| 调用 `generate` / `moderate` 返回 500             | 未配置 `ACG_AI_META_LLM_API_KEY`，补上 DeepSeek key 即可         |
| `[Errno 48] Address already in use` / 端口被占    | 8100 被占用，换 `--port 8101` 并同步改访问地址                    |
| `ModuleNotFoundError: No module named 'fastapi'`  | 没用 venv 解释器，确认走 `venv/Scripts/python.exe`               |
| ChromaDB 相关报错                                 | 检查 `data/chroma` 可写权限，必要时删除后让其自动重建            |

---

## 9. 运行测试（可选）

```bash
venv/Scripts/python.exe -m pytest
```

> 配置见 `pyproject.toml` 的 `[tool.pytest.ini_options]`（`asyncio_mode = "auto"`，测试目录 `tests/`）。
