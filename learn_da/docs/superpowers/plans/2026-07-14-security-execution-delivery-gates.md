# Security Execution and Delivery Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将生产代码执行迁移到独立、受限且 fail-closed 的 Runner，并补齐匿名会话、Web/API 信任边界和可重复执行的交付门禁。

**Architecture:** FastAPI API 只校验请求、生成关联 ID 并通过内部 HTTP 调用 Runner；Runner 在独立部署单元中使用容器执行提供者。浏览器身份改为签名匿名 session cookie，富文本统一经 Markdown parser 与 allow-list sanitizer，生产 readiness 同时检查数据库与 Runner。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、httpx、Docker SDK、SQLAlchemy、Vue 3、TypeScript 5.9、Axios、markdown-it、DOMPurify、Vitest、GitHub Actions。

## Global Constraints

- 生产 API 进程不得调用 `subprocess`、Docker SDK或其他本地代码执行路径。
- Runner 不可用、失联或未就绪时，`POST /api/v1/playground/execute` 返回 HTTP `503` 和 `status=unavailable`；不得本地回退或返回 mock 成功。
- 执行状态只允许 `success`、`error`、`timeout`、`rejected`、`unavailable`。
- 受控用户代码错误与运行超时返回 HTTP `200`；输入拒绝返回 `4xx`；基础设施不可用返回 `503`。
- Runner 默认限制为 5 秒、256 MiB、0.5 CPU、64 PIDs、stdout 64 KiB、stderr 64 KiB；禁止网络、使用非 root UID、只读根文件系统、`cap_drop=ALL` 和 `no-new-privileges`。
- 匿名身份使用签名、`HttpOnly`、生产环境 `Secure`、`SameSite=Lax` 的 session cookie；客户端不得发送 `visitorId` 作为授权身份。
- 快照默认每页 20 条、最大每页 50 条；每个匿名会话最多保留 100 条，全局最多保留 10,000 条。
- 完整代码、session secret、Runner token 和未经脱敏的用户数据不得写入日志。
- 本计划不改变学习完成语义、推荐算法、Monaco 编辑器、可验证练习或登录账号体系。

---

## File Map

### Backend API

- Modify: `learn_da/config/settings.py` - 生产配置校验、Runner/session/保留策略配置。
- Modify: `learn_da/main.py` - lifespan 资源、session 中间件、liveness/readiness 和生产 OpenAPI 开关。
- Create: `learn_da/app/core/session.py` - 匿名 session 的唯一身份接口。
- Create: `learn_da/app/core/client_ip.py` - 可信代理下的客户端 IP 解析。
- Modify: `learn_da/app/sandbox/schemas.py` - 稳定执行契约与状态枚举。
- Create: `learn_da/app/sandbox/client.py` - Runner HTTP client。
- Modify: `learn_da/app/sandbox/service.py` - 仅委托 Runner，移除本地/Docker/mock 选择。
- Delete after migration: `learn_da/app/sandbox/local_runner.py`, `learn_da/app/sandbox/docker_runner.py` - 不再属于 API 进程。
- Modify: `learn_da/app/playground/schemas.py`, `service.py`, `router.py` - 异步执行和结构化失败。
- Modify: `learn_da/app/agent/service.py`, `schemas.py` - Agent 只返回候选修复，不自动执行。
- Modify: `learn_da/app/analytics/router.py`, `schemas.py`, `service.py`, `repository.py` - session 身份、分页、保留和输入约束。
- Modify: `learn_da/app/learning/router.py`, `learn_da/app/agent/router.py` - 从 session 注入 visitor ID。
- Modify: `learn_da/app/middleware/security.py`, `rate_limit.py`, `cors.py` - 安全响应头、可信代理和 cookie CORS。

### Runner

- Create: `learn_da_runner/pyproject.toml`, `Dockerfile` - 独立 Runner 工程与镜像。
- Create: `learn_da_runner/runner/main.py`, `settings.py`, `schemas.py`, `auth.py`, `provider.py` - 内部 HTTP API 与 Docker 执行提供者。
- Create: `learn_da_runner/tests/test_api.py`, `test_provider.py` - 鉴权、状态映射和容器限制测试。
- Modify: `learn_da/Dockerfile.sandbox` - 非 root 执行镜像。

### Frontend

- Modify: `learn_da_vue/src/api/index.ts` - cookie credentials 与取消信号契约。
- Modify: `learn_da_vue/src/api/playground.ts`, `analytics.ts`, `recommendation.ts`, `agent.ts` - 新执行/session 契约。
- Modify: `learn_da_vue/src/types/api.ts` - 执行状态、分页和移除 visitor ID。
- Modify: `learn_da_vue/src/stores/playground.ts`, `src/views/Playground.vue`, `src/components/agent/AgentPanel.vue` - 明确失败状态和 Agent 候选代码确认。
- Modify: `learn_da_vue/src/views/Learning.vue`, `LessonDetail.vue`, `Dashboard.vue` - 停止传 visitor ID。
- Replace: `learn_da_vue/src/lib/markdown.ts` - markdown-it + DOMPurify。
- Create: `learn_da_vue/src/api/index.spec.ts`, `src/api/agent.spec.ts`, `src/lib/markdown.spec.ts`, `src/stores/playground.spec.ts` - 前端关键契约测试。
- Create: `learn_da_vue/vitest.config.ts`, `src/test/setup.ts` - Vitest 配置。

