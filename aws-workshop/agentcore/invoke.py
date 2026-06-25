"""
Invoke the deployed AgentCore Runtime agent.

This is used both for testing and as the client library that main_agentcore.py
uses to route Cartesia voice requests to the AgentCore-hosted agent.

Usage (standalone test):
    python -m agentcore.invoke --arn <AGENT_RUNTIME_ARN> --prompt "I need to file a claim"

Usage (as library):
    from agentcore.invoke import invoke_agent
    response = invoke_agent(arn, prompt, session_id)
"""

import argparse
import json
import os
import uuid

import boto3


def invoke_agent(
    agent_runtime_arn: str,
    prompt: str,
    session_id: str = None,
    region: str = None,
) -> dict:
    """
    Invoke the AgentCore Runtime agent and return the parsed response.

    Args:
        agent_runtime_arn: ARN of the deployed AgentCore Runtime
        prompt: User message to send to the agent
        session_id: Session ID for conversation continuity (auto-generated if None)
        region: AWS region (defaults to AWS_REGION env var)

    Returns:
        Dict with keys:
          - "response": Agent's text response
          - "end_call": True if the agent signaled call termination
    """
    if region is None:
        region = os.environ.get("AWS_REGION", os.environ.get("AWS_REGION_NAME", "us-west-2"))

    if session_id is None:
        session_id = str(uuid.uuid4())

    client = boto3.client("bedrock-agentcore", region_name=region)

    payload = json.dumps({
        "input": {"prompt": prompt},
        "session_id": session_id,
    })

    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_runtime_arn,
        runtimeSessionId=session_id,
        payload=payload.encode("utf-8"),
        qualifier="DEFAULT",
    )

    # Read the streaming response and extract from JSON envelope
    raw = response["response"].read().decode("utf-8")

    # The /invocations endpoint returns:
    #   {"response": "...", "status": "success", "end_call": true/false}
    # Extract the response text so callers don't receive raw JSON
    try:
        parsed = json.loads(raw)
        return {
            "response": parsed["response"],
            "end_call": parsed.get("end_call", False),
        }
    except (json.JSONDecodeError, KeyError):
        # Fall back to raw text if response format is unexpected
        return {"response": raw, "end_call": False}


def main():
    parser = argparse.ArgumentParser(description="Invoke AgentCore Runtime agent")
    parser.add_argument("--arn", required=True, help="Agent Runtime ARN")
    parser.add_argument("--prompt", required=True, help="Message to send")
    parser.add_argument("--session-id", help="Session ID (auto-generated if omitted)")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))

    args = parser.parse_args()

    print(f"Invoking agent: {args.arn}")
    print(f"Session: {args.session_id or '(new)'}")
    print(f"Prompt: {args.prompt}")
    print("---")

    result = invoke_agent(
        agent_runtime_arn=args.arn,
        prompt=args.prompt,
        session_id=args.session_id,
        region=args.region,
    )

    print(f"Response: {result['response']}")
    if result["end_call"]:
        print("[Call ended by agent]")


if __name__ == "__main__":
    main()
