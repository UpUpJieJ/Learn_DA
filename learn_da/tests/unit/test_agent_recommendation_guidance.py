import pytest

from app.agent.prompts import build_recommendation_guidance_messages
from app.agent.schemas import RecommendationGuidanceRequest
from app.agent.service import AgentService
from app.learning.schemas import LearningRecommendation


class FakeRecommendationService:
    async def get_recommendation(
        self,
        visitor_id,
        completed_lessons,
        current_lesson_slug=None,
    ):
        from app.learning.recommendation import (
            LearningRecommendation as RuleRecommendation,
        )
        from app.learning.recommendation import RecommendationResponse

        return RecommendationResponse(
            primary=RuleRecommendation(
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


class EmptyRecommendationService:
    async def get_recommendation(
        self,
        visitor_id,
        completed_lessons,
        current_lesson_slug=None,
    ):
        from app.learning.recommendation import RecommendationResponse

        return RecommendationResponse(primary=None, alternatives=[])


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


def test_recommendation_guidance_prompt_includes_reason_and_exercise_format():
    recommendation = LearningRecommendation(
        type="review_lesson",
        targetSlug="polars-basics",
        targetTitle="Polars 基础",
        reason="你在当前课多次运行代码，建议回顾基础。",
        reasonCode="prerequisite_weak",
        priority=5,
        actionLabel="回顾课程",
    )

    messages = build_recommendation_guidance_messages(recommendation)
    content = messages[-1]["content"]

    assert "你在当前课多次运行代码" in content
    assert "解释建议：" in content
    assert "下一步练习：" in content


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


@pytest.mark.unit
async def test_recommendation_guidance_splits_llm_response(monkeypatch):
    service = AgentService(recommendation_service=FakeRecommendationService())

    async def fake_ask_llm(messages):
        return (
            "解释建议：先回顾基础，可以减少当前课程里的重复错误。\n\n"
            "下一步练习：修改一个表达式并观察结果，不要直接查看答案。"
        )

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.recommendation_guidance(
        RecommendationGuidanceRequest(visitorId="visitor-1")
    )

    assert result.used_fallback is False
    assert result.explanation == "先回顾基础，可以减少当前课程里的重复错误。"
    assert result.exercise_prompt == "修改一个表达式并观察结果，不要直接查看答案。"


@pytest.mark.unit
async def test_recommendation_guidance_fallback_handles_no_recommendation(monkeypatch):
    service = AgentService(recommendation_service=EmptyRecommendationService())

    async def fake_ask_llm(messages):
        return None

    monkeypatch.setattr(service, "_ask_llm", fake_ask_llm)

    result = await service.recommendation_guidance(
        RecommendationGuidanceRequest(visitorId="visitor-1")
    )

    assert result.used_fallback is True
    assert result.recommendation is None
    assert "当前没有明确推荐" in result.explanation
    assert result.exercise_prompt


@pytest.mark.unit
async def test_recommendation_guidance_endpoint_returns_rule_recommendation(client):
    response = await client.post(
        "/api/v1/agent/recommendation-guidance",
        json={
            "visitorId": "guidance-user",
            "completedLessons": ["polars-basics"],
            "currentLesson": "polars-expressions",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert "explanation" in body["data"]
    assert "usedFallback" in body["data"]
