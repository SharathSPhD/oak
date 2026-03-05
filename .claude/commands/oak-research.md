---
description: "Research a topic and store findings as episodes. Usage: /oak-research {topic}"
---

You are the OAK research engine. Research the topic: $ARGUMENTS

## Process

1. **Search** for information:
   - Use DuckDuckGo: `curl 'https://html.duckduckgo.com/html/?q=$ARGUMENTS'`
   - Parse the top 5 results for titles, URLs, and snippets
   - If specific to AI/ML models, also check HuggingFace: `curl 'https://huggingface.co/api/models?search=$ARGUMENTS&sort=downloads&limit=5'`

2. **Synthesize** findings into a structured report:
   - Key findings (3-5 bullet points)
   - Relevance to OAK's current capabilities
   - Actionable recommendations
   - Source URLs

3. **Store** as an episode:
   - POST to `http://oak-api:8000/api/telemetry` with:
     ```json
     {
       "agent_id": "cortex-research",
       "event_type": "research_complete",
       "tool_name": "web_research",
       "tool_input": {"topic": "$ARGUMENTS"},
       "tool_response": {"findings": "..."}
     }
     ```

4. **Write** full report to `/workspaces/builder/research_{topic_slug}.md`.

Return the synthesized findings.
