from pathlib import Path

import pytest

from app.core.content_loader import load_catalog, load_lesson_from_file
from app.learning.recommendation import RecommendationService
from app.learning.repository import LearningRepository


def test_load_catalog_reads_platform_topics_and_tracks(tmp_path: Path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "catalog.yml").write_text(
        """
platform:
  name: LearnHub
  title: General Learning
topics:
  - key: programming
    label: Programming
tracks:
  - key: python-basics
    topic: programming
    label: Python Basics
    start_lesson: python-functions
""".strip(),
        encoding="utf-8",
    )

    catalog = load_catalog(content_dir)

    assert catalog["platform"]["name"] == "LearnHub"
    assert catalog["topics"][0]["key"] == "programming"
    assert catalog["tracks"][0]["key"] == "python-basics"


def test_default_catalog_includes_existing_data_analysis_tracks():
    catalog = load_catalog()

    assert catalog["topics"][0]["key"] == "data-analysis"
    track_keys = {track["key"] for track in catalog["tracks"]}
    assert {"polars_basics", "duckdb_basics", "combined_workflow"}.issubset(track_keys)


def test_lesson_loader_preserves_general_topic_metadata(tmp_path: Path):
    lesson_file = tmp_path / "python-functions.md"
    lesson_file.write_text(
        """
---
id: 101
slug: python-functions
title: Python Functions
topic: programming
category: python
track: python-basics
difficulty: beginner
prerequisites: [python-variables]
recommended_next: [python-modules]
skill_tags: [function, return]
is_review_friendly: true
is_branch_point: false
---

# Python Functions
""".strip(),
        encoding="utf-8",
    )

    lesson = load_lesson_from_file(lesson_file)

    assert lesson is not None
    assert lesson["topic"] == "programming"
    assert lesson["track"] == "python-basics"
    assert lesson["prerequisites"] == ["python-variables"]
    assert lesson["recommended_next"] == ["python-modules"]
    assert lesson["skill_tags"] == ["function", "return"]


@pytest.mark.unit
async def test_lessons_endpoint_filters_by_topic_and_track(client):
    resp = await client.get(
        "/api/v1/lessons",
        params={"topic": "data-analysis", "track": "polars_basics"},
    )
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]
    assert {lesson["topic"] for lesson in body["data"]} == {"data-analysis"}
    assert {lesson["track"] for lesson in body["data"]} == {"polars_basics"}


@pytest.mark.unit
async def test_catalog_endpoint_returns_platform_topics_and_tracks(client):
    resp = await client.get("/api/v1/catalog")
    body = resp.json()

    assert resp.status_code == 200
    assert body["code"] == 200
    assert body["data"]["platform"]["name"]
    assert body["data"]["topics"]
    assert body["data"]["tracks"]


def test_recommendation_metadata_uses_lesson_model_fields():
    service = RecommendationService(repository=LearningRepository())

    metadata = service._get_lesson_metadata()

    assert metadata["polars-basics"].track == "polars_basics"
    assert "duckdb-analytics" in metadata["polars-basics"].recommended_next
    assert "dataframe_basics" in metadata["polars-basics"].skill_tags
