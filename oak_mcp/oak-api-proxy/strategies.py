# oak_mcp/oak-api-proxy/strategies.py
__pattern__ = "Strategy"

from abc import ABC, abstractmethod


class RoutingStrategy(ABC):
    """Decides, given a request and a local response, which backend to use."""

    @abstractmethod
    async def should_escalate(self, request_body: dict, local_response: dict) -> bool:
        """Return True to escalate to Claude API; False to use local response."""
        ...

class PassthroughStrategy(RoutingStrategy):
    """Always returns False. Default in v1 — no escalation, fully local."""
    async def should_escalate(
        self, request_body: dict, local_response: dict
    ) -> bool:
        return False

class StallDetectionStrategy(RoutingStrategy):
    """Escalates on empty, too-short, or phrase-triggered responses.
    Enabled only when STALL_DETECTION_ENABLED=true."""
    def __init__(self, min_tokens: int, stall_phrases: list[str]) -> None:
        self.min_tokens = min_tokens
        self.stall_phrases = stall_phrases

    async def should_escalate(
        self, request_body: dict, local_response: dict
    ) -> bool:
        text = local_response.get("content", [{}])[0].get("text", "").lower().strip()
        if not text:
            return True
        if len(text.split()) < self.min_tokens:
            return True
        return any(text.startswith(p) for p in self.stall_phrases)

class ConfidenceThresholdStrategy(RoutingStrategy):
    """Escalates when the model's self-reported confidence field drops below threshold.
    Used in mini profile where local model capability is more limited."""
    def __init__(self, threshold: float) -> None:
        self.threshold = threshold

    async def should_escalate(
        self, request_body: dict, local_response: dict
    ) -> bool:
        confidence = local_response.get("confidence", 1.0)
        return confidence < self.threshold


class CouncilStrategy(RoutingStrategy):
    """Fan-out prompt to multiple local models, use a judge model to pick the best.

    Activated via ROUTING_STRATEGY=council. Only invoked when the primary model
    produces an uncertain response. In passthrough mode, acts like PassthroughStrategy.
    """
    def __init__(self, council_models: list[str], judge_model: str) -> None:
        self.council_models = council_models
        self.judge_model = judge_model

    async def should_escalate(
        self, request_body: dict, local_response: dict
    ) -> bool:
        return False

    async def select_best(
        self, responses: list[dict], original_prompt: str
    ) -> dict:
        """Given multiple model responses, return the best one.
        For now, returns the longest non-empty response (heuristic).
        Full judge-model synthesis is Phase 5+.
        """
        best = {}
        best_len = 0
        for resp in responses:
            text = ""
            for block in resp.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
                elif block.get("type") == "tool_use":
                    text += str(block.get("input", {}))
            if len(text) > best_len:
                best = resp
                best_len = len(text)
        return best or responses[0] if responses else {}
