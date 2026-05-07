# Dockerfile for deploying the Strands Agent to AgentCore Runtime
#
# AgentCore Runtime contract:
#   GET  /ping         → 200 {"status": "healthy"}
#   POST /invocations  → agent response (text/plain)
#
# Build:
#   docker build -t cartesia-workshop-agent -f agentcore/Dockerfile .
#
# Test locally:
#   docker run -p 8080:8080 \
#     -e AWS_ACCESS_KEY_ID=... \
#     -e AWS_SECRET_ACCESS_KEY=... \
#     -e AWS_REGION=us-west-2 \
#     -e BEDROCK_KB_ID=... \
#     cartesia-workshop-agent

FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY agentcore/requirements-agent.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY agentcore/agent.py /app/agent.py
COPY agentcore/__init__.py /app/agentcore/__init__.py

# AgentCore Runtime expects the server on port 8080
ENV PORT=8080
EXPOSE 8080

# Health check for container orchestration
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ping')" || exit 1

CMD ["python", "agent.py"]
