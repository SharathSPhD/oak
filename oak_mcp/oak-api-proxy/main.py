"""
oak-api-proxy: Routes Claude Code API calls to Ollama or Claude API.
Implements the OAK Harness Proxy layer (HARNESS PROXY in architecture).
Never modifies the proxy() function — all routing logic lives in RoutingStrategy subclasses.
"""
__pattern__ = "Strategy"

import json
import os
import time
import uuid

import httpx

try:
    import redis as _redis_sync  # available at runtime inside Docker
except ImportError:  # pragma: no cover — redis absent only in bare test envs
    _redis_sync = None  # type: ignore[assignment]
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from strategies import (
    ConfidenceThresholdStrategy,
    PassthroughStrategy,
    RoutingStrategy,
    StallDetectionStrategy,
)

app = FastAPI(title="OAK API Proxy", version="0.1.0")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://oak-ollama:11434")
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_API_KEY_REAL = os.environ.get("ANTHROPIC_API_KEY_REAL", "")
ROUTING_STRATEGY_NAME = os.environ.get("ROUTING_STRATEGY", "passthrough")
STALL_DETECTION_ENABLED = os.environ.get("STALL_DETECTION_ENABLED", "false").lower() == "true"
STALL_MIN_TOKENS = int(os.environ.get("STALL_MIN_TOKENS", "20"))

# Default Ollama model for all Claude Code orchestrator calls
OLLAMA_DEFAULT_MODEL = os.environ.get("OLLAMA_DEFAULT_MODEL", "llama3.3:70b")

# Synthetic Claude model IDs to present to Claude Code (model validation)
_SYNTHETIC_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
]

# Build routing strategy from config — never use inline conditionals (PRD AP-2)
_STRATEGY_MAP = {
    "passthrough": PassthroughStrategy,
    "stall": StallDetectionStrategy,
    "confidence": ConfidenceThresholdStrategy,
}


def _build_strategy() -> RoutingStrategy:
    if not STALL_DETECTION_ENABLED:
        return PassthroughStrategy()
    cls = _STRATEGY_MAP.get(ROUTING_STRATEGY_NAME, PassthroughStrategy)
    if cls == StallDetectionStrategy:
        stall_phrases = json.loads(
            os.environ.get(
                "STALL_PHRASES",
                '["i cannot","i don\'t know how","i\'m unable","as an ai"]',
            )
        )
        return StallDetectionStrategy(min_tokens=STALL_MIN_TOKENS, stall_phrases=stall_phrases)
    if cls == ConfidenceThresholdStrategy:
        threshold = float(os.environ.get("LOCAL_CONFIDENCE_THRESHOLD", "0.8"))
        return ConfidenceThresholdStrategy(threshold=threshold)
    return PassthroughStrategy()


routing_strategy = _build_strategy()

REDIS_URL_PROXY = os.environ.get("REDIS_URL", "redis://localhost:6379")


def _log_escalation(problem_uuid: str | None) -> None:
    """Increment Redis escalation counters (fire-and-forget, never raises)."""
    try:
        r = _redis_sync.from_url(REDIS_URL_PROXY, decode_responses=True, socket_timeout=1)
        r.incr("oak:telemetry:escalations")
        if problem_uuid:
            r.hincrby(f"oak:telemetry:problem:{problem_uuid}", "escalations", 1)
        r.close()
    except Exception:
        pass  # telemetry is non-blocking; proxy must not fail on Redis down


def _log_call() -> None:
    """Increment total call counter (fire-and-forget)."""
    try:
        r = _redis_sync.from_url(REDIS_URL_PROXY, decode_responses=True, socket_timeout=1)
        r.incr("oak:telemetry:total_calls")
        r.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Anthropic ↔ OpenAI format conversion helpers
# ---------------------------------------------------------------------------

import re as _re


def _parse_xml_tool_calls(text: str) -> list[dict]:
    """Parse qwen3-coder XML-format tool calls from text content.

    Models like qwen3-coder fall back to text-format function calls when given
    many tools, using: <function=Name><parameter=key>value</parameter>...</function>

    Returns list of Anthropic tool_use dicts, or [] if no XML calls found.
    """
    calls = []
    # Match <function=ToolName>...</function> blocks (greedy but contained)
    fn_pattern = _re.compile(
        r"<function=(\w+)>(.*?)</function>", _re.DOTALL
    )
    for m in fn_pattern.finditer(text):
        name = m.group(1)
        body = m.group(2)
        # Extract <parameter=key>value</parameter> pairs
        param_pattern = _re.compile(
            r"<parameter=(\w+)>\s*(.*?)\s*</parameter>", _re.DOTALL
        )
        tool_input: dict = {}
        for pm in param_pattern.finditer(body):
            tool_input[pm.group(1)] = pm.group(2).strip()
        calls.append({
            "type": "tool_use",
            "id": f"toolu_{uuid.uuid4().hex[:8]}",
            "name": name,
            "input": tool_input,
        })
    return calls


