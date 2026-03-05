"""OAK autonomous builder action catalogue.

Exports the Action base class, ActionResult, and build_catalogue() to
instantiate all actions for the Cortex cognitive loop.
"""
from __future__ import annotations

__pattern__ = "Strategy"

from oak_builder.cortex import Action, ActionResult

from oak_builder.actions.code_changes import (
    AddFeature,
    FixBug,
    ImproveHarness,
    ImprovePrompt,
)
from oak_builder.actions.domain_problems import RunDomainProblem
from oak_builder.actions.git_ops import (
    MergeToMain,
    OpenBranch,
    PrReview,
    PushToRemote,
    RunAcceptance,
)
from oak_builder.actions.infra import AddDependency, RebuildImage, UpdateDependency
from oak_builder.actions.introspection import (
    AuditSelf,
    BenchmarkRegression,
    ReplayFailure,
)
from oak_builder.actions.learning import HarvestHuggingFace, ReadPaper, WebResearch
from oak_builder.actions.manifest import ProposeAmendment, RatifyAmendment
from oak_builder.actions.models import BenchmarkModels, PullModel, UpdateRouting
from oak_builder.actions.rag import BuildRagIndex, EvaluateRagQuality
from oak_builder.actions.self_modify import SelfModify

__all__ = [
    "Action",
    "ActionResult",
    "build_catalogue",
]


def build_catalogue(
    *,
    api_url: str,
    ollama_url: str,
    repo_path: str = "/oak-repo",
    workspace_base: str = "/workspaces",
) -> dict[str, Action]:
    """Instantiate all actions and return a dict mapping name -> Action."""
    common = {"api_url": api_url, "ollama_url": ollama_url}
    extended = {**common, "repo_path": repo_path, "workspace_base": workspace_base}

    actions: list[Action] = [
        # Introspection
        AuditSelf(**common),
        ReplayFailure(**common),
        BenchmarkRegression(**common),
        # Domain
        RunDomainProblem(**common),
        # Learning
        WebResearch(**common),
        HarvestHuggingFace(**common),
        ReadPaper(**common),
        # Models
        PullModel(**common),
        BenchmarkModels(**common),
        UpdateRouting(**common),
        # Code
        ImprovePrompt(**extended),
        ImproveHarness(**extended),
        FixBug(**extended),
        AddFeature(**extended),
        # Git
        OpenBranch(**extended),
        PrReview(**extended),
        RunAcceptance(**extended),
        MergeToMain(**extended),
        PushToRemote(**extended),
        # Infrastructure
        RebuildImage(**extended),
        UpdateDependency(**extended),
        AddDependency(**extended),
        # RAG
        BuildRagIndex(**common),
        EvaluateRagQuality(**common),
        # Manifest
        ProposeAmendment(**extended),
        RatifyAmendment(**extended),
        # Self-modification
        SelfModify(**extended),
    ]
    return {a.name: a for a in actions}
