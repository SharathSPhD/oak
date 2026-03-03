#!/usr/bin/env python3
"""oak-memory-mcp: MCP server for episodic memory retrieval via pgvector."""
__pattern__ = "Repository"

import asyncio
import json
import os
import asyncpg
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("oak-memory-mcp")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://oak:oak@oak-postgres:5432/oak")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="store_episode",
            description="Store an agent episode in episodic memory with optional embedding.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "problem_uuid": {"type": "string"},
                    "event_type": {"type": "string"},
                    "embedding": {"type": "array", "items": {"type": "number"}, "description": "Optional 1536-dim embedding"},
                },
                "required": ["content", "agent_id", "event_type"],
            },
        ),
        types.Tool(
            name="retrieve_similar",
            description="Retrieve semantically similar episodes using pgvector cosine similarity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query_embedding": {"type": "array", "items": {"type": "number"}},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query_embedding"],
            },
        ),
        types.Tool(
            name="mark_retrieved",
            description="Increment retrieved_count for an episode.",
            inputSchema={
                "type": "object",
                "properties": {"episode_id": {"type": "string"}},
                "required": ["episode_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        if name == "store_episode":
            row = await conn.fetchrow(
                """INSERT INTO episodes (problem_id, agent_id, event_type, content, embedding)
                   VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                arguments.get("problem_uuid"), arguments["agent_id"],
                arguments["event_type"], arguments["content"],
                arguments.get("embedding"),
            )
            return [types.TextContent(type="text", text=json.dumps({"episode_id": str(row["id"])}))]

        elif name == "retrieve_similar":
            rows = await conn.fetch(
                """SELECT id, agent_id, event_type, content, created_at FROM episodes
                   WHERE embedding IS NOT NULL AND archived_at IS NULL
                   ORDER BY embedding <=> $1::vector LIMIT $2""",
                arguments["query_embedding"], arguments.get("top_k", 5),
            )
            results = [
                {"id": str(r["id"]), "agent_id": r["agent_id"],
                 "event_type": r["event_type"], "content": r["content"],
                 "created_at": str(r["created_at"])}
                for r in rows
            ]
            return [types.TextContent(type="text", text=json.dumps(results))]

        elif name == "mark_retrieved":
            await conn.execute(
                """UPDATE episodes SET retrieved_count = retrieved_count + 1,
                   last_retrieved_at = NOW() WHERE id = $1""",
                arguments["episode_id"],
            )
            return [types.TextContent(type="text", text=json.dumps({"status": "ok"}))]

        else:
            raise ValueError(f"Unknown tool: {name}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(stdio_server(server))