def _anthropic_to_openai_request(data: dict) -> dict:
    """Convert Anthropic /v1/messages request body to OpenAI /v1/chat/completions."""
    messages: list[dict] = []

    # System prompt goes first as a system message
    if data.get("system"):
        system = data["system"]
        if isinstance(system, list):
            # system can be a list of content blocks in newer API versions
            text_parts = [b.get("text", "") for b in system if b.get("type") == "text"]
            system = "\n".join(text_parts)
        messages.append({"role": "system", "content": system})

    # Convert message content (handles text blocks and tool_result)
    for msg in data.get("messages", []):
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            # Flatten content blocks to a single string for Ollama
            text_parts = []
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    # Tool result content
                    inner = block.get("content", "")
                    if isinstance(inner, list):
                        inner = "\n".join(b.get("text", "") for b in inner if b.get("type") == "text")
                    text_parts.append(f"[tool_result id={block.get('tool_use_id')}]\n{inner}")
                elif block.get("type") == "tool_use":
                    # Tool use from assistant — convert to text for simplicity
                    text_parts.append(
                        f"[tool_use name={block.get('name')} id={block.get('id')}]\n"
                        + json.dumps(block.get("input", {}))
                    )
            messages.append({"role": role, "content": "\n".join(text_parts)})
        else:
            messages.append({"role": role, "content": str(content)})

    oai: dict = {
        "model": OLLAMA_DEFAULT_MODEL,
        "messages": messages,
        "stream": data.get("stream", False),
    }
    if data.get("max_tokens"):
        oai["max_tokens"] = data["max_tokens"]
    if data.get("temperature") is not None:
        oai["temperature"] = data["temperature"]

    # Convert Anthropic tools to OpenAI tools
    if data.get("tools"):
        oai_tools = []
        for t in data["tools"]:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            })
        oai["tools"] = oai_tools

    return oai


