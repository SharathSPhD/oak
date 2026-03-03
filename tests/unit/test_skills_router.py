import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime
from fastapi.testclient import TestClient
from api.main import app
from memory.interfaces import PromotionThresholdNotMet


client = TestClient(app)


def test_skills_router__list_with_query__returns_200_and_skills():
    """GET /api/skills?query=... returns matching skills."""
    skill_id = uuid4()
    mock_skill = MagicMock()
    mock_skill.id = skill_id
    mock_skill.name = "etl-pipeline"
    mock_skill.category = "etl"
    mock_skill.description = "ETL skill"
    mock_skill.trigger_keywords = ["pipeline"]
    mock_skill.status = "permanent"
    mock_skill.use_count = 5
    mock_skill.verified_on_problems = []
    mock_skill.filesystem_path = "/skills/etl.md"

    with patch("api.routers.skills.PostgreSQLSkillRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.find_by_keywords = AsyncMock(return_value=[mock_skill])

        response = client.get("/api/skills?query=pipeline&top_k=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "etl-pipeline"
        assert data[0]["category"] == "etl"


def test_skills_router__list_no_query__returns_200():
    """GET /api/skills without query returns all permanent skills."""
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: {
        "id": uuid4(),
        "name": "test-skill",
        "category": "etl",
        "description": "Test skill",
        "trigger_keywords": ["test"],
        "embedding": None,
        "status": "permanent",
        "use_count": 3,
        "verified_on_problems": [],
        "filesystem_path": "/skills/test.md",
        "deprecated_reason": None,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }[key]

    with patch("asyncpg.connect") as mock_connect:
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        mock_conn.fetch.return_value = [mock_row]

        response = client.get("/api/skills")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-skill"


def test_skills_router__promote__threshold_not_met__returns_409():
    """POST /api/skills/{skill_id}/promote returns 409 when threshold not met."""
    skill_id = uuid4()

    with patch("api.routers.skills.PostgreSQLSkillRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.promote = AsyncMock(side_effect=PromotionThresholdNotMet("Need 2, have 1"))

        response = client.post(f"/api/skills/{skill_id}/promote")

        assert response.status_code == 409
        assert "Need 2, have 1" in response.json()["detail"]


def test_skills_router__promote__not_found__returns_404():
    """POST /api/skills/{skill_id}/promote returns 404 when skill not found."""
    skill_id = uuid4()

    with patch("api.routers.skills.PostgreSQLSkillRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.promote = AsyncMock(side_effect=ValueError(f"Skill {skill_id} not found"))

        response = client.post(f"/api/skills/{skill_id}/promote")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
