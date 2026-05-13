"""
Cartesia Line voice agent — backed by Amazon Bedrock AgentCore Runtime.

This is the AgentCore-powered alternative to main.py. Instead of calling Bedrock
directly via LiteLLM, this routes all reasoning through a Strands Agent deployed
on AgentCore Runtime.

Architecture:
    Caller → Cartesia Line → this file → AgentCore Runtime (InvokeAgentRuntime)
                                                ↓
                                        Strands Agent (in microVM)
                                                ↓
                                        Bedrock Claude + KB tools
                                                ↓
                                        Response → Cartesia TTS → Caller

Why AgentCore instead of direct Bedrock?
    - Session isolation: every caller gets their own microVM
    - Managed infrastructure: no servers to scale/manage
    - Built-in memory: conversation state persisted across invocations
    - Cost efficiency: pay only for active CPU, not I/O wait time
    - Observability: automatic tracing via CloudWatch/X-Ray
    - Tools/MCP: agent tools run securely inside the microVM

Usage:
    AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:...  \\
    AWS_REGION_NAME=us-west-2                             \\
    uv run python main_agentcore.py
"""

import asyncio
import os
import uuid
from typing import Annotated

import boto3
from loguru import logger

from line.llm_agent import LlmAgent, LlmConfig, ToolEnv, end_call, loopback_tool
from line.voice_agent_app import AgentEnv, CallRequest, VoiceAgentApp
from agentcore.invoke import invoke_agent

# ─── Configuration ────────────────────────────────────────────────────────────

AGENTCORE_RUNTIME_ARN = os.environ.get("AGENTCORE_RUNTIME_ARN")
AWS_REGION = os.environ.get("AWS_REGION_NAME", os.environ.get("AWS_REGION", "us-west-2"))

SYSTEM_PROMPT = """You are routing voice calls to a claims intake agent running on AgentCore.
Pass through the caller's messages and return the agent's responses verbatim."""

INTRODUCTION = "Thanks for calling Northwind Mutual claims. I can help you start a claim or answer questions about your policy. What's going on today?"


# ─── AgentCore Tool (bridges Cartesia Line to AgentCore Runtime) ──────────────


@loopback_tool(is_background=True)
async def ask_agentcore_agent(
    ctx: ToolEnv,
    message: Annotated[str, "The caller's transcribed message to send to the agent."],
) -> str:
    """Send the caller's message to the AgentCore-hosted claims agent and return its response.

    This tool invokes the deployed Strands Agent on AgentCore Runtime, which has access
    to the Bedrock Knowledge Base and all claims-intake logic.
    """
    if not AGENTCORE_RUNTIME_ARN:
        return "AgentCore agent is not configured. Set AGENTCORE_RUNTIME_ARN environment variable."

    # Use call_id as session_id for conversation continuity within a call
    session_id = getattr(ctx, "call_id", str(uuid.uuid4()))

    try:
        response = await asyncio.to_thread(
            invoke_agent,
            agent_runtime_arn=AGENTCORE_RUNTIME_ARN,
            prompt=message,
            session_id=session_id,
            region=AWS_REGION,
        )
        logger.info(f"AgentCore response: {response[:100]}...")
        return response
    except Exception as e:
        logger.exception("AgentCore invocation failed")
        return f"I'm having trouble connecting to our system. Please hold. Error: {e}"


# ─── Agent setup ──────────────────────────────────────────────────────────────


async def get_agent(env: AgentEnv, call_request: CallRequest):
    """
    Create the voice agent that routes to AgentCore.

    This uses a thin LLM layer (Haiku) that acts as a pass-through:
    it receives the caller's speech transcription from Cartesia Line,
    sends it to the AgentCore agent via tool call, and speaks the response.

    For a production deployment, you could bypass the local LLM entirely
    and route Cartesia transcription events directly to InvokeAgentRuntime.
    This approach keeps compatibility with the Line SDK's tool-calling pattern.
    """
    logger.info(
        f"Starting AgentCore-backed call for {call_request.call_id}. "
        f"Runtime ARN: {AGENTCORE_RUNTIME_ARN}"
    )

    return LlmAgent(
        # Thin orchestration layer — just routes to AgentCore
        model="bedrock/converse/anthropic.claude-haiku-4-5-20251001-v1:0",
        api_key=None,
        tools=[ask_agentcore_agent, end_call],
        config=LlmConfig.from_call_request(
            call_request,
            fallback_system_prompt=(
                "You are a voice call router. When the caller speaks, ALWAYS call the "
                "ask_agentcore_agent tool with their message. Speak the tool's response "
                "verbatim to the caller. Never answer questions yourself — always use the tool. "
                "When the tool returns '__END_CALL__', say goodbye and call end_call."
            ),
            fallback_introduction=INTRODUCTION,
        ),
    )


# ─── App ──────────────────────────────────────────────────────────────────────

app = VoiceAgentApp(get_agent=get_agent)

if __name__ == "__main__":
    if not AGENTCORE_RUNTIME_ARN:
        logger.warning(
            "⚠️  AGENTCORE_RUNTIME_ARN not set! "
            "The agent will fail to invoke AgentCore. "
            "Set it to your deployed agent's ARN."
        )
    print("Starting Cartesia Line + AgentCore voice agent")
    print(f"  AgentCore ARN: {AGENTCORE_RUNTIME_ARN or '(NOT SET)'}")
    print(f"  Region: {AWS_REGION}")
    app.run()