def _openai_to_anthropic_response(oai_resp: dict, original_model: str) -> dict:
    """Convert OpenAI /v1/chat/completions response to Anthropic /v1/messages format."""
    choice = oai_resp.get("choices", [{}])[0]
    message = choice.get("message", {})
    usage = oai_resp.get("usage", {})

    content_text = message.get("content") or ""
    content_blocks: list[dict] = []

    # Handle tool_calls from Ollama
    if message.get("tool_calls"):
        for tc in message["tool_calls"]:
            fn = tc.get("function", {})
            try:
                tool_input = json.loads(fn.get("arguments", "{}"))
            except Exception:
                tool_input = {"raw": fn.get("arguments", "")}
            content_blocks.append({
                "type": "tool_use",
                "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:8]}"),
                "name": fn.get("name", "unknown"),
                "input": tool_input,
            })

    # Detect XML-format tool calls in text (fallback for models with many tools)
    if not content_blocks and content_text and "<function=" in content_text:
        xml_calls = _parse_xml_tool_calls(content_text)
        if xml_calls:
            content_blocks.extend(xml_calls)
            content_text = ""  # suppress text block; only emit tool_use

    if content_text:
        content_blocks.append({"type": "text", "text": content_text})

    finish_reason = choice.get("finish_reason", "stop")
    stop_reason = "end_turn"
    if finish_reason == "tool_calls" or any(b.get("type") == "tool_use" for b in content_blocks):
        stop_reason = "tool_use"
    elif finish_reason == "length":
        stop_reason = "max_tokens"

    return {
        "id": f"msg_{oai_resp.get('id', uuid.uuid4().hex[:20])}",
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": original_model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


async def _stream_anthropic(
    ollama_url: str,
    oai_body: dict,
    original_model: str,
):
    """Stream Ollama SSE chunks converted to Anthropic SSE format.

    Handles both text content and tool_call deltas.
    Tool_calls come as incremental argument JSON that must be accumulated and
    emitted as Anthropic input_json_delta events.
    """
    msg_id = f"msg_{uuid.uuid4().hex[:20]}"

    yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'content': [], 'model': original_model, 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}})}\n\n"  # noqa: E501
    yield f"event: ping\ndata: {json.dumps({'type': 'ping'})}\n\n"

    # Track open content blocks
    text_block_index: int | None = None  # Index of text block if emitted at finish
    text_buffer: list[str] = []  # Buffer all text; emit as text or XML tool calls at finish
    # tool_call_index → anthropic_block_index
    tool_block_map: dict[int, int] = {}
    next_block_index = 0
    output_tokens = 0

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", ollama_url, json=oai_body,
                                 headers={"Authorization": "Bearer ollama"}) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except Exception:
                    continue

                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta", {})

                # ── Text content (buffer; emit only if no XML tool calls found later)
                text = delta.get("content") or ""
                if text:
                    text_buffer.append(text)
                    output_tokens += 1

                # ── Tool calls (OpenAI structured format) ─────────────────
                for tc_delta in delta.get("tool_calls") or []:
                    tc_idx = tc_delta.get("index", 0)
                    fn = tc_delta.get("function", {})

                    if tc_idx not in tool_block_map:
                        # First chunk for this tool call — emit content_block_start
                        bi = next_block_index
                        tool_block_map[tc_idx] = bi
                        next_block_index += 1
                        tc_id = tc_delta.get("id") or f"toolu_{uuid.uuid4().hex[:8]}"
                        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': bi, 'content_block': {'type': 'tool_use', 'id': tc_id, 'name': fn.get('name', ''), 'input': {}}})}\n\n"  # noqa: E501

                    bi = tool_block_map[tc_idx]
                    args_chunk = fn.get("arguments") or ""
                    if args_chunk:
                        yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': bi, 'delta': {'type': 'input_json_delta', 'partial_json': args_chunk}})}\n\n"  # noqa: E501

                # ── Finish ────────────────────────────────────────────────
                finish = choice.get("finish_reason")
                if finish:
                    stop_reason = "end_turn"
                    if finish == "tool_calls":
                        stop_reason = "tool_use"
                    elif finish == "length":
                        stop_reason = "max_tokens"

                    full_text = "".join(text_buffer)

                    # Detect XML-format tool calls (<function=Name>...) from models
                    # that fall back to text-based function calling with many tools
                    xml_calls = []
                    if not tool_block_map and "<function=" in full_text:
                        xml_calls = _parse_xml_tool_calls(full_text)

                    if xml_calls:
                        # Emit XML tool calls as proper tool_use blocks
                        stop_reason = "tool_use"
                        for tc in xml_calls:
                            bi = next_block_index
                            next_block_index += 1
                            yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': bi, 'content_block': {'type': 'tool_use', 'id': tc['id'], 'name': tc['name'], 'input': {}}})}\n\n"  # noqa: E501
                            args_json = json.dumps(tc["input"])
                            yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': bi, 'delta': {'type': 'input_json_delta', 'partial_json': args_json}})}\n\n"  # noqa: E501
                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': bi})}\n\n"
                    else:
                        # Emit buffered text as text block
                        if full_text:
                            text_block_index = next_block_index
                            yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': text_block_index, 'content_block': {'type': 'text', 'text': ''}})}\n\n"  # noqa: E501
                            yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': text_block_index, 'delta': {'type': 'text_delta', 'text': full_text}})}\n\n"  # noqa: E501
                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': text_block_index})}\n\n"  # noqa: E501
                            next_block_index += 1

                        # Close structured tool_call blocks (text block already closed above)
                        for bi in sorted(tool_block_map.values()):
                            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': bi})}\n\n"

                    yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_reason, 'stop_sequence': None}, 'usage': {'output_tokens': output_tokens}})}\n\n"  # noqa: E501
                    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
                    return

    # Fallback stop (stream ended without finish_reason chunk)
    full_text = "".join(text_buffer)
    xml_calls = _parse_xml_tool_calls(full_text) if (not tool_block_map and "<function=" in full_text) else []
    if xml_calls:
        stop_reason = "tool_use"
        for tc in xml_calls:
            bi = next_block_index
            next_block_index += 1
            yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': bi, 'content_block': {'type': 'tool_use', 'id': tc['id'], 'name': tc['name'], 'input': {}}})}\n\n"  # noqa: E501
            yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': bi, 'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(tc['input'])}})}\n\n"  # noqa: E501
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': bi})}\n\n"
    else:
        stop_reason = "end_turn"
        if full_text:
            text_block_index = next_block_index
            yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': text_block_index, 'content_block': {'type': 'text', 'text': ''}})}\n\n"  # noqa: E501
            yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': text_block_index, 'delta': {'type': 'text_delta', 'text': full_text}})}\n\n"  # noqa: E501
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': text_block_index})}\n\n"  # noqa: E501
        for bi in sorted(tool_block_map.values()):
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': bi})}\n\n"
    yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop_reason, 'stop_sequence': None}, 'usage': {'output_tokens': output_tokens}})}\n\n"  # noqa: E501
    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"


# ---------------------------------------------------------------------------
# Interceptors — registered BEFORE catch_all so FastAPI routes them first
# ---------------------------------------------------------------------------

@app.get("/v1/models")
async def models_list() -> dict:
    """Return synthetic Claude model list so Claude Code accepts model names."""
    _log_call()
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": m, "object": "model", "created": created, "owned_by": "anthropic"}
            for m in _SYNTHETIC_MODELS
        ],
    }