### Deployment And Quality

- Modify: `docker-compose.prod.yml`, `deploy/nginx.conf`, `deploy/.env.example` - 独立 Runner、生产安全配置和健康检查。
- Create: `docker-compose.runner-dev.yml` - 仅本地受控测试使用 Docker socket 的覆盖配置。
- Modify: `learn_da_vue/Dockerfile` - 使用完整 `npm run build`。
- Create: `.github/workflows/ci.yml`, `learn_da/scripts/check_mypy_baseline.py` - CI 与类型债务增量门禁。
- Modify: `learn_da/pyproject.toml`, `learn_da_vue/package.json`, lock files - 测试、安全依赖与脚本。

---

### Task 1: Freeze The Execution Contract And Fail-Closed Settings

**Files:**
- Modify: `learn_da/config/settings.py`
- Modify: `learn_da/app/sandbox/schemas.py`
- Modify: `learn_da/app/playground/schemas.py`
- Create: `learn_da/tests/unit/test_security_settings.py`
- Create: `learn_da/tests/unit/test_execution_contract.py`

**Interfaces:**
- Produces: `ExecutionStatus`, `ExecutionSource`, `RunnerExecutionRequest`, `SandboxExecutionResult`.
- Produces settings: `RUNNER_URL`, `RUNNER_TOKEN`, `RUNNER_TIMEOUT_SECONDS`, `SESSION_SECRET`, `SESSION_COOKIE_NAME`, `SNAPSHOT_MAX_PER_SESSION`, `SNAPSHOT_MAX_GLOBAL`.

- [ ] **Step 1: Write failing production configuration tests**

```python
# learn_da/tests/unit/test_security_settings.py
import pytest
from pydantic import ValidationError

from config.settings import Settings


def production_settings(**overrides):
    values = {
        "APP_ENV": "production",
        "CORS_ORIGINS": "https://learn.example.com",
        "RUNNER_URL": "http://runner:8080",
        "RUNNER_TOKEN": "r" * 32,
        "SESSION_SECRET": "s" * 32,
        "SANDBOX_LOCAL_ENABLED": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_requires_runner_and_secrets():
    with pytest.raises(ValidationError):
        production_settings(RUNNER_URL="", RUNNER_TOKEN="", SESSION_SECRET="")


def test_production_rejects_local_execution():
    with pytest.raises(ValidationError):
        production_settings(SANDBOX_LOCAL_ENABLED=True)
```

- [ ] **Step 2: Run the settings tests and confirm they fail**

Run: `cd learn_da && uv run pytest tests/unit/test_security_settings.py -q`

Expected: FAIL because Runner/session settings and the production validator do not exist.

- [ ] **Step 3: Add exact settings and production validation**

Add these fields and a `model_validator(mode="after")` to `Settings`:

```python
RUNNER_URL: str = "http://127.0.0.1:8080"
RUNNER_TOKEN: str = ""
RUNNER_TIMEOUT_SECONDS: float = 7.0
SESSION_SECRET: str = "development-only-change-me"
SESSION_COOKIE_NAME: str = "learn_da_session"
SNAPSHOT_MAX_PER_SESSION: int = 100
SNAPSHOT_MAX_GLOBAL: int = 10_000
SNAPSHOT_PAGE_SIZE_DEFAULT: int = 20
SNAPSHOT_PAGE_SIZE_MAX: int = 50
TRUSTED_PROXY_IPS: str = ""
OPENAPI_ENABLED: bool = False

@model_validator(mode="after")
def validate_production_security(self) -> "Settings":
    if self.APP_ENV != "production":
        return self
    if self.SANDBOX_LOCAL_ENABLED:
        raise ValueError("SANDBOX_LOCAL_ENABLED must be false in production")
    if not self.RUNNER_URL.strip():
        raise ValueError("RUNNER_URL is required in production")
    if len(self.RUNNER_TOKEN) < 32:
        raise ValueError("RUNNER_TOKEN must contain at least 32 characters")
    if len(self.SESSION_SECRET) < 32:
        raise ValueError("SESSION_SECRET must contain at least 32 characters")
    return self
```

- [ ] **Step 4: Define and test the wire contract**

```python
# learn_da/app/sandbox/schemas.py
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


ExecutionSource = Literal["playground", "agent_suggested"]


class RunnerExecutionRequest(BaseModel):
    request_id: UUID
    code: str = Field(min_length=1, max_length=5000)
    language: Literal["python"] = "python"
    source: ExecutionSource = "playground"


class SandboxExecutionResult(BaseModel):
    request_id: UUID
    execution_id: UUID
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    error_type: str | None = None
    duration_ms: int = Field(ge=0)
    output_truncated: bool = False
```

Update `ExecuteCodeRequest/Response` to expose the same IDs, `source`, status, `errorType`, `durationMs` and `outputTruncated`; remove `mocked` and `usedSandbox` from the public contract. Test JSON aliases in `test_execution_contract.py`.

- [ ] **Step 5: Run contract and existing playground tests**

