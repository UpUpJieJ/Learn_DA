# Round 4 Agent-Guided Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Agent-guided layer on top of the existing rule-based recommendation system so the Agent can explain the current recommendation and generate a small next exercise from the user's current learning state.

**Architecture:** Keep `RecommendationService` as the source of truth for ranking and recommendation types. Add a thin Agent-facing orchestration path that fetches the rule recommendation, injects it into prompts, and returns structured coaching output without changing the Phase 3 recommendation priority chain.

**Tech Stack:** FastAPI, Pydantic v2, pytest, existing `AgentService`, existing `RecommendationService`, existing analytics data.

---

## File Structure

- Modify `learn_da/app/agent/schemas.py`: add request/response models for recommendation guidance.
- Modify `learn_da/app/agent/prompts.py`: add prompt builders for recommendation explanation and next exercise generation.
- Modify `learn_da/app/agent/service.py`: add a method that calls `RecommendationService`, asks the LLM for coaching text, and falls back to deterministic text.
- Modify `learn_da/app/agent/router.py`: add a new endpoint under `/api/v1/agent/recommendation-guidance`.
- Modify `learn_da_vue/src/components/agent/AgentPanel.vue`: add a quick action that asks why the current recommendation was shown.
- Create `learn_da/tests/unit/test_agent_recommendation_guidance.py`: service and endpoint tests.
- Create or modify frontend API tests if a frontend test harness exists for the Agent API.

## Scope

This round does:
- Explain the current Phase 3 recommendation in learner-friendly language.
- Generate one small practice prompt tied to the recommended lesson.
- Preserve deterministic fallbacks when no LLM key is configured.

This round does not:
- Replace rule-based ranking with LLM ranking.
- Store long-term user preference profiles.
- Add new analytics tables.

### Task 1: Agent Guidance Schemas

**Files:**
- Modify: `learn_da/app/agent/schemas.py`
- Test: `learn_da/tests/unit/test_agent_recommendation_guidance.py`

- [x] **Step 1: Write the failing schema serialization test**

```python
from app.agent.schemas import RecommendationGuidanceRequest


def test_recommendation_guidance_request_accepts_camel_case_context():
    req = RecommendationGuidanceRequest.model_validate(
        {
            "visitorId": "visitor-1",
            "completedLessons": ["polars-basics"],
            "currentLesson": "polars-expressions",
        }
    )

    assert req.visitor_id == "visitor-1"
    assert req.completed_lessons == ["polars-basics"]
    assert req.current_lesson == "polars-expressions"
```

- [x] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_agent_recommendation_guidance.py::test_recommendation_guidance_request_accepts_camel_case_context -q`

Expected: FAIL because `RecommendationGuidanceRequest` does not exist.

- [x] **Step 3: Add the minimal schemas**

```python
from pydantic import Field
from app.learning.schemas import LearningRecommendation
from app.utils.base_response import BaseResponseModel


class RecommendationGuidanceRequest(BaseResponseModel):
    visitor_id: str = Field(..., alias="visitorId")
    completed_lessons: list[str] = Field(default_factory=list, alias="completedLessons")
    current_lesson: str | None = Field(None, alias="currentLesson")


class RecommendationGuidanceResponse(BaseResponseModel):
    recommendation: LearningRecommendation | None = None
    explanation: str
    exercise_prompt: str | None = None
    model: str
    used_fallback: bool = False
```

- [x] **Step 4: Run the schema test**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_agent_recommendation_guidance.py::test_recommendation_guidance_request_accepts_camel_case_context -q`

Expected: PASS.

### Task 2: Prompt Builder

**Files:**
- Modify: `learn_da/app/agent/prompts.py`
- Test: `learn_da/tests/unit/test_agent_recommendation_guidance.py`

- [x] **Step 1: Write the failing prompt test**

```python
from app.agent.prompts import build_recommendation_guidance_messages
from app.learning.schemas import LearningRecommendation


def test_recommendation_guidance_prompt_includes_reason_and_exercise_format():
    rec = LearningRecommendation(
        type="review_lesson",
        targetSlug="polars-basics",
        targetTitle="Polars 基础",
        reason="你在当前课多次运行代码，建议回顾基础。",
        reasonCode="prerequisite_weak",
        priority=5,
        actionLabel="回顾课程",
    )

    messages = build_recommendation_guidance_messages(rec)
    content = messages[-1]["content"]

    assert "你在当前课多次运行代码" in content
    assert "解释建议：" in content
    assert "下一步练习：" in content
```

