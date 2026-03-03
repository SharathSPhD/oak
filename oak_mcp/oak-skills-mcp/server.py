#!/usr/bin/env python3
"""oak-skills-mcp: MCP server for skill library lookup and promotion."""
__pattern__ = "Repository"

import asyncio
import json
import os
import asyncpg
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("oak-skills-mcp")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://oak:oak@oak-postgres:5432/oak")
SKILL_PROMO_THRESHOLD = int(os.environ.get("OAK_SKILL_PROMO_THRESHOLD", "2"))


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="find_skills",
            description="Search skill library by keyword. Always call this before writing new code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "category": {"type": "string", "enum": ["etl", "analysis", "ml", "ui", "infra"]},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="add_skill_use",
            description="Record that a skill was successfully used on a problem.",
            inputSchema={
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "problem_uuid": {"type": "string"},
                },
                "required": ["skill_id", "problem_uuid"],
            },
        ),
        types.Tool(
            name="request_promotion",
            description="Request promotion of a skill from probationary to permanent.",
            inputSchema={
                "type": "object",
                "properties": {"skill_id": {"type": "string"}},
                "required": ["skill_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        if name == "find_skills":
            query = arguments["query"]
            category = arguments.get("category")
            top_k = arguments.get("top_k", 5)
            if category:
                rows = await conn.fetch(
                    """SELECT id, name, category, description, trigger_keywords, status, use_count
                       FROM skills WHERE status != 'deprecated' AND category = $1
                         AND ($2 = ANY(trigger_keywords) OR name ILIKE $3) LIMIT $4""",
                    category, query, f"%{query}%", top_k,
                )
            else:
                rows = await conn.fetch(
                    """SELECT id, name, category, description, trigger_keywords, status, use_count
                       FROM skills WHERE status != 'deprecated'
                         AND ($1 = ANY(trigger_keywords) OR name ILIKE $2) LIMIT $3""",
                    query, f"%{query}%", top_k,
                )
            results = [
                {"id": str(r["id"]), "name": r["name"], "category": r["category"],
                 "description": r["description"], "trigger_keywords": list(r["trigger_keywords"] or []),
                 "status": r["status"], "use_count": r["use_count"]}
                for r in rows
            ]
            return [types.TextContent(type="text", text=json.dumps(results))]

        elif name == "add_skill_use":
            skill_id = arguments["skill_id"]
            problem_uuid = arguments["problem_uuid"]
            await conn.execute(
                """UPDATE skills SET use_count = use_count + 1,
                   verified_on_problems = array_append(verified_on_problems, $2::uuid),
                   updated_at = NOW() WHERE id = $1""",
                skill_id, problem_uuid,
            )
            return [types.TextContent(type="text", text=json.dumps({"status": "recorded"}))]

        elif name == "request_promotion":
            skill_id = arguments["skill_id"]
            row = await conn.fetchrow(
                "SELECT verified_on_problems FROM skills WHERE id = $1", skill_id
            )
            if row is None:
                return [types.TextContent(type="text", text=json.dumps({"error": "skill not found"}))]
            verified = row["verified_on_problems"] or []
            if len(verified) < SKILL_PROMO_THRESHOLD:
                return [types.TextContent(type="text", text=json.dumps({
                    "status": "threshold_not_met",
                    "verified_count": len(verified),
                    "required": SKILL_PROMO_THRESHOLD,
                }))]
            await conn.execute(
                "UPDATE skills SET status='permanent', updated_at=NOW() WHERE id=$1", skill_id
            )
            return [types.TextContent(type="text", text=json.dumps({"status": "promoted"}))]

        else:
            raise ValueError(f"Unknown tool: {name}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(stdio_server(server))
