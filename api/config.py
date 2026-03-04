__pattern__ = "Configuration"

from enum import StrEnum

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OAKMode(StrEnum):
    DGX   = "dgx"
    MINI  = "mini"
    CLOUD = "cloud"


class RoutingStrategy(StrEnum):
    PASSTHROUGH  = "passthrough"
    STALL        = "stall"
    CONFIDENCE   = "confidence"
    COUNCIL      = "council"


class OAKSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
                                      extra="ignore", case_sensitive=False)

    # -- Platform -----------------------------------------------------------------
    oak_mode: OAKMode = OAKMode.DGX

    # -- Inference ----------------------------------------------------------------
    anthropic_base_url: str     = "http://oak-api-proxy:9000"
    anthropic_auth_token: str   = "ollama"
    anthropic_api_key: str      = ""          # Empty = local-only
    anthropic_api_key_real: str = ""          # Used by proxy for escalation
    default_model: str          = "llama3.3:70b"
    coder_model: str            = "qwen3-coder"
    analysis_model: str         = "glm-4.7"
    reasoning_model: str        = "llama3.3:70b"   # Orchestration, Judge, Meta

    # -- Routing strategy ---------------------------------------------------------
    routing_strategy: RoutingStrategy = RoutingStrategy.PASSTHROUGH
    stall_detection_enabled: bool     = False
    stall_min_tokens: int             = 20
    stall_phrases: list[str]          = Field(
        default=["i cannot", "i don't know how", "i'm unable", "as an ai"])
    local_confidence_threshold: float = 0.8
    council_models: list[str] = Field(default=["qwen3-coder", "deepseek-r1:14b"])
    council_judge_model: str = "deepseek-r1:14b"

    # -- Resource caps ------------------------------------------------------------
    max_agents_per_problem: int   = 10
    max_concurrent_problems: int  = 3
    max_harness_containers: int   = 20

    # -- Memory -------------------------------------------------------------------
    database_url: str                 = "postgresql://oak:oak@oak-postgres:5432/oak"
    redis_url: str                    = "redis://oak-redis:6379"
    oak_session_ttl_hours: int        = 24
    oak_memory_ttl_days: int          = 90

    # -- Skill library ------------------------------------------------------------
    oak_skill_promo_threshold: int    = 2
    skill_probationary_path: str      = "/workspace/skills/probationary"
    skill_permanent_path: str         = "/workspace/skills/permanent"

    # -- Agent behaviour ----------------------------------------------------------
    oak_idle_timeout_seconds: int     = 120
    claude_code_experimental_agent_teams: str = "1"

    # -- Observability ------------------------------------------------------------
    telemetry_enabled: bool           = True
    stall_escalation_alert_threshold: float = 0.3   # Alert if > 30% of calls escalate

    # -- Feature flags ------------------------------------------------------------
    skill_extraction_enabled: bool    = True
    judge_required: bool              = True
    # Set META_AGENT_ENABLED=true in .env to enable prompt evolution proposals
    meta_agent_enabled: bool          = False
    ui_evolution_enabled: bool        = False
    concurrent_problems_enabled: bool = False

    def model_for_role(self, role: str) -> str:
        """Return the Ollama model name appropriate for the given agent role."""
        analysis_roles = {"data-scientist", "skill-extractor"}
        reasoning_roles = {"orchestrator", "judge-agent", "meta-agent", "software-architect"}
        if role in analysis_roles:
            return self.analysis_model
        if role in reasoning_roles:
            return self.reasoning_model
        return self.coder_model  # data-engineer, ml-engineer, default

    @model_validator(mode="after")
    def validate_escalation_config(self) -> "OAKSettings":
        if self.stall_detection_enabled and not self.anthropic_api_key_real:
            # Not a hard error -- proxy will log and fall back to local
            import warnings
            warnings.warn(
                "STALL_DETECTION_ENABLED=true but ANTHROPIC_API_KEY_REAL is empty. "
                "Escalation will be attempted and silently fall back to Ollama response.",
                stacklevel=2)
        return self

    @model_validator(mode="after")
    def validate_resource_caps(self) -> "OAKSettings":
        if self.oak_mode == OAKMode.MINI and self.max_agents_per_problem > 4:
            import warnings
            warnings.warn(
                f"OAK_MODE=mini but MAX_AGENTS_PER_PROBLEM={self.max_agents_per_problem}. "
                "Mini profile recommends <= 4 agents per problem due to memory constraints.",
                stacklevel=2)
        return self


# Singleton -- imported by all modules
settings = OAKSettings()
