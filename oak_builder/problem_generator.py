"""Synthetic problem and dataset generator for self-build sprints.

Uses Ollama to generate a Python script that produces a CSV dataset,
then validates the output before submission to the OAK pipeline.
"""
from __future__ import annotations

__pattern__ = "Factory"

import logging
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import pandas as pd

from oak_builder.gap_analyzer import Gap

logger = logging.getLogger("oak.builder.problem_generator")

MAX_RETRIES = 3
SCRIPT_TIMEOUT = 60

GENERATION_PROMPT = """\
You are a synthetic data generator for business analytics.

DOMAIN: {domain_name}
SCENARIO: {scenario_title}
DESCRIPTION: {scenario_description}
COMPANY CONTEXT: {company_context}

Generate a Python script that creates a realistic CSV dataset for this scenario.
Requirements:
- Use only pandas and random/numpy (no external data sources)
- Create between {min_rows} and {max_rows} rows
- Include these columns at minimum: {required_columns}
- Add 2-3 additional realistic columns relevant to the domain
- Data should have realistic distributions (not uniform/constant)
- Include some missing values (< 10%) ONLY in string/categorical columns, never in numeric columns
- CRITICAL: Do NOT assign NaN, None, or np.nan to integer or float columns. All numeric columns must contain only valid numbers.
- Do NOT use np.nan with integer arrays or as values in integer columns
- If using np.random.choice with probabilities, ensure probabilities sum EXACTLY to 1.0 (use p=[...] and normalize: p = np.array(p); p = p/p.sum())
- Avoid timedelta with numpy int types - cast to int() first: timedelta(days=int(val))
- Include date columns where appropriate (ISO format)
- Save to the path specified in the variable OUTPUT_PATH

Output ONLY the Python script, no explanations. Start with:
import pandas as pd
import numpy as np
OUTPUT_PATH = "{output_path}"
"""


@dataclass
class GeneratedProblem:
    problem_uuid: str
    title: str
    description: str
    csv_path: str
    domain_id: str
    scenario_id: str


async def generate_problem(
    gap: Gap,
    *,
    workspace_base: str,
    ollama_url: str,
    model: str = "qwen3-coder",
    manifest_companies: dict | None = None,
) -> GeneratedProblem | None:
    """Generate a synthetic problem + dataset for a domain gap.

    Retries up to MAX_RETRIES if the generated dataset fails validation.
    Returns None if all retries are exhausted.
    """
    problem_uuid = str(uuid.uuid4())
    workspace = Path(workspace_base) / f"self-build-{problem_uuid[:8]}"
    workspace.mkdir(parents=True, exist_ok=True)
    csv_path = str(workspace / "dataset.csv")

    company = gap.scenario.get("canonical_company", "Acme Corp")
    if manifest_companies:
        for key, info in manifest_companies.items():
            if key.lower() in (gap.domain_id, gap.skill_category):
                company = f"{key}: {info.get('description', '')}"
                break

    scenario = gap.scenario
    rows_range = scenario.get("rows_range", [100, 500])
    required_cols = scenario.get("columns_required", [])

    prompt = GENERATION_PROMPT.format(
        domain_name=gap.domain_name,
        scenario_title=scenario["title"],
        scenario_description=scenario.get("description", scenario["title"]),
        company_context=company,
        min_rows=rows_range[0],
        max_rows=rows_range[1],
        required_columns=", ".join(required_cols),
        output_path=csv_path,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "Generating dataset for %s/%s (attempt %d/%d)",
            gap.domain_id, scenario["id"], attempt, MAX_RETRIES,
        )

        script = await _call_ollama(ollama_url, model, prompt)
        if not script:
            continue

        if not _run_script(script, csv_path, workspace):
            continue

        if validate_synthetic_dataset(csv_path, gap.domain_id, required_cols):
            title = f"[self-build] {scenario['title']} — {gap.domain_name}"
            description = (
                f"Auto-generated problem for {gap.domain_name} domain, "
                f"scenario: {scenario['title']}. "
                f"Dataset: dataset.csv (in the workspace directory)"
            )
            logger.info("Dataset validated: %s (%s)", csv_path, gap.domain_id)
            return GeneratedProblem(
                problem_uuid=problem_uuid,
                title=title,
                description=description,
                csv_path=csv_path,
                domain_id=gap.domain_id,
                scenario_id=scenario["id"],
            )

        logger.warning(
            "Validation failed for %s attempt %d", gap.domain_id, attempt,
        )

    logger.error(
        "All %d attempts failed for %s/%s",
        MAX_RETRIES, gap.domain_id, scenario["id"],
    )
    return None


def validate_synthetic_dataset(
    csv_path: str,
    domain_id: str,
    required_columns: list[str] | None = None,
) -> bool:
    """Validate a generated CSV meets quality thresholds.

    Also sanitizes numeric columns by filling NaN with column median
    to prevent downstream integer conversion errors.
    """
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        logger.error("Cannot read CSV: %s", csv_path)
        return False

    if len(df) < 30:
        logger.warning("Too few rows: %d", len(df))
        return False

    null_ratio = df.isnull().mean().max()
    if null_ratio > 0.5:
        logger.warning("Excessive nulls: %.1f%%", null_ratio * 100)
        return False

    numeric = df.select_dtypes(include="number")
    for col in numeric.columns:
        if df[col].isnull().any():
            median_val = df[col].median()
            if pd.isna(median_val):
                median_val = 0
            df[col] = df[col].fillna(median_val)
            logger.info("Filled NaN in numeric column '%s' with median", col)

    if len(numeric.columns) > 0 and numeric.std().min() == 0:
        logger.warning("Zero-variance numeric column detected")
        return False

    if required_columns:
        existing = {c.lower() for c in df.columns}
        for col in required_columns:
            if col.lower() not in existing:
                logger.warning("Missing required column: %s", col)
                return False

    try:
        df.to_csv(csv_path, index=False)
    except Exception as exc:
        logger.warning("Could not re-save sanitized CSV: %s", exc)

    return True


async def _call_ollama(url: str, model: str, prompt: str) -> str | None:
    """Call Ollama-compatible /v1/chat/completions and extract the script."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return _extract_python(content)
    except Exception as exc:
        logger.error("Ollama call failed: %s", exc)
        return None


def _extract_python(text: str) -> str:
    """Extract Python code from an LLM response (handles code fences)."""
    if "```python" in text:
        parts = text.split("```python", 1)
        code = parts[1].split("```", 1)[0]
        return code.strip()
    if "```" in text:
        parts = text.split("```", 1)
        code = parts[1].split("```", 1)[0]
        return code.strip()
    return text.strip()


def _run_script(script: str, expected_csv: str, workspace: Path) -> bool:
    """Run a generated Python script and check if it produced the CSV."""
    script_path = workspace / "generate_data.py"
    script_path.write_text(script)

    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT,
            cwd=str(workspace),
        )
        if result.returncode != 0:
            logger.warning("Script failed: %s", result.stderr[:500])
            return False
        if not Path(expected_csv).exists():
            logger.warning("Script completed but CSV not produced at %s", expected_csv)
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.warning("Script timed out after %ds", SCRIPT_TIMEOUT)
        return False
    except Exception as exc:
        logger.error("Script execution error: %s", exc)
        return False
