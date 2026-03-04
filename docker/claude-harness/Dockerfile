FROM ubuntu:22.04
LABEL maintainer="OAK Team"

# Install Claude Code and dependencies
RUN apt-get update && apt-get install -y \
    curl wget git python3 python3-pip redis-tools postgresql-client jq \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required by Claude Code)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Install Claude Code
RUN npm install -g @anthropic-ai/claude-code

# Install Python data science packages used by problem agents
RUN pip3 install --no-cache-dir pandas requests numpy scikit-learn

# Install oak-session state manager
COPY scripts/session-state.py /usr/local/bin/oak-session
RUN chmod +x /usr/local/bin/oak-session

# Install tool-proxy wrapper
COPY scripts/tool-proxy.sh /usr/local/bin/tool-proxy
RUN chmod +x /usr/local/bin/tool-proxy

# Install oak-entrypoint script
COPY scripts/entrypoint.sh /usr/local/bin/oak-entrypoint
RUN chmod +x /usr/local/bin/oak-entrypoint

# Create non-root user (claude-code refuses --dangerously-skip-permissions as root)
RUN useradd -m -s /bin/bash oak && \
    mkdir -p /workspace /mnt/oak-data /mnt/oak-skills && \
    chown -R oak:oak /workspace /mnt/oak-data /mnt/oak-skills

# Workspace mount point
WORKDIR /workspace
VOLUME ["/workspace", "/mnt/oak-data", "/mnt/oak-skills"]

# Environment (values injected at container start via docker-compose)
ENV ANTHROPIC_BASE_URL=http://oak-api-proxy:9000
ENV ANTHROPIC_AUTH_TOKEN=ollama
ENV ANTHROPIC_API_KEY="ollama"
ENV CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
ENV CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

USER oak

# Entrypoint: fetch problem details and start Claude Code with initial task
ENTRYPOINT ["/usr/local/bin/oak-entrypoint"]
