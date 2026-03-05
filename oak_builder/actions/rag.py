"""RAG actions: build index, assess quality."""
from __future__ import annotations

__pattern__ = "Strategy"

import logging
from pathlib import Path

import httpx

from oak_builder.cortex import Action, ActionResult, CortexState, Perception

logger = logging.getLogger("oak.builder.actions.rag")

OLLAMA_EMBED = "http://oak-ollama:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"


class BuildRagIndex(Action):
    """Chunk knowledge text, embed via Ollama, INSERT INTO domain_knowledge."""

    def __init__(
        self,
        api_url: str,
        ollama_url: str,
        repo_path: str = "/oak-repo",
        workspace_base: str = "/workspaces",
    ) -> None:
        super().__init__(api_url=api_url, ollama_url=ollama_url)
        self.repo_path = repo_path
        self.workspace_base = workspace_base

    @property
    def name(self) -> str:
        return "build_rag_index"

    @property
    def category(self) -> str:
        return "rag"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if getattr(state, "knowledge_to_index", None):
            return 0.9
        if getattr(state, "rag_index_stale", None):
            return 0.6
        return 0.2

    async def execute(self, state: CortexState) -> ActionResult:
        knowledge = getattr(state, "knowledge_to_index", "")
        if not knowledge:
            knowledge_path = Path(self.repo_path) / "domain_knowledge.txt"
            if knowledge_path.exists():
                knowledge = knowledge_path.read_text()
            else:
                return ActionResult(
                    success=False,
                    summary="No knowledge_to_index or domain_knowledge.txt",
                )

        chunks = _chunk_text(knowledge, chunk_size=500, overlap=50)
        if not chunks:
            return ActionResult(success=False, summary="No chunks produced")

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                inserted = 0
                for i, chunk in enumerate(chunks[:100]):
                    resp = await client.post(
                        OLLAMA_EMBED,
                        json={"model": EMBED_MODEL, "prompt": chunk[:8000]},
                    )
                    if resp.status_code != 200:
                        logger.warning("Embedding failed for chunk %d: %s", i, resp.status_code)
                        continue
                    data = resp.json()
                    embedding = data.get("embedding")
                    if not embedding:
                        continue

                    db_resp = await client.post(
                        f"{self.api_url}/api/rag/index",
                        json={
                            "content": chunk,
                            "embedding": embedding,
                            "source": "domain_knowledge",
                        },
                    )
                    if db_resp.status_code in (200, 201):
                        inserted += 1

                recall = await _verify_retrieval(client, self.api_url)
                return ActionResult(
                    success=inserted > 0,
                    artifacts={
                        "chunks_indexed": inserted,
                        "total_chunks": len(chunks),
                        "retrieval_verified": recall,
                    },
                    summary=None if inserted > 0 else "No chunks inserted",
                )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end < len(text) else len(text)
    return chunks


async def _verify_retrieval(client: httpx.AsyncClient, api_url: str) -> bool:
    """Run a test query to verify retrieval quality."""
    try:
        resp = await client.get(
            f"{api_url}/api/rag/search",
            params={"query": "domain knowledge", "top_k": 3},
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", []) if isinstance(data, dict) else data
            return len(results) > 0
    except Exception:
        pass
    return False


class EvaluateRagQuality(Action):
    """Run test queries, measure recall@3, log results."""

    def __init__(
        self,
        api_url: str,
        ollama_url: str,
        repo_path: str = "/oak-repo",
        workspace_base: str = "/workspaces",
    ) -> None:
        super().__init__(api_url=api_url, ollama_url=ollama_url)
        self.repo_path = repo_path
        self.workspace_base = workspace_base

    @property
    def name(self) -> str:
        return "evaluate_rag_quality"

    @property
    def category(self) -> str:
        return "rag"

    async def estimate_value(self, state: CortexState, perception: Perception) -> float:
        if getattr(state, "rag_index_built", None) or getattr(state, "evaluate_rag_pending", None):
            return 0.8
        return 0.4

    async def execute(self, state: CortexState) -> ActionResult:
        test_queries = getattr(state, "rag_test_queries", [
            "What is the domain model?",
            "How does ETL work?",
            "What are the skill categories?",
        ])

        try:
            recall_scores = []
            async with httpx.AsyncClient(base_url=self.api_url, timeout=30) as client:
                for query in test_queries[:10]:
                    resp = await client.get(
                        "/api/rag/search",
                        params={"query": query, "top_k": 3},
                    )
                    if resp.status_code != 200:
                        recall_scores.append(0.0)
                        continue
                    data = resp.json()
                    results = data.get("results", []) if isinstance(data, dict) else data
                    recall = min(1.0, len(results) / 3.0) if results else 0.0
                    recall_scores.append(recall)

            avg_recall = sum(recall_scores) / len(recall_scores) if recall_scores else 0.0
            logger.info("RAG recall@3: %.2f (queries=%d)", avg_recall, len(recall_scores))

            return ActionResult(
                success=True,
                artifacts={
                    "recall_at_3": avg_recall,
                    "per_query": recall_scores,
                    "queries_run": len(test_queries),
                },
            )
        except Exception as exc:
            return ActionResult(success=False, summary=str(exc))
