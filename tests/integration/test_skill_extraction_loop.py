"""Integration test for the skill extraction → promotion loop.

Proves: problem completes → judge issues PASS → skill stored (probationary)
→ verified on 2+ problems → promote() transitions to permanent.

Uses mocked DB to avoid requiring a real PostgreSQL instance.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from memory.interfaces import PromotionThresholdNotMetError
from memory.skill_repository import PostgreSQLSkillRepository


@pytest.mark.integration
@pytest.mark.asyncio
async def test_skill_extraction_loop__full_lifecycle():
    """End-to-end: store probationary skill → verify on problems → promote to permanent."""
    skill_id = uuid4()
    problem_1 = uuid4()
    problem_2 = uuid4()

    with patch("asyncpg.connect") as mock_connect:
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn

        # -- Phase 1: Skill extracted after first problem PASS --
        # The Skill Extractor would INSERT into skills with status='probationary'
        mock_conn.fetchrow.return_value = {
            "id": skill_id,
            "name": "iris-classification",
            "category": "ml",
            "description": "Random Forest pipeline for tabular classification",
            "trigger_keywords": ["classification", "random forest", "tabular"],
            "embedding": None,
            "status": "probationary",
            "use_count": 1,
            "verified_on_problems": [problem_1],
            "filesystem_path": "/skills/probationary/iris_classification.md",
            "deprecated_reason": None,
            "created_at": None,
            "updated_at": None,
        }

        repo = PostgreSQLSkillRepository()

        # -- Phase 2: Try to promote with only 1 verified problem → must fail --
        mock_tx = MagicMock()
        mock_tx.__aenter__ = AsyncMock(return_value=None)
        mock_tx.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_conn.fetchrow.return_value = {"verified_on_problems": [problem_1]}

        with pytest.raises(PromotionThresholdNotMetError, match="Need 2"):
            await repo.promote(skill_id)

        mock_conn.execute.assert_not_called()
        mock_conn.close.assert_called()
        mock_conn.reset_mock()

        # -- Phase 3: Second problem verifies the skill → now at threshold --
        mock_connect.return_value = mock_conn
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_conn.fetchrow.return_value = {
            "verified_on_problems": [problem_1, problem_2],
        }

        await repo.promote(skill_id)

        mock_conn.execute.assert_called_once()
        update_sql = mock_conn.execute.call_args[0][0]
        assert "UPDATE skills SET status='permanent'" in update_sql
        mock_conn.close.assert_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_skill_extraction_loop__find_retrieves_promoted_skill():
    """After promotion, skill is findable via find_by_keywords."""
    skill_id = uuid4()
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: {
        "id": skill_id,
        "name": "iris-classification",
        "category": "ml",
        "description": "Random Forest pipeline for tabular classification",
        "trigger_keywords": ["classification", "random forest"],
        "embedding": None,
        "status": "permanent",
        "use_count": 3,
        "verified_on_problems": [uuid4(), uuid4()],
        "filesystem_path": "/skills/permanent/iris_classification.md",
        "deprecated_reason": None,
        "created_at": None,
        "updated_at": None,
    }[key]

    with patch("asyncpg.connect") as mock_connect:
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        mock_conn.fetch.return_value = [mock_row]

        repo = PostgreSQLSkillRepository()
        results = await repo.find_by_keywords("classification", category="ml")

        assert len(results) == 1
        assert results[0].status == "permanent"
        assert results[0].name == "iris-classification"
        query = mock_conn.fetch.call_args[0][0]
        assert "status != 'deprecated'" in query


@pytest.mark.integration
@pytest.mark.asyncio
async def test_skill_extraction_loop__deprecate__excludes_from_search():
    """Deprecated skills are excluded from find_by_keywords results."""
    with patch("asyncpg.connect") as mock_connect:
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        mock_conn.fetch.return_value = []

        repo = PostgreSQLSkillRepository()

        skill_id = uuid4()
        await repo.deprecate(skill_id, "Superseded by v2")

        deprecate_sql = mock_conn.execute.call_args[0][0]
        assert "status='deprecated'" in deprecate_sql
        assert "deprecated_reason" in deprecate_sql

        mock_conn.reset_mock()
        mock_connect.return_value = mock_conn
        mock_conn.fetch.return_value = []

        results = await repo.find_by_keywords("classification")
        assert results == []
        search_sql = mock_conn.fetch.call_args[0][0]
        assert "status != 'deprecated'" in search_sql
