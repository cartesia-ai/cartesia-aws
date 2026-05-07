"""
Strands Agent for Amazon Bedrock AgentCore Runtime.

This agent replaces the direct LiteLLM → Bedrock Converse path from the base workshop.
It runs inside an AgentCore Runtime microVM and exposes the standard /ping and /invocations
HTTP contract that AgentCore expects.

The agent:
  - Uses the same system prompt and tools as the original workshop
  - Runs on Claude Haiku 4.5 via Bedrock (configurable)
  - Includes the policy KB lookup tool
  - Is deployed as a containerized service to AgentCore Runtime
"""

import asyncio
import json
import os
from typing import Any, Dict

import boto3
from strands import Agent, tool
from strands.models.bedrock import BedrockModel

# ─── System Prompt (same as base workshop) ───────────────────────────────────

SYSTEM_PROMPT = """# Role: Northwind Mutual Claims Intake Specialist

# Personality and Tone

## Identity
You are a Northwind Mutual claims intake specialist who handles the first phone call when a policyholder needs to start a claim or has a question about coverage.

## Task
Take a first-notice-of-loss for a Northwind Mutual auto or home policy, or answer a policyholder's questions about their coverage. For coverage questions, always look up the answer in the policy knowledge base — never guess or rely on general insurance knowledge.

## Demeanor
Calm, steady, and reassuring.

## Tone
Warm but professional.

## Instructions
- Ask one question at a time. Wait for the answer before moving on.
- Keep every response under 35 words.
- For ANY question about coverage, deductibles, exclusions, limits, or policy terms, call the query_policy_kb tool. NEVER answer policy questions from general knowledge.
- All internal operations must be completely silent. Never explain or mention tool calls to the caller.
- Never use bullet points, numbered lists, asterisks, markdown, or emojis in your speech.
"""

INTRODUCTION = "Thanks for calling Northwind Mutual claims. I can help you start a claim or answer questions about your policy. What's going on today?"


# ─── Tools ────────────────────────────────────────────────────────────────────


@tool
def query_policy_kb(question: str) -> str:
    """Look up policy and coverage details from the Northwind Mutual knowledge base.

    Use this for any question about coverage, deductibles, exclusions, limits, claims
    process, or policy terms. Do not answer such questions from general knowledge.

    Args:
        question: The policy or coverage question to look up, in natural language.
    """
    kb_id = os.environ.get("BEDROCK_KB_ID")
    if not kb_id:
        return "Knowledge base is not configured. Please offer to have an adjuster follow up."

    region = os.environ.get("AWS_REGION", os.environ.get("AWS_REGION_NAME", "us-east-1"))
    client = boto3.client("bedrock-agent-runtime", region_name=region)

    try:
        resp = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": question},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 4}},
        )
        chunks = [r["content"]["text"] for r in resp.get("retrievalResults", [])]
        if not chunks:
            return "No matching policy information found."
        return "\n\n---\n\n".join(chunks)
    except Exception as e:
        return f"Knowledge base lookup failed: {e}"


@tool
def end_call() -> str:
    """End the current phone call. Call this after you've said goodbye to the caller."""
    return "__END_CALL__"


# ─── Agent Factory ────────────────────────────────────────────────────────────


def create_agent() -> Agent:
    """Create and return the Strands Agent configured for this workshop."""
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_REGION_NAME", "us-east-1"))
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    model = BedrockModel(
        model_id=model_id,
        region_name=region,
    )

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[query_policy_kb, end_call],
    )

    return agent


# ─── HTTP Server (AgentCore Runtime Contract) ─────────────────────────────────
# AgentCore Runtime requires:
#   GET  /ping         → 200 (health check)
#   POST /invocations  → agent response


def create_app():
    """Create the Express-like HTTP app for AgentCore Runtime."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    agent = create_agent()
    # Store conversation history per session
    sessions: Dict[str, list] = {}

    class AgentCoreHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/ping":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "healthy"}')
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/invocations":
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")

                try:
                    payload = json.loads(body)
                    prompt = payload.get("input", {}).get("prompt", payload.get("prompt", ""))
                    session_id = payload.get("session_id", "default")

                    # Invoke agent
                    result = agent(prompt)
                    response_text = str(result)

                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(response_text.encode("utf-8"))

                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    error_resp = json.dumps({"error": str(e)})
                    self.wfile.write(error_resp.encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            # Suppress default HTTP logs; use structured logging in production
            pass

    return AgentCoreHandler


if __name__ == "__main__":
    from http.server import HTTPServer

    port = int(os.environ.get("PORT", 8080))
    handler = create_app()
    server = HTTPServer(("0.0.0.0", port), handler)
    print(f"AgentCore agent server running on port {port}")
    print(f"  /ping         → health check")
    print(f"  /invocations  → agent inference")
    server.serve_forever()
