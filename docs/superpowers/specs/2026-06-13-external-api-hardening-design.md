# 对外 API 加固设计（单内部调用方）

- 日期：2026-06-13
- 状态：待审阅
- 范围：acgagent-ai（Python）服务的 API 鉴权与暴露加固

## 背景

acgagent-ai 是 AI 能力服务（FastAPI + LangChain + ChromaDB + LangGraph），由**同集群的 Java 后端**调用（acg-chat 等模块，配置托管于 Nacos，namespace `acg_agent`）。调用链路：**前端 → Java 后端 → Python agent**。

当前已具备单一共享 API Key 鉴权（`X-API-Key` ↔ `settings.api_key`，默认 `dev-api-key`），所有 `/api/v1/*` 受保护，`/api/v1/health` 免鉴权。连通性已验证（health 200、正确 key 200、错误 key 401、ChromaDB connected）。

本设计针对"安全地长期提供给 Java 调用"做**最小加固**，不新增子系统。

## 目标 / 成功标准

- Java 后端能用对齐后的 API Key 稳定、安全调用 Python agent。
- 鉴权失败统一返回 401；API Key 不进入代码仓库。
- 无新增复杂子系统（YAGNI）。

## 范围

**做**：
1. 鉴权代码加固（`app/api/deps.py`）。
2. 默认密钥启动告警（`app/main.py`）。
3. API Key 本地化注入（`.env` / 环境变量，已 gitignore）。
4. 网络层访问限制（部署侧；K8s / Docker / 裸机三选一）。
5. 调用约定与探针文档化。
6. 鉴权相关测试补全。

**不做（YAGNI）**：多 key 注册表、限流、密钥轮换、本层 HTTPS、租户/数据隔离、CORS 收紧（可选）。

## 现状（加固前）

- `app/api/deps.py:10` `verify_api_key`：明文 `!=` 比对；缺 header → FastAPI 422（`Header(...)` 必填所致）。
- `app/config.py:19` `api_key` 默认 `"dev-api-key"`，env 前缀 `ACG_AI_`（即 `ACG_AI_API_KEY`）。
- `app/main.py:16` `host=0.0.0.0:8100`；CORS `allow_origins=["*"]`（`app/main.py:53`）；仅 `LoggingMiddleware`。
- `.gitignore` 已含 `.env`（第 8 行）。
- 数据全局共享（无租户隔离）——本设计不改。

## 设计

### 1. 鉴权加固（代码，核心）

文件 `app/api/deps.py`，函数 `verify_api_key`：

- 形参改为 `x_api_key: str | None = Header(None, alias="X-API-Key")`（允许缺失）。
- 缺失或为空 → `raise HTTPException(status_code=401, detail="Missing API key")`。
- 比对改用 `secrets.compare_digest(x_api_key, settings.api_key)`；不符 → 401 `"Invalid API key"`。
- 保持返回 `x_api_key`。

效果：缺 key 从 422 → 401；比对改为常数时间。

### 2. 默认密钥启动告警（代码）

文件 `app/main.py` 的 `lifespan` 启动段：

- `if settings.api_key == "dev-api-key": logger.warning("Using default API key; set ACG_AI_API_KEY in production")`。
- 不阻断启动（本地开发友好）。

### 3. API Key 本地化注入（运维，无代码）

- 生成强随机 key（`python -c "import secrets; print(secrets.token_urlsafe(32))"`）。
- 写入本地 `.env`：`ACG_AI_API_KEY=<key>`（`.env` 已 gitignore，不提交）。
- 同一值配置到 Nacos `acg-chat.yaml`（Java 侧），保证两侧一致。
- 任何含 key 的文件不入 git。

> 当前已生成并写入本地 `.env`（见实施记录）；待 Java 侧在 Nacos 配入同一值。

### 4. 网络层访问限制（运维，按部署环境）

应用层保持 `host=0.0.0.0`，限制在网络层：

- **K8s**：Service 用 ClusterIP（不开 NodePort/LoadBalancer）；NetworkPolicy 仅允许 Java 后端 Pod（按 namespace/label）入站 8100。
- **Docker Compose**：Python 与 Java 同 internal network，不 publish 8100 到宿主。
- **裸机**：主机防火墙仅放行 Java 所在机器 IP 到 8100。

### 5. 调用约定（文档）

- Java 调 `${agent-base}/api/v1/*`，请求头 `X-API-Key: <key>`（base URL 配在 Nacos `acg-chat.yaml`）。
- 存活/就绪探针：`GET /api/v1/health`（免鉴权），期望 200。
- 错误码：401 = 鉴权失败；其余按业务 `Result` 约定。

### 6. 测试（TDD）

扩展 `tests/`（复用现有鉴权 fixture）：

- 合法 key → 200。
- 缺 key → 401（新行为）。
- 错误 key → 401。
- 默认 key 启动告警命中（caplog）。

## 错误处理

鉴权失败统一 401（缺/错）。`/api/v1/health` 维持开放。无新增异常路径。

## 安全考量

- API Key 仅存本地 `.env` 与 Nacos，不进 git（`.gitignore` 已覆盖）。
- 常数时间比对防计时侧信道。
- 网络层限制降低暴露面。

## 风险 / 取舍

- 单 key 模型：若未来新增调用方，需扩成 key 注册表（届时再做，现 YAGNI）。
- 本层不做 HTTPS：依赖集群/ingress 的 TLS 或内网可信。

## 验收

- 上述测试全绿。
- Java 用对齐后的 key 调 `/api/v1/agents` 返回 200。
- `.env` 含 key，且 `git status` 不显示 `.env`。