Run: `cd learn_da && uv run pytest tests/unit/test_security_settings.py tests/unit/test_execution_contract.py tests/unit/test_playground_service.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the contract**

```bash
git add learn_da/config/settings.py learn_da/app/sandbox/schemas.py learn_da/app/playground/schemas.py learn_da/tests/unit/test_security_settings.py learn_da/tests/unit/test_execution_contract.py
git commit -m "refactor: define fail-closed execution contract"
```

---

### Task 2: Build The Standalone Runner Service

**Files:**
- Create: `learn_da_runner/pyproject.toml`
- Create: `learn_da_runner/runner/__init__.py`
- Create: `learn_da_runner/runner/settings.py`
- Create: `learn_da_runner/runner/schemas.py`
- Create: `learn_da_runner/runner/auth.py`
- Create: `learn_da_runner/runner/provider.py`
- Create: `learn_da_runner/runner/main.py`
- Create: `learn_da_runner/tests/test_api.py`
- Create: `learn_da_runner/tests/test_provider.py`
- Create: `learn_da_runner/Dockerfile`
- Modify: `learn_da/Dockerfile.sandbox`

**Interfaces:**
- Consumes: Task 1 JSON contract.
- Produces: `POST /v1/executions`, `GET /live`, `GET /ready` on port `8080`.
- Produces: `DockerExecutionProvider.execute(request) -> RunnerExecutionResult`.

- [ ] **Step 1: Scaffold only the test/runtime dependencies**

`learn_da_runner/pyproject.toml` must include Python `>=3.12`, `fastapi`, `uvicorn`, `pydantic-settings`, `docker`; dev dependencies are `pytest`, `httpx`, `pytest-mock`.

- [ ] **Step 2: Write failing API authentication and status tests**

```python
# learn_da_runner/tests/test_api.py
from fastapi.testclient import TestClient

from runner.main import app, get_provider


class FakeProvider:
    def ping(self) -> bool:
        return True

    def execute(self, request):
        return {
            "requestId": str(request.request_id),
            "executionId": "00000000-0000-0000-0000-000000000002",
            "status": "success",
            "stdout": "ok\n",
            "stderr": "",
            "errorType": None,
            "durationMs": 2,
            "outputTruncated": False,
        }


def test_execute_requires_runner_token(monkeypatch):
    monkeypatch.setenv("RUNNER_TOKEN", "t" * 32)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as client:
        response = client.post("/v1/executions", json={"requestId": "00000000-0000-0000-0000-000000000001", "code": "print('ok')", "language": "python", "source": "playground"})
    assert response.status_code == 401


