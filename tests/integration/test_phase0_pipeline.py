"""Integration test: Phase 0 exit criterion — 1 CSV in -> PG table + app.py out.

Uses unittest.mock to avoid needing a real database in CI.
Run with: pytest tests/integration/test_phase0_pipeline.py -v
"""
import pathlib
import textwrap

import pytest
from unittest.mock import patch


@pytest.fixture
def sample_csv(tmp_path: pathlib.Path) -> pathlib.Path:
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(
        textwrap.dedent("""
        id,name,value,category
        1,alpha,10.5,A
        2,beta,20.0,B
        3,gamma,30.1,A
    """).strip()
    )
    return csv_file


def test_phase0_pipeline__csv_to_app__app_py_generated(
    sample_csv: pathlib.Path, tmp_path: pathlib.Path
):
    """Core Phase 0 exit criterion: CSV input produces a valid app.py."""
    from scripts.ingest_csv import ingest_csv

    with patch("scripts.ingest_csv._load_to_postgres", return_value=3) as mock_load:
        result = ingest_csv(
            csv_path=str(sample_csv),
            problem_uuid="test-uuid-0001",
            output_dir=str(tmp_path / "output"),
            db_url="postgresql://oak:oak@localhost:5432/oak",
        )

    app_path = pathlib.Path(result["app_path"])
    assert app_path.exists(), "app.py was not generated"
    app_content = app_path.read_text()
    assert "streamlit" in app_content.lower()
    assert "problem_test_uuid_0001" in app_content

    assert result["table_name"] == "problem_test_uuid_0001"
    assert result["columns"] == ["id", "name", "value", "category"]
    assert result["rows_loaded"] == 3
    mock_load.assert_called_once()


def test_phase0_pipeline__missing_csv__raises_file_not_found(tmp_path: pathlib.Path):
    from scripts.ingest_csv import ingest_csv

    with pytest.raises(FileNotFoundError):
        ingest_csv("/nonexistent/path.csv", "uuid-001", str(tmp_path))


def test_phase0_pipeline__app_py__contains_table_name(
    sample_csv: pathlib.Path, tmp_path: pathlib.Path
):
    from scripts.ingest_csv import ingest_csv

    with patch("scripts.ingest_csv._load_to_postgres", return_value=3):
        result = ingest_csv(
            csv_path=str(sample_csv),
            problem_uuid="abc-123",
            output_dir=str(tmp_path / "out"),
        )
    content = pathlib.Path(result["app_path"]).read_text()
    assert "problem_abc_123" in content


def test_phase0_pipeline__sanitize_column_names__removes_special_chars(
    tmp_path: pathlib.Path,
):
    """Column names with spaces and special chars are sanitized."""
    csv_file = tmp_path / "messy.csv"
    csv_file.write_text("First Name,Last-Name,Score (%)\nAlice,Smith,95\n")

    from scripts.ingest_csv import ingest_csv

    with patch("scripts.ingest_csv._load_to_postgres", return_value=1):
        result = ingest_csv(str(csv_file), "sanitize-test", str(tmp_path / "out"))

    assert "first_name" in result["columns"]
    assert "last_name" in result["columns"]
    assert "score____" in result["columns"] or any(
        "score" in c for c in result["columns"]
    )
