# Agent Fix Sandbox Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/agent/fix` optionally verify model-generated fixed code through the existing sandbox and return the verification result to the frontend.

**Architecture:** Keep the existing `/agent/fix` contract backward-compatible by adding optional response fields instead of changing existing `fixedCode`, `explanation`, `model`, and `usedFallback`. `AgentService` will accept an injectable `SandboxService`, extract the code block from the model response, run only that extracted code when a real LLM response exists, and skip sandbox execution for fallback responses.

**Tech Stack:** FastAPI, Pydantic v2, existing `SandboxService`, OpenAI SDK, pytest/httpx.

---

## File Structure

- Modify `learn_da/app/agent/schemas.py`: add `AgentRunVerification` and optional `verification` field on `FixCodeResponse`.
- Modify `learn_da/app/agent/service.py`: inject `SandboxService`, add `_verify_fixed_code()`, call it from `fix_code()` when LLM returns content.
- Modify `learn_da/tests/test_health.py`: keep smoke coverage and assert fallback fix does not verify.
- Create `learn_da/tests/unit/test_agent_service.py`: focused service tests with fake LLM output and fake sandbox runners.

## Task 1: Add Response Schema for Verification

**Files:**
- Modify: `learn_da/app/agent/schemas.py`
- Test: `learn_da/tests/unit/test_agent_service.py`

- [ ] **Step 1: Write a failing schema test**

Create `learn_da/tests/unit/test_agent_service.py` with this initial test:

```python
from app.agent.schemas import AgentRunVerification, FixCodeResponse


def test_fix_code_response_serializes_optional_verification():
    response = FixCodeResponse(
        fixed_code="print('ok')",
        explanation="修复完成",
        model="test-model",
        used_fallback=False,
        verification=AgentRunVerification(
            verified=True,
            status="success",
            stdout="ok\n",
            stderr="",
            execution_time=12,
            used_sandbox="fake",
        ),
    )

    body = response.model_dump(by_alias=True)

    assert body["fixedCode"] == "print('ok')"
    assert body["verification"]["verified"] is True
    assert body["verification"]["executionTime"] == 12
    assert body["verification"]["usedSandbox"] == "fake"
```

Run:

```bash
uv run pytest tests/unit/test_agent_service.py::test_fix_code_response_serializes_optional_verification -q
```

Expected: FAIL with `ImportError` because `AgentRunVerification` does not exist yet.

- [ ] **Step 2: Add schema models**

Update `learn_da/app/agent/schemas.py`:

```python
class AgentRunVerification(BaseResponseModel):
    verified: bool
    status: str
    stdout: str = ""
    stderr: str = ""
    execution_time: int
    used_sandbox: str
```

Then update `FixCodeResponse`:

```python
class FixCodeResponse(BaseResponseModel):
    fixed_code: str
    explanation: str
    model: str
    used_fallback: bool = False
    verification: AgentRunVerification | None = None
```

- [ ] **Step 3: Verify schema test passes**

Run:

```bash
uv run pytest tests/unit/test_agent_service.py::test_fix_code_response_serializes_optional_verification -q
```

Expected: PASS.

## Task 2: Verify LLM Fixed Code Through Sandbox

**Files:**
- Modify: `learn_da/app/agent/service.py`
- Test: `learn_da/tests/unit/test_agent_service.py`

- [ ] **Step 1: Write a failing service test for successful verification**

Add to `learn_da/tests/unit/test_agent_service.py`:

```python
import pytest

from app.agent.schemas import FixCodeRequest
from app.agent.service import AgentService
from app.sandbox.schemas import SandboxExecutionResult


class FakeSandboxService:
    def __init__(self, result):
        self.result = result
        self.executed_code = None

    def execute(self, code: str):
        self.executed_code = code
        return self.result


@pytest.mark.unit
async def test_fix_code_verifies_llm_code_block(monkeypatch):
    service = AgentService(
        sandbox_service=FakeSandboxService(
            SandboxExecutionResult(
                status="success",
                stdout="ok\n",
                stderr="",
                execution_time=7,
                used_sandbox="fake",
            )
        )
    )

    async def fake_ask_llm(messages):
        return "原因：变量未定义。\n```python\nprint('ok')\n```"

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.fix_code(
        FixCodeRequest(
            code="print(df)",
            errorMessage="NameError: name 'df' is not defined",
        )
    )

    assert result.fixed_code == "print('ok')"
    assert result.used_fallback is False
    assert result.verification is not None
    assert result.verification.verified is True
    assert result.verification.status == "success"
    assert result.verification.stdout == "ok\n"
    assert service.sandbox_service.executed_code == "print('ok')"
```

Run:

```bash
uv run pytest tests/unit/test_agent_service.py::test_fix_code_verifies_llm_code_block -q
```

Expected: FAIL because `AgentService.__init__()` does not accept `sandbox_service` and `FixCodeResponse` does not populate `verification`.

- [ ] **Step 2: Inject sandbox service and add verification helper**

Update the imports in `learn_da/app/agent/service.py`:

```python
from app.sandbox import SandboxService
from app.sandbox.schemas import SandboxExecutionResult
```

Update `AgentService.__init__`:

