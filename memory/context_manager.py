"""Context window management for OAK agents."""
__pattern__ = "Strategy"

from dataclasses import dataclass


@dataclass
class ContextBudget:
    """Tracks token usage within an agent's context window."""
    max_tokens: int = 128000
    used_tokens: int = 0
    reserved_tokens: int = 8000  # reserved for system prompt + tools

    @property
    def available(self) -> int:
        return max(0, self.max_tokens - self.used_tokens - self.reserved_tokens)

    def consume(self, tokens: int) -> None:
        self.used_tokens += tokens

    @property
    def utilization(self) -> float:
        return self.used_tokens / self.max_tokens if self.max_tokens > 0 else 1.0


class ContextManager:
    """Manages context window for an agent session.

    Prioritizes recent episodes and high-importance content.
    Summarizes older context when approaching the token limit.
    """

    def __init__(self, max_tokens: int = 128000) -> None:
        self.budget = ContextBudget(max_tokens=max_tokens)
        self._episodes: list[dict] = []

    def add_episode(self, episode: dict, estimated_tokens: int = 100) -> bool:
        """Add an episode to context. Returns False if budget exceeded."""
        if estimated_tokens > self.budget.available:
            return False
        self._episodes.append(episode)
        self.budget.consume(estimated_tokens)
        return True

    def get_context_episodes(self) -> list[dict]:
        """Return episodes ordered by relevance (recent + high importance first)."""
        return sorted(
            self._episodes,
            key=lambda e: (
                e.get("importance", 0.5),
                e.get("created_at", ""),
            ),
            reverse=True,
        )

    def should_summarize(self) -> bool:
        """Returns True when context utilization exceeds 80%."""
        return self.budget.utilization > 0.8

    def summarize_old_context(self) -> str:
        """Produce a summary of oldest episodes to free context space.
        Returns summary text. Caller should replace old episodes with summary.
        """
        if len(self._episodes) < 5:
            return ""
        old = self._episodes[:len(self._episodes) // 2]
        summary_parts = []
        for ep in old:
            content = ep.get("content", "")[:200]
            summary_parts.append(f"- [{ep.get('event_type', '?')}] {content}")
        self._episodes = self._episodes[len(self._episodes) // 2:]
        freed = sum(100 for _ in old)  # rough estimate
        self.budget.used_tokens = max(0, self.budget.used_tokens - freed)
        return "Previous context summary:\n" + "\n".join(summary_parts)