- [x] **Step 2: Run the prompt test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_agent_recommendation_guidance.py::test_recommendation_guidance_prompt_includes_reason_and_exercise_format -q`

Expected: FAIL because the prompt builder does not exist.

- [x] **Step 3: Add the prompt builder**

```python
def build_recommendation_guidance_messages(recommendation) -> list[dict[str, str]]:
    if recommendation is None:
        user_content = (
            "当前没有明确推荐。请按以下格式回复：\n"
            "解释建议：说明为什么现在适合自由浏览或继续当前课程。\n\n"
            "下一步练习：给一个 5 到 10 分钟的小练习。"
        )
    else:
        user_content = (
            "请解释这条学习建议，并给一个小练习。\n\n"
            f"建议类型：{recommendation.type}\n"
            f"目标课程：{recommendation.target_title}\n"
            f"规则理由：{recommendation.reason}\n"
            f"优先级：{recommendation.priority}\n\n"
            "必须按以下格式回复：\n"
            "解释建议：用 2 到 4 句话说明为什么推荐它。\n\n"
            "下一步练习：给一个 5 到 10 分钟的小练习，不要直接给答案。"
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
```

- [x] **Step 4: Run the prompt test**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_agent_recommendation_guidance.py::test_recommendation_guidance_prompt_includes_reason_and_exercise_format -q`

Expected: PASS.

### Task 3: Agent Service Orchestration

**Files:**
- Modify: `learn_da/app/agent/service.py`
- Test: `learn_da/tests/unit/test_agent_recommendation_guidance.py`

- [x] **Step 1: Write the failing service fallback test**

```python
import pytest

from app.agent.schemas import RecommendationGuidanceRequest
from app.agent.service import AgentService


class FakeRecommendationService:
    async def get_recommendation(self, visitor_id, completed_lessons, current_lesson_slug=None):
        from app.learning.recommendation import LearningRecommendation, RecommendationResponse

        return RecommendationResponse(
            primary=LearningRecommendation(
                type="review_lesson",
                target_slug="polars-basics",
                target_title="Polars 基础",
                reason="你在当前课多次运行代码，建议回顾基础。",
                reason_code="prerequisite_weak",
                priority=5,
                action_label="回顾课程",
            ),
            alternatives=[],
        )


@pytest.mark.unit
async def test_recommendation_guidance_falls_back_without_llm(monkeypatch):
    service = AgentService(recommendation_service=FakeRecommendationService())

    async def fake_ask_llm(messages):
        return None

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.recommendation_guidance(
        RecommendationGuidanceRequest(
            visitorId="visitor-1",
            completedLessons=["polars-basics"],
            currentLesson="polars-expressions",
        )
    )

    assert result.used_fallback is True
    assert result.recommendation.target_slug == "polars-basics"
    assert "Polars 基础" in result.explanation
    assert result.exercise_prompt
```

- [x] **Step 2: Run the service test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_agent_recommendation_guidance.py::test_recommendation_guidance_falls_back_without_llm -q`

Expected: FAIL because `AgentService` does not accept `recommendation_service` and has no `recommendation_guidance` method.

- [x] **Step 3: Add service dependency and method**

Add a `recommendation_service` optional dependency to `AgentService.__init__`, defaulting to `RecommendationService(repository=LearningRepository())` only when used by the new method. Add:

```python
async def recommendation_guidance(self, payload: RecommendationGuidanceRequest):
    response = await self.recommendation_service.get_recommendation(
        visitor_id=payload.visitor_id,
        completed_lessons=payload.completed_lessons,
        current_lesson_slug=payload.current_lesson,
    )
    recommendation = response.primary
    messages = build_recommendation_guidance_messages(recommendation)
    content = await self._ask_llm(messages)
    if content:
        explanation, exercise = self._split_guidance_content(content)
        return RecommendationGuidanceResponse(
            recommendation=recommendation,
            explanation=explanation,
            exercise_prompt=exercise,
            model=self.model,
            used_fallback=False,
        )
    return RecommendationGuidanceResponse(
        recommendation=recommendation,
        explanation=self._fallback_recommendation_explanation(recommendation),
        exercise_prompt=self._fallback_recommendation_exercise(recommendation),
        model=self.model,
        used_fallback=True,
    )
```

- [x] **Step 4: Run the service test**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_agent_recommendation_guidance.py::test_recommendation_guidance_falls_back_without_llm -q`

Expected: PASS.

### Task 4: FastAPI Endpoint

**Files:**
- Modify: `learn_da/app/agent/router.py`
- Test: `learn_da/tests/unit/test_agent_recommendation_guidance.py`

- [x] **Step 1: Write the failing endpoint test**

```python
@pytest.mark.unit
async def test_recommendation_guidance_endpoint_returns_rule_recommendation(client):
    resp = await client.post(
        "/api/v1/agent/recommendation-guidance",
        json={
            "visitorId": "guidance-user",
            "completedLessons": ["polars-basics"],
            "currentLesson": "polars-expressions",
        },
    )
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert "explanation" in body["data"]
    assert "usedFallback" in body["data"]
```

- [x] **Step 2: Run the endpoint test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_agent_recommendation_guidance.py::test_recommendation_guidance_endpoint_returns_rule_recommendation -q`

Expected: FAIL with 404.

- [x] **Step 3: Add the endpoint**

```python
@router.post("/recommendation-guidance", response_model=StdResp[RecommendationGuidanceResponse])
@limiter.limit(settings.RATE_LIMIT_AGENT_CHAT)
async def recommendation_guidance(
    request: Request,
    payload: RecommendationGuidanceRequest,
    service: AgentService = Depends(get_agent_service),
):
    return StdResp.success(data=await service.recommendation_guidance(payload))
```

- [x] **Step 4: Run endpoint and full agent tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_agent_service.py tests/unit/test_agent_recommendation_guidance.py -q`

Expected: all tests pass.

### Task 5: Frontend Quick Action

**Files:**
- Modify: `learn_da_vue/src/api/agent.ts`
- Modify: `learn_da_vue/src/components/agent/AgentPanel.vue`

- [x] **Step 1: Add API wrapper**

Add:

```ts
export async function getRecommendationGuidance(payload: {
  visitorId: string
  completedLessons: string[]
  currentLesson?: string
}) {
  return post<RecommendationGuidanceResponse>("/agent/recommendation-guidance", payload)
}
```

- [x] **Step 2: Add response type**

Add to `learn_da_vue/src/types/api.ts`:

```ts
export interface RecommendationGuidanceResponse {
  recommendation: LearningRecommendation | null
  explanation: string
  exercisePrompt?: string | null
  model: string
  usedFallback: boolean
}
```

- [x] **Step 3: Add quick action to Agent panel**

Add a quick action labeled `解释推荐` that calls the new API using the current visitor id, completed lessons, and current lesson slug. Render the returned `explanation` as an assistant message and append `exercisePrompt` when present.

- [x] **Step 4: Run frontend build**

Run: `npm run build` from `learn_da_vue`.

Expected: build passes.

### Task 6: Final Verification

**Files:**
- No new files.

- [x] **Step 1: Run backend tests**

Run: `.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_cache\tmp-run`

Expected: all tests pass.

- [x] **Step 2: Run frontend build**

Run: `npm run build`

Expected: build passes.

- [x] **Step 3: Commit**

```bash
git add learn_da/app/agent learn_da/tests/unit/test_agent_recommendation_guidance.py learn_da_vue/src
git commit -m "feat: add agent-guided learning recommendations"
```

## Self-Review

- Spec coverage: the plan covers schema, prompt, service, endpoint, frontend action, fallback behavior, and verification.
- Placeholder scan: no `TBD`, `TODO`, or open-ended implementation placeholders remain.
- Type consistency: request fields are `visitor_id`, `completed_lessons`, `current_lesson`; JSON aliases are `visitorId`, `completedLessons`, `currentLesson`.