@app.post("/v1/messages")
async def messages(request: Request) -> Response:
    """
    Anthropic /v1/messages → Ollama /v1/chat/completions bridge.
    Handles both streaming and non-streaming. Escalates to real Claude API if
    the routing strategy requests it.
    """
    _log_call()
    body = await request.body()
    data = json.loads(body) if body else {}
    original_model = data.get("model", "claude-sonnet-4-6")
    is_stream = data.get("stream", False)

    # DEBUG: log tools and last message to stderr
    import sys as _sys
    tools_names = [t.get("name") for t in data.get("tools", [])]
    last_msg = (data.get("messages") or [{}])[-1]
    last_role = last_msg.get("role", "?")
    last_content = last_msg.get("content", "")
    if isinstance(last_content, list):
        last_content = str([b.get("type") for b in last_content])
    print(f"[proxy-debug] stream={is_stream} tools={tools_names} last_role={last_role} content_preview={str(last_content)[:80]}", file=_sys.stderr, flush=True)

    oai_body = _anthropic_to_openai_request(data)
    ollama_url = f"{OLLAMA_BASE_URL}/v1/chat/completions"

    if is_stream:
        return StreamingResponse(
            _stream_anthropic(ollama_url, oai_body, original_model),
            media_type="text/event-stream",
        )

    # Non-streaming
    async with httpx.AsyncClient(timeout=300) as client:
        ollama_resp = await client.post(
            ollama_url,
            json=oai_body,
            headers={"Authorization": "Bearer ollama"},
        )

    try:
        oai_json = ollama_resp.json()
    except Exception:
        oai_json = {}

    should_escalate = await routing_strategy.should_escalate(data, oai_json)
    if should_escalate and ANTHROPIC_API_KEY_REAL:
        escalation_headers = dict(request.headers)
        escalation_headers.pop("host", None)
        escalation_headers["x-api-key"] = ANTHROPIC_API_KEY_REAL
        escalation_headers.pop("authorization", None)
        async with httpx.AsyncClient(timeout=180) as client:
            claude_resp = await client.post(
                f"{ANTHROPIC_BASE_URL}/v1/messages",
                content=body,
                headers=escalation_headers,
            )
        _log_escalation(request.headers.get("x-oak-problem-uuid"))
        return Response(
            content=claude_resp.content,
            status_code=claude_resp.status_code,
            headers=dict(claude_resp.headers),
        )

    anthropic_resp = _openai_to_anthropic_response(oai_json, original_model)
    return Response(
        content=json.dumps(anthropic_resp),
        status_code=200,
        media_type="application/json",
    )


async def proxy(request: Request, path: str) -> Response:
    """
    Core proxy function. NEVER modify this function — routing decisions
    are delegated entirely to routing_strategy.should_escalate().
    """
    # Log total call count
    _log_call()

    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers["Authorization"] = "Bearer ollama"

    # Forward to Ollama
    async with httpx.AsyncClient(timeout=120) as client:
        ollama_resp = await client.request(
            method=request.method,
            url=f"{OLLAMA_BASE_URL}/{path}",
            content=body,
            headers=headers,
        )

    # Check if escalation is needed
    try:
        local_response = ollama_resp.json()
    except Exception:
        local_response = {}

    should_escalate = await routing_strategy.should_escalate(
        json.loads(body) if body else {}, local_response
    )

    if should_escalate and ANTHROPIC_API_KEY_REAL:
        escalation_headers = dict(request.headers)
        escalation_headers.pop("host", None)
        escalation_headers["x-api-key"] = ANTHROPIC_API_KEY_REAL
        escalation_headers.pop("authorization", None)
        async with httpx.AsyncClient(timeout=180) as client:
            claude_resp = await client.request(
                method=request.method,
                url=f"{ANTHROPIC_BASE_URL}/v1/{path}",
                content=body,
                headers=escalation_headers,
            )
        problem_uuid = headers.get("x-oak-problem-uuid")
        _log_escalation(problem_uuid)
        return Response(
            content=claude_resp.content,
            status_code=claude_resp.status_code,
            headers=dict(claude_resp.headers),
        )

    return Response(
        content=ollama_resp.content,
        status_code=ollama_resp.status_code,
        headers=dict(ollama_resp.headers),
    )


@app.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "routing_strategy": ROUTING_STRATEGY_NAME,
        "stall_detection_enabled": STALL_DETECTION_ENABLED,
        "ollama_url": OLLAMA_BASE_URL,
        "ollama_model": OLLAMA_DEFAULT_MODEL,
        "escalation_available": bool(ANTHROPIC_API_KEY_REAL),
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(request: Request, path: str) -> Response:
    return await proxy(request, path)
