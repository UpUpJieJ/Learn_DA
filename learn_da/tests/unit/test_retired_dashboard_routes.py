import pytest


@pytest.mark.parametrize("route", [
    "analytics/learning-progress", "analytics/home-stats", "analytics/user-profile",
    "analytics/user-lesson-stats", "analytics/daily-trend", "analytics/category-progress",
    "lessons/all",
])
async def test_obsolete_dashboard_and_duplicate_routes_are_retired(client, route):
    response = await client.get(f"/api/v1/{route}")
    assert response.status_code == 404
