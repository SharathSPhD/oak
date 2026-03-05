FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl ca-certificates gnupg openssh-client jq && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY docker/builder/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY oak_builder/ /app/oak_builder/
COPY manifest_domains.json /app/manifest_domains.json
COPY .claude/ /app/.claude/

ENV PYTHONUNBUFFERED=1
ENV GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

CMD ["python", "-m", "oak_builder.main"]