```python
class AgentService:
    def __init__(self, sandbox_service: SandboxService | None = None) -> None:
        self.model = settings.effective_llm_model
        self.sandbox_service = sandbox_service or SandboxService()
```

Add `AgentRunVerification` to the `.schemas` import list.

Add this method to `AgentService`:

```python
    def _verify_fixed_code(self, code: str) -> AgentRunVerification:
        try:
            result = self.sandbox_service.execute(code)
        except Exception as exc:
            return AgentRunVerification(
                verified=False,
                status="error",
                stdout="",
                stderr=str(exc),
                execution_time=0,
                used_sandbox="none",
            )

        return self._verification_from_result(result)

    def _verification_from_result(
        self,
        result: SandboxExecutionResult,
    ) -> AgentRunVerification:
        return AgentRunVerification(
            verified=result.status == "success",
            status=result.status,
            stdout=result.stdout,
            stderr=result.stderr,
            execution_time=result.execution_time,
            used_sandbox=result.used_sandbox,
        )
```

Update the LLM-success branch in `fix_code()`:

```python
        if content:
            fixed_code = self._extract_code_block(content) or payload.code
            return FixCodeResponse(
                fixed_code=fixed_code,
                explanation=content,
                model=self.model,
                used_fallback=False,
                verification=self._verify_fixed_code(fixed_code),
            )
```

- [ ] **Step 3: Verify service test passes**

Run:

```bash
uv run pytest tests/unit/test_agent_service.py::test_fix_code_verifies_llm_code_block -q
```

Expected: PASS.

## Task 3: Handle Sandbox Failure and Fallback Behavior

**Files:**
- Modify: `learn_da/app/agent/service.py`
- Modify: `learn_da/tests/test_health.py`
- Test: `learn_da/tests/unit/test_agent_service.py`

- [ ] **Step 1: Write a failing service test for verification failure**

Add to `learn_da/tests/unit/test_agent_service.py`:

```python
@pytest.mark.unit
async def test_fix_code_marks_verification_false_when_sandbox_errors(monkeypatch):
    service = AgentService(
        sandbox_service=FakeSandboxService(
            SandboxExecutionResult(
                status="error",
                stdout="",
                stderr="NameError: still broken",
                execution_time=5,
                used_sandbox="fake",
            )
        )
    )

    async def fake_ask_llm(messages):
        return "修复建议：\n```python\nprint(df)\n```"

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.fix_code(
        FixCodeRequest(
            code="print(df)",
            errorMessage="NameError: name 'df' is not defined",
        )
    )

    assert result.used_fallback is False
    assert result.verification is not None
    assert result.verification.verified is False
    assert result.verification.status == "error"
    assert "still broken" in result.verification.stderr
```

Run:

```bash
uv run pytest tests/unit/test_agent_service.py::test_fix_code_marks_verification_false_when_sandbox_errors -q
```

Expected: PASS if Task 2 implementation maps sandbox status correctly; if not, FAIL and fix `_verification_from_result()`.

- [ ] **Step 2: Assert fallback skips verification**

Update `test_agent_fix_returns_structured_fallback` in `learn_da/tests/test_health.py`:

```python
    assert body["data"]["usedFallback"] is True
    assert body["data"]["verification"] is None
```

Run:

```bash
uv run pytest tests/test_health.py::test_agent_fix_returns_structured_fallback -q
```

Expected: PASS because fallback response should not call sandbox or claim verification.

## Task 4: Router Contract Smoke Test

**Files:**
- Modify: `learn_da/tests/test_health.py`

- [ ] **Step 1: Add response-shape assertion without forcing live LLM**

Keep `test_agent_fix_returns_structured_fallback` as the stable route smoke test. Do not add live model tests in `test_health.py`; live model behavior is environment-dependent and should stay in service tests with monkeypatched `_ask_llm`.

- [ ] **Step 2: Run Agent smoke tests**

Run:

```bash
uv run pytest tests/test_health.py::test_agent_chat_uses_learning_toolchain tests/test_health.py::test_agent_chat_accepts_history_and_context tests/test_health.py::test_agent_fix_returns_structured_fallback tests/test_health.py::test_agent_explain_returns_structured_fallback -q
```

Expected: PASS.

## Task 5: Final Verification

**Files:**
- Test only.

- [ ] **Step 1: Run focused service tests**

Run:

```bash
uv run pytest tests/unit/test_agent_service.py -q
```

Expected: all Agent service unit tests pass.

- [ ] **Step 2: Run backend smoke tests**

Run:

```bash
uv run pytest tests/test_health.py -q
```

Expected: all smoke tests pass.

- [ ] **Step 3: Run full backend test suite**

Run:

```bash
uv run pytest -q
```

Expected: full backend suite passes.

## Self-Review

- Spec coverage: The plan adds verification to `/agent/fix`, skips verification for fallback, handles sandbox success and failure, and preserves the existing frontend-compatible response fields.
- Placeholder scan: No placeholders remain; every code-changing step includes concrete code.
- Type consistency: Response aliases remain camelCase through `BaseResponseModel`: `fixedCode`, `usedFallback`, `executionTime`, `usedSandbox`.