def test_execute_returns_stable_contract(monkeypatch):
    monkeypatch.setenv("RUNNER_TOKEN", "t" * 32)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as client:
        response = client.post("/v1/executions", headers={"X-Runner-Token": "t" * 32}, json={"requestId": "00000000-0000-0000-0000-000000000001", "code": "print('ok')", "language": "python", "source": "playground"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

- [ ] **Step 3: Run Runner tests and confirm they fail**

Run: `cd learn_da_runner && uv run pytest tests/test_api.py -q`

Expected: FAIL because the Runner package does not exist.

- [ ] **Step 4: Implement token authentication and the HTTP surface**

Use `secrets.compare_digest` for `X-Runner-Token`. The execute endpoint must call the synchronous provider through `await anyio.to_thread.run_sync(provider.execute, payload)` so Docker waits never block the event loop. `/ready` returns `503` when `provider.ping()` is false; `/live` never calls Docker.

```python
@app.post("/v1/executions", response_model=RunnerExecutionResult)
async def execute(
    payload: RunnerExecutionRequest,
    _: None = Depends(require_runner_token),
    provider: ExecutionProvider = Depends(get_provider),
) -> RunnerExecutionResult:
    return await anyio.to_thread.run_sync(provider.execute, payload)
```

- [ ] **Step 5: Write failing provider policy tests**

Mock `docker.DockerClient.containers.run` and assert the exact arguments: `network_mode="none"`, `read_only=True`, `user="65532:65532"`, `pids_limit=64`, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges"]`, `mem_limit="256m"`, `nano_cpus=500_000_000`, and a 64 MiB `tmpfs` at `/tmp`. Add cases mapping non-zero exit to `error`, SDK timeout to `timeout`, and output clipping to 65,536 bytes with `outputTruncated=true`.

- [ ] **Step 6: Implement the provider and harden the execution image**

The provider must always remove the container in `finally`, close the Docker client, classify errors without returning exception internals, and clip decoded output before constructing the response. `learn_da/Dockerfile.sandbox` must create UID/GID `65532`, copy no application source, set `USER 65532:65532`, and retain only Python plus the approved Polars/DuckDB runtime dependencies.

- [ ] **Step 7: Run Runner unit tests**

Run: `cd learn_da_runner && uv run pytest -q`

Expected: PASS; no real Docker daemon is required for unit tests.

- [ ] **Step 8: Commit the Runner**

```bash
git add learn_da_runner learn_da/Dockerfile.sandbox
git commit -m "feat: add isolated execution runner service"
```

---

### Task 3: Replace API-Local Execution With The Runner Client

**Files:**
- Create: `learn_da/app/sandbox/client.py`
- Modify: `learn_da/app/sandbox/service.py`
- Modify: `learn_da/app/sandbox/__init__.py`
- Modify: `learn_da/app/playground/service.py`
- Modify: `learn_da/app/playground/router.py`
- Modify: `learn_da/main.py`
- Create: `learn_da/tests/unit/test_runner_client.py`
- Modify: `learn_da/tests/unit/test_playground_service.py`
- Modify: `learn_da/tests/unit/test_security_settings.py`
- Modify: `learn_da/tests/test_health.py`
- Delete: `learn_da/app/sandbox/local_runner.py`
- Delete: `learn_da/app/sandbox/docker_runner.py`

**Interfaces:**
- Consumes: Runner `POST /v1/executions` and `GET /ready`.
- Produces: `RunnerClient.execute(payload) -> SandboxExecutionResult`, `RunnerClient.is_ready() -> bool`.
- Produces: async `PlaygroundService.execute(payload)`.

- [ ] **Step 1: Write failing Runner client tests with `httpx.MockTransport`**

Cover successful deserialization, connect timeout, malformed Runner response and upstream `503`. All transport/protocol failures must raise one internal `RunnerUnavailableError`; submitted code and Runner response bodies must not appear in the exception string.

```python
async def test_runner_timeout_is_unavailable():
    async def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    client = RunnerClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), settings)
    with pytest.raises(RunnerUnavailableError, match="runner unavailable"):
        await client.execute(valid_request())
```

- [ ] **Step 2: Run the client test and confirm it fails**

Run: `cd learn_da && uv run pytest tests/unit/test_runner_client.py -q`

Expected: FAIL because `RunnerClient` does not exist.

- [ ] **Step 3: Implement a single reusable Runner client**

Create one `httpx.AsyncClient` in FastAPI lifespan, store `RunnerClient` on `app.state.runner_client`, and close it during shutdown. Send only the Task 1 JSON contract and `X-Runner-Token`; set the total timeout to `RUNNER_TIMEOUT_SECONDS`.

- [ ] **Step 4: Make Playground async and map infrastructure failure to 503**

`SandboxService` receives a `RunnerClient`; it has no runner selection logic. `PlaygroundService.execute` becomes async. The router catches `RunnerUnavailableError` and returns a response with HTTP `503`, `status=unavailable`, empty output and a stable `errorType="runner_unavailable"`.

After every accepted request, emit one structured audit log containing only `request_id`, `execution_id` when available, anonymous session ID hash, `source`, `status`, `error_type`, `duration_ms` and `output_truncated`. Never log submitted code, stdout/stderr, session cookies or Runner tokens. Log the same safe fields for rejected and unavailable requests so operational failures remain traceable.

- [ ] **Step 5: Remove API-local runners and obsolete API settings**

Delete `SANDBOX_DOCKER_ENABLED`, `SANDBOX_DOCKER_IMAGE`, `SANDBOX_DOCKER_HOST`, `SANDBOX_MEMORY_LIMIT_MB`, `SANDBOX_CPU_QUOTA` and `SANDBOX_LOCAL_ENABLED` from API `Settings`; their Runner equivalents live only in `learn_da_runner/runner/settings.py`. Remove the interim local-execution validator branch from Task 1 and replace its test with:

```python
def test_api_settings_expose_no_local_execution_switches():
    assert "SANDBOX_LOCAL_ENABLED" not in Settings.model_fields
    assert "SANDBOX_DOCKER_ENABLED" not in Settings.model_fields
```

Delete both local runner modules, then prove no execution import remains:

Run: `rg -n "LocalSubprocessRunner|DockerSandboxRunner|subprocess\.run|docker\.from_env|containers\.run" learn_da/app learn_da/main.py`

Expected: no matches.

- [ ] **Step 6: Add liveness/readiness tests**

`GET /live` returns `200` without external checks. `GET /ready` checks database and `RunnerClient.is_ready()`; it returns HTTP `503` with `runner=unhealthy` if Runner is down. Keep `/health` as a temporary alias to readiness for deployment compatibility and mark it deprecated in code comments.

- [ ] **Step 7: Run backend execution and health tests**

Run: `cd learn_da && uv run pytest tests/unit/test_runner_client.py tests/unit/test_playground_service.py tests/test_health.py -q`

Expected: PASS.

- [ ] **Step 8: Commit the API migration**

```bash
git add learn_da/app/sandbox learn_da/app/playground learn_da/main.py learn_da/tests
git commit -m "refactor: route playground execution through runner"
```

---

### Task 4: Require User Confirmation For Agent-Suggested Code

**Files:**
- Modify: `learn_da/app/agent/service.py`
- Modify: `learn_da/app/agent/schemas.py`
- Modify: `learn_da/tests/unit/test_agent_service.py`
- Modify: `learn_da_vue/src/api/playground.ts`
- Modify: `learn_da_vue/src/types/api.ts`
- Modify: `learn_da_vue/src/stores/playground.ts`
- Modify: `learn_da_vue/src/views/Playground.vue`
- Modify: `learn_da_vue/src/components/agent/AgentPanel.vue`
- Create: `learn_da_vue/src/stores/playground.spec.ts`
- Modify: `learn_da_vue/package.json`
- Modify: `learn_da_vue/package-lock.json`
- Create: `learn_da_vue/vitest.config.ts`
- Create: `learn_da_vue/src/test/setup.ts`

**Interfaces:**
- Produces: `loadAgentSuggestion(code)` sets code and the next execution source to `agent_suggested`.
- Produces: every execution request carries `requestId` and `source`; source resets to `playground` after the attempt.

- [ ] **Step 1: Write a failing backend test that Agent fix never executes code**

Inject a sandbox mock whose `execute` raises `AssertionError`. Call `AgentService.fix_code`; assert the response contains `fixedCode` and `verification is None`, and the mock was never called.

- [ ] **Step 2: Remove automatic verification from the Agent path**

Delete the sandbox dependency and `_verify_fix` call from `AgentService`. Keep `verification` temporarily nullable in the response for wire compatibility, but always return `None` in this phase.

- [ ] **Step 3: Establish the minimal frontend test runner**

Run: `cd learn_da_vue && npm install -D vitest jsdom`

Add `"test": "vitest"` to `package.json`, use the `jsdom` environment in `vitest.config.ts`, and load `src/test/setup.ts`. Do not add Vue component test utilities yet; the store/API/Markdown contracts are pure TypeScript tests.

- [ ] **Step 4: Write failing frontend store tests**

Mock `executeCode`, call `loadAgentSuggestion("print(1)")`, then `runCode()`. Assert the first payload contains `{source: "agent_suggested"}` and the next normal run contains `{source: "playground"}`. Assert rejected/unavailable responses are not stored as successes.

- [ ] **Step 5: Implement explicit source propagation**

`executeCode` generates no IDs itself; `runCode()` sends `requestId: crypto.randomUUID()`. `injectToPlayground` only loads the candidate through `loadAgentSuggestion`; it must never call `runCode`. Present the existing Run control as the explicit confirmation action.

- [ ] **Step 6: Render distinct execution states**

In `Playground.vue`, map:

```ts
const statusCopy: Record<ExecuteStatus, string> = {
  success: '运行完成',
  error: '代码运行出错',
  timeout: '运行超时',
  rejected: '该代码未获准运行',
  unavailable: '执行服务暂时不可用',
}
```

Do not describe `rejected` or `unavailable` as a learner code error. Keep layout changes limited to existing output/status surfaces.

- [ ] **Step 7: Run focused backend and frontend tests**

Run: `cd learn_da && uv run pytest tests/unit/test_agent_service.py -q`

Run: `cd learn_da_vue && npm test -- --run src/stores/playground.spec.ts`

Expected: PASS.

- [ ] **Step 8: Commit the confirmation flow**

```bash
git add learn_da/app/agent learn_da/tests/unit/test_agent_service.py learn_da_vue/package.json learn_da_vue/package-lock.json learn_da_vue/vitest.config.ts learn_da_vue/src
git commit -m "fix: require confirmation for agent-suggested execution"
```

---

### Task 5: Establish Signed Anonymous Sessions

**Files:**
- Create: `learn_da/app/core/session.py`
- Modify: `learn_da/app/core/__init__.py`
- Modify: `learn_da/main.py`
- Modify: `learn_da/app/analytics/schemas.py`
- Modify: `learn_da/app/analytics/router.py`
- Modify: `learn_da/app/analytics/service.py`
- Modify: `learn_da/app/learning/router.py`
- Modify: `learn_da/app/agent/schemas.py`
- Modify: `learn_da/app/agent/router.py`
- Create: `learn_da/tests/unit/test_anonymous_session.py`
- Create: `learn_da/tests/integration/test_session_scoping.py`

**Interfaces:**
- Produces: `get_anonymous_visitor_id(request: Request) -> str`.
- Produces: session cookie `learn_da_session`; production attributes are `HttpOnly`, `Secure`, `SameSite=Lax`.
- Changes: analytics/recommendation endpoints derive `visitor_id` from session, never payload/query.

- [ ] **Step 1: Write failing session creation and tamper tests**

Use `TestClient` to call an endpoint without a cookie, assert one signed cookie is returned, then reuse it and assert the visitor ID is stable. Modify one cookie byte and assert the server creates a new identity rather than accepting the forged value.

- [ ] **Step 2: Register `SessionMiddleware` and implement the dependency**

```python
ANONYMOUS_VISITOR_KEY = "anonymous_visitor_id"


def get_anonymous_visitor_id(request: Request) -> str:
    visitor_id = request.session.get(ANONYMOUS_VISITOR_KEY)
    if not isinstance(visitor_id, str):
        visitor_id = uuid4().hex
        request.session[ANONYMOUS_VISITOR_KEY] = visitor_id
    return visitor_id
```

Register `SessionMiddleware` with `secret_key=settings.SESSION_SECRET`, `session_cookie=settings.SESSION_COOKIE_NAME`, `https_only=settings.APP_ENV == "production"`, `same_site="lax"`, and `max_age=31_536_000`.

- [ ] **Step 3: Remove visitor ID from backend request schemas and routes**

Delete `visitor_id` from `EventTrackRequest`, `CodeSnapshotRequest`, and `RecommendationGuidanceRequest`. Remove visitor query parameters from Analytics and Learning routes. Inject `visitor_id: str = Depends(get_anonymous_visitor_id)` and pass it explicitly into service methods. Keep `completedLessons` temporarily because unified learning state belongs to the next Spec.

- [ ] **Step 4: Add cross-session isolation tests**

Create snapshots under two independent `TestClient` cookie jars. Assert each client lists only its own snapshot even when it supplies the other client’s old `visitorId` query parameter; the query parameter must be ignored or rejected, never used as authority.

- [ ] **Step 5: Run session and affected backend tests**

Run: `cd learn_da && uv run pytest tests/unit/test_anonymous_session.py tests/integration/test_session_scoping.py tests/unit/test_recommendation_phase3.py tests/unit/test_agent_recommendation_guidance.py -q`

Expected: PASS.

- [ ] **Step 6: Commit backend session ownership**

```bash
git add learn_da/app/core learn_da/app/analytics learn_da/app/learning/router.py learn_da/app/agent learn_da/main.py learn_da/tests
git commit -m "feat: scope learner APIs to signed sessions"
```

---

### Task 6: Migrate Frontend Session Calls And Govern Snapshots

**Files:**
- Modify: `learn_da_vue/src/api/index.ts`
- Modify: `learn_da_vue/src/api/analytics.ts`
- Modify: `learn_da_vue/src/api/recommendation.ts`
- Modify: `learn_da_vue/src/api/agent.ts`
- Modify: `learn_da_vue/src/types/api.ts`
- Modify: `learn_da_vue/src/views/Learning.vue`
- Modify: `learn_da_vue/src/views/LessonDetail.vue`
- Modify: `learn_da_vue/src/views/Playground.vue`
- Modify: `learn_da_vue/src/views/Dashboard.vue`
- Modify: `learn_da_vue/src/components/agent/AgentPanel.vue`
- Modify: `learn_da/app/analytics/schemas.py`
- Modify: `learn_da/app/analytics/repository.py`
- Modify: `learn_da/app/analytics/service.py`
- Modify: `learn_da/app/analytics/router.py`
- Create: `learn_da/tests/integration/test_snapshot_governance.py`

**Interfaces:**
- Produces frontend `SnapshotPage { items, total, page, pageSize }`.
- Produces repository `list_snapshots(visitor_id, lesson_slug, offset, limit) -> tuple[list[CodeSnapshot], int]`.
- Produces `prune_snapshots(visitor_id, per_session_limit, global_limit) -> None` in the same save transaction.

- [ ] **Step 1: Turn on cookie credentials and remove frontend visitor parameters**

Set Axios `withCredentials: true`. Remove `visitorId` from analytics event/snapshot types and all API signatures. Change recommendation parameters to `{ completedLessons, currentLesson? }`. Remove `getVisitorId` imports only from server API call sites; keep `src/lib/visitorId.ts` until the later learner-state migration because local progress may still use it.

- [ ] **Step 2: Write failing pagination and retention integration tests**

For one session, insert 105 snapshots, then assert total is 100 and page 1/page 2 contain non-overlapping 20-item slices in newest-first order. Configure a test global limit of 12, write snapshots across two sessions, and assert only the newest 12 non-deleted rows remain.

- [ ] **Step 3: Implement the paginated contract**

```python
class CodeSnapshotPage(BaseResponseModel):
    items: list[CodeSnapshotItem]
    total: int
    page: int
    page_size: int
```

`GET /analytics/snapshots` accepts `page: int = Query(1, ge=1)` and `page_size: int = Query(default, ge=1, le=max)`. Repository queries must filter `is_deleted == False`, order by `created_time DESC, id DESC`, and use `offset=(page-1)*page_size`.

- [ ] **Step 4: Enforce retention transactionally**

After creating a snapshot but before commit, soft-delete rows older than the newest 100 for that visitor, then rows older than the newest 10,000 globally. Use SQL subqueries by descending `created_time/id`; do not load all snapshot code into Python.

- [ ] **Step 5: Add high-risk route limits and exact input bounds**

Add settings and decorators:

- Analytics write: `30/minute` per session/IP.
- Snapshot save: `10/minute`.
- Snapshot list and Dashboard reads: `60/minute`.
- Recommendation and Agent guidance: existing `20/minute` Agent limit or `30/minute` recommendation limit.
- `eventType`: existing enum only; `lessonSlug` max 128; metadata fields max 256; snapshot code max 50,000; recommendation completed list max 500 items and each slug max 128.

- [ ] **Step 6: Update Playground snapshot pagination**

Load page 1 initially and append subsequent pages only through the existing snapshot/history interaction. Do not add a new dashboard or advanced navigation surface in this phase.

- [ ] **Step 7: Run backend and frontend verification**

Run: `cd learn_da && uv run pytest tests/integration/test_session_scoping.py tests/integration/test_snapshot_governance.py -q`

Run: `cd learn_da_vue && npm run type-check && npm run build-only`

Expected: PASS.

- [ ] **Step 8: Commit session consumers and storage governance**

```bash
git add learn_da/app/analytics learn_da/tests/integration learn_da_vue/src
git commit -m "feat: govern anonymous snapshots and session calls"
```

---

### Task 7: Replace Regex Markdown And Add Frontend Contract Tests

**Files:**
- Modify: `learn_da_vue/package.json`
- Modify: `learn_da_vue/package-lock.json`
- Replace: `learn_da_vue/src/lib/markdown.ts`
- Create: `learn_da_vue/src/lib/markdown.spec.ts`
- Create: `learn_da_vue/src/api/index.spec.ts`
- Create: `learn_da_vue/src/api/agent.spec.ts`
- Modify: `learn_da/app/agent/schemas.py`
- Modify: `learn_da/tests/unit/test_agent_service.py`

**Interfaces:**
- Produces: existing `renderMarkdown(md, options) -> string`, preserving `codeLoadable`, `codeRunnable`, and `newlineToBr` options.
- Produces: `npm test -- --run`.

- [ ] **Step 1: Install the parser and sanitizer into the existing test stack**

Run: `cd learn_da_vue && npm install markdown-it dompurify && npm install -D @types/markdown-it`

- [ ] **Step 2: Write failing XSS and behavior tests**

```ts
it.each([
  '<script>alert(1)</script>',
  '<img src=x onerror=alert(1)>',
  '[click](javascript:alert(1))',
  '<svg><a xlink:href="javascript:alert(1)">x</a></svg>',
])('removes dangerous markup: %s', (payload) => {
  const html = renderMarkdown(payload)
  expect(html).not.toMatch(/<script|onerror|javascript:|<svg/i)
})

it('keeps agent code actions as data-only buttons', () => {
  const html = renderMarkdown('```python\nprint(1)\n```', { codeRunnable: true })
  expect(html).toContain('class="code-btn run-btn"')
  expect(html).toContain('data-code=')
  expect(html).not.toContain('onclick=')
})
```

- [ ] **Step 3: Replace the regex renderer**

Create one `markdown-it({ html: false, linkify: false, breaks: options.newlineToBr })` instance per option set, override only the fence renderer to emit the existing data-only action buttons, then sanitize with DOMPurify. Allow only headings, paragraphs, lists, blockquotes, tables, `pre/code`, `div/span/button`, `a`, `br`, `hr`, `strong/em`; allow `class`, safe `href`, `target`, `rel`, `data-id`, `data-lang`, `data-code`. Permit relative links and `http/https`; reject every executable scheme. Always add `rel="noopener noreferrer"` to external links.

- [ ] **Step 4: Add request cancellation and Agent history tests**

In `src/api/index.spec.ts`, start two requests with the same key and assert the first receives `CancelledError` while a caller-provided `AbortSignal` also cancels the actual Axios request. In `src/api/agent.spec.ts`, assert `buildChatHistory` excludes system, streaming placeholder and the current user message, retaining at most the latest 20 completed messages. Adjust `buildChatHistory(messages, currentMessageId)` and the AgentPanel call accordingly. Change backend `AgentChatRequest.history` to `max_length=20` and add a service test proving 20 completed messages are accepted without duplicating the current message; this fixes the known fourth-message history contract failure on both sides of the wire.

- [ ] **Step 5: Run frontend tests, type check and build**

Run: `cd learn_da_vue && npm test -- --run`

Run: `cd learn_da_vue && npm run type-check && npm run build-only`

Expected: all tests pass and production assets build.

- [ ] **Step 6: Commit the trusted rendering boundary**

```bash
git add learn_da/app/agent/schemas.py learn_da/tests/unit/test_agent_service.py learn_da_vue/package.json learn_da_vue/package-lock.json learn_da_vue/src
git commit -m "fix: sanitize markdown and test frontend contracts"
```

---

### Task 8: Harden Production HTTP And Deployment Boundaries

**Files:**
- Create: `learn_da/app/core/client_ip.py`
- Modify: `learn_da/app/middleware/security.py`
- Modify: `learn_da/app/middleware/rate_limit.py`
- Modify: `learn_da/app/middleware/cors.py`
- Modify: `learn_da/main.py`
- Create: `learn_da/tests/unit/test_security_headers.py`
- Create: `learn_da/tests/unit/test_client_ip.py`
- Modify: `learn_da/tests/test_health.py`
- Modify: `docker-compose.prod.yml`
- Create: `docker-compose.runner-dev.yml`
- Modify: `deploy/nginx.conf`
- Modify: `deploy/.env.example`

**Interfaces:**
- Produces: `get_client_ip(request, trusted_proxy_ips) -> str`.
- Produces production CSP/HSTS/Permissions Policy and disabled docs/OpenAPI.
- Produces production services `backend`, `runner`, `web`; execution provider connection exists only in `runner`.

- [ ] **Step 1: Write failing header, docs and trusted-proxy tests**

Assert production responses contain:

```text
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'
Strict-Transport-Security: max-age=31536000; includeSubDomains
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
```

Assert `/docs` and `/openapi.json` return `404` in production. Assert an untrusted direct client cannot spoof `X-Forwarded-For`; only a direct peer listed in `TRUSTED_PROXY_IPS` may supply the first forwarded address.

- [ ] **Step 2: Implement environment-aware HTTP security**

Remove obsolete `X-XSS-Protection`. Construct FastAPI with `docs_url/openapi_url=None` in production unless `OPENAPI_ENABLED=true` was explicitly set after secure defaults. Enable CORS credentials only for explicit origins; reject the invalid combination `ALLOW_ALL_ORIGINS=true` and credentials.

- [ ] **Step 3: Use trusted client IP resolution in both limiters**

Replace direct `X-Forwarded-For` trust in custom middleware and configure SlowAPI’s key function through the same helper. High-risk endpoint limits remain effective without trusting arbitrary forwarding headers.

- [ ] **Step 4: Add the Runner deployment unit**

In `docker-compose.prod.yml`:

- Backend has `RUNNER_URL=http://runner:8080`, `SANDBOX_LOCAL_ENABLED=false`, no Docker socket and no Docker host credentials.
- Runner uses `learn_da_runner/Dockerfile`, receives `RUNNER_TOKEN` and production `RUNNER_DOCKER_HOST`, and is reachable only on the internal network.
- Production Compose must not mount `/var/run/docker.sock`.
- `docker-compose.runner-dev.yml` may mount the local socket only as an explicitly selected local testing override and must include a warning comment.
- Web depends on backend readiness; backend readiness depends logically on Runner health.

- [ ] **Step 5: Remove production docs proxy routes and tighten Nginx**

Delete `/docs` and `/openapi.json` locations, add `server_tokens off`, keep exact forwarding headers, and set execution proxy timeout to 10 seconds rather than the current 120-second blanket timeout.

- [ ] **Step 6: Run security and deployment validation**

Run: `cd learn_da && uv run pytest tests/unit/test_security_headers.py tests/unit/test_client_ip.py tests/test_health.py -q`

Run: `docker compose -f docker-compose.prod.yml config`

Expected: tests PASS; Compose config resolves with no API Docker socket and local execution disabled.

- [ ] **Step 7: Commit production hardening**

```bash
git add learn_da/app/core learn_da/app/middleware learn_da/main.py learn_da/tests docker-compose.prod.yml docker-compose.runner-dev.yml deploy
git commit -m "chore: harden production trust boundaries"
```

---

### Task 9: Establish CI, Debt Baselines And Release Evidence

**Files:**
- Modify: `learn_da/pyproject.toml`
- Modify: `learn_da/uv.lock`
- Create: `learn_da/scripts/check_mypy_baseline.py`
- Create: `.github/workflows/ci.yml`
- Modify: `learn_da_vue/Dockerfile`
- Modify: `learn_da/docs/README.md`
- Create: `learn_da/docs/security-execution-acceptance.md`

**Interfaces:**
- Produces: CI jobs `backend`, `runner`, `frontend`, `dependency-audit`, `compose-validation`.
- Produces: `uv run python scripts/check_mypy_baseline.py --max-errors 65`.

- [ ] **Step 1: Add dependency audit and the Mypy baseline checker**

Add `pip-audit` to backend dev dependencies. The checker runs `uv run mypy app config main.py`, parses `Found N errors`, exits non-zero if `N > 65`, and succeeds when errors decrease. Unit-test the parser with zero, 64, 65 and 66 errors before wiring it into CI.

- [ ] **Step 2: Apply Black once and verify behavior did not change**

Run: `cd learn_da && uv run black app config tests main.py scripts`

Run: `cd learn_da && uv run pytest -q`

Expected: the full backend suite passes after mechanical formatting.

- [ ] **Step 3: Make the frontend production image use the full build**

Replace any `npm run build-only` invocation in `learn_da_vue/Dockerfile` with `npm run build`, so `vue-tsc` cannot be skipped during image creation.

- [ ] **Step 4: Create the CI workflow**

CI must run on pull requests and pushes to `main`:

- Backend: `uv sync --extra dev`, `uv run black --check app config tests main.py scripts`, Mypy baseline checker, `uv run pytest -q`.
- Runner: sync and `uv run pytest -q` in `learn_da_runner`.
- Frontend: `npm ci`, `npm test -- --run`, `npm run build`.
- Audit: `uv run pip-audit`, `npm audit --audit-level=high`.
- Compose: `docker compose -f docker-compose.prod.yml config` with non-secret dummy values of at least 32 characters.

Do not place production secrets in workflow YAML or logs.

- [ ] **Step 5: Run the complete release gate locally**

Run:

```bash
cd learn_da && uv run black --check app config tests main.py scripts
cd learn_da && uv run python scripts/check_mypy_baseline.py --max-errors 65
cd learn_da && uv run pytest -q
cd learn_da_runner && uv run pytest -q
cd learn_da_vue && npm test -- --run
cd learn_da_vue && npm run build
docker compose -f docker-compose.prod.yml config
```

Expected: every command exits `0`.

- [ ] **Step 6: Perform controlled Runner acceptance tests**

Using the local-only Runner override, verify and record results for: normal output, syntax error, five-second timeout, 64 KiB output clipping, denied outbound network, denied read outside the temporary workspace, process/PID pressure, Runner shutdown returning API `503`, Markdown XSS corpus, forged session cookie, snapshot retention and rate-limit `429`. Record execution IDs and classifications, never submitted source code.

- [ ] **Step 7: Update project documentation**

`security-execution-acceptance.md` records environment, commands, result table and known residual risks. Update `docs/README.md` to mark the plan active or completed only according to actual execution status; do not mark it complete merely because CI files exist.

- [ ] **Step 8: Commit the release gate**

```bash
git add .github learn_da/pyproject.toml learn_da/uv.lock learn_da/scripts learn_da_vue/Dockerfile learn_da/docs
git commit -m "ci: enforce security and delivery gates"
```

---

## Final Review Gate

- [ ] Every requirement in `docs/superpowers/specs/2026-07-14-security-execution-delivery-gates-design.md` maps to at least one task above.
- [ ] `rg -n "LocalSubprocessRunner|DockerSandboxRunner|mocked|SANDBOX_USE_MOCK_WHEN_DISABLED" learn_da docker-compose.prod.yml` returns no production-path matches.
- [ ] API container has no Docker socket, Docker SDK execution call or local subprocess path.
- [ ] Agent suggestion cannot execute without the user pressing Run.
- [ ] Runner unavailable is observably different from learner code error.
- [ ] Session forgery, cross-session snapshot access, XSS payloads, untrusted forwarding headers and unbounded snapshots have regression tests.
- [ ] Full backend, Runner and frontend suites, production build, audits and Compose validation pass.
- [ ] Acceptance evidence documents residual risk: the Runner host/runtime remains a privileged security boundary and must be isolated and patched operationally.
