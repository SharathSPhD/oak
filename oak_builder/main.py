"""OAK Builder — autonomous self-evolving cognitive loop.

Entry point for the oak-builder Docker service. Runs the Cortex
perception-decision-action loop, with fallback to legacy sprint mode.
"""
from __future__ import annotations

__pattern__ = "TemplateMethod"

import asyncio
import logging
import os
import sys

from oak_builder.cortex import Cortex
from oak_builder.actions import build_catalogue

logging.basicConfig(
    level=logging.INFO,
    format="[oak-builder %(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("oak.builder.main")

API_URL = os.environ.get("OAK_API_URL", "http://oak-api:8000")
OLLAMA_URL = os.environ.get("OAK_BUILDER_OLLAMA_URL", "http://oak-api-proxy:9000")
REPO_PATH = os.environ.get("OAK_REPO_PATH", "/oak-repo")
WORKSPACE_BASE = os.environ.get("OAK_WORKSPACE_BASE", "/workspaces")


async def main() -> None:
    """Main entry point: run the Cortex cognitive loop."""
    logger.info("OAK Builder starting — Cortex cognitive loop")

    cortex = Cortex(
        api_url=API_URL,
        ollama_url=OLLAMA_URL,
        manifest_domains_path=os.path.join(REPO_PATH, "manifest_domains.json"),
    )

    catalogue = build_catalogue(
        api_url=API_URL,
        ollama_url=OLLAMA_URL,
        repo_path=REPO_PATH,
        workspace_base=WORKSPACE_BASE,
    )
    for action in catalogue.values():
        cortex.register_action(action)

    logger.info("Registered %d actions: %s", len(catalogue), list(catalogue.keys()))

    await cortex.run()


if __name__ == "__main__":
    asyncio.run(main())
