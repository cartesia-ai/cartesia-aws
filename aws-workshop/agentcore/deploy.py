"""
Deploy the Strands agent to Amazon Bedrock AgentCore Runtime.

Usage:
    python -m agentcore.deploy create   # First-time deploy
    python -m agentcore.deploy update   # Update existing runtime
    python -m agentcore.deploy status   # Check runtime status
    python -m agentcore.deploy delete   # Tear down

Prerequisites:
    - AWS CLI configured with appropriate permissions
    - ECR repository created (or use --direct-code-deploy for zip mode)
    - IAM execution role with Bedrock + ECR + CloudWatch permissions
"""

import argparse
import json
import os
import sys
import time

import boto3

AGENT_NAME = "cartesia-workshop-agent"
DEFAULT_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_REGION_NAME", "us-west-2"))


def get_clients(region: str):
    """Create the control plane and data plane clients."""
    control = boto3.client("bedrock-agentcore-control", region_name=region)
    data = boto3.client("bedrock-agentcore", region_name=region)
    return control, data


def create_runtime(region: str, role_arn: str, image_uri: str, kb_id: str = None):
    """Create an AgentCore Runtime with the workshop agent container."""
    control, _ = get_clients(region)

    env_vars = {}
    if kb_id:
        env_vars["BEDROCK_KB_ID"] = kb_id
    env_vars["AWS_REGION"] = region

    params = {
        "agentRuntimeName": AGENT_NAME,
        "agentRuntimeArtifact": {
            "containerConfiguration": {"containerUri": image_uri}
        },
        "networkConfiguration": {"networkMode": "PUBLIC"},
        "roleArn": role_arn,
        "protocolConfiguration": {"serverProtocol": "HTTP"},
    }

    if env_vars:
        params["environmentVariables"] = env_vars

    print(f"Creating AgentCore Runtime '{AGENT_NAME}'...")
    resp = control.create_agent_runtime(**params)

    runtime_id = resp.get("agentRuntimeId", "unknown")
    runtime_arn = resp.get("agentRuntimeArn", "unknown")
    print(f"✅ Runtime created!")
    print(f"   ID:  {runtime_id}")
    print(f"   ARN: {runtime_arn}")
    print(f"\nWaiting for ACTIVE status (usually ~60s)...")

    # Poll for active status
    for i in range(30):
        time.sleep(5)
        status_resp = control.get_agent_runtime(agentRuntimeId=runtime_id)
        status = status_resp.get("status", "UNKNOWN")
        print(f"   [{i*5}s] Status: {status}")
        if status == "ACTIVE":
            print(f"\n✅ Runtime is ACTIVE and ready to receive requests.")
            print(f"\nTo invoke:")
            print(f"  python -m agentcore.invoke --arn {runtime_arn} --prompt 'Hello'")
            return runtime_arn
        elif status == "FAILED":
            print(f"\n❌ Runtime creation FAILED.")
            print(f"   Reason: {status_resp.get('failureReason', 'unknown')}")
            return None

    print("⏳ Still provisioning. Check status with: python -m agentcore.deploy status")
    return runtime_arn


def get_status(region: str):
    """Get the status of the workshop runtime."""
    control, _ = get_clients(region)

    try:
        # List runtimes and find ours
        resp = control.list_agent_runtimes()
        for rt in resp.get("agentRuntimeSummaries", []):
            if rt.get("agentRuntimeName") == AGENT_NAME:
                runtime_id = rt["agentRuntimeId"]
                detail = control.get_agent_runtime(agentRuntimeId=runtime_id)
                print(f"Runtime: {AGENT_NAME}")
                print(f"  ID:     {detail.get('agentRuntimeId')}")
                print(f"  ARN:    {detail.get('agentRuntimeArn')}")
                print(f"  Status: {detail.get('status')}")
                print(f"  Created: {detail.get('createdAt')}")
                return detail
        print(f"No runtime found with name '{AGENT_NAME}'")
        return None
    except Exception as e:
        print(f"Error checking status: {e}")
        return None


def delete_runtime(region: str):
    """Delete the workshop runtime."""
    control, _ = get_clients(region)

    try:
        resp = control.list_agent_runtimes()
        for rt in resp.get("agentRuntimeSummaries", []):
            if rt.get("agentRuntimeName") == AGENT_NAME:
                runtime_id = rt["agentRuntimeId"]
                control.delete_agent_runtime(agentRuntimeId=runtime_id)
                print(f"✅ Runtime '{AGENT_NAME}' ({runtime_id}) deleted.")
                return
        print(f"No runtime found with name '{AGENT_NAME}'")
    except Exception as e:
        print(f"Error deleting runtime: {e}")


def main():
    parser = argparse.ArgumentParser(description="Deploy workshop agent to AgentCore Runtime")
    parser.add_argument("action", choices=["create", "update", "status", "delete"])
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--role-arn", help="IAM execution role ARN")
    parser.add_argument("--image-uri", help="ECR container image URI")
    parser.add_argument("--kb-id", help="Bedrock Knowledge Base ID")

    args = parser.parse_args()

    if args.action == "create":
        if not args.role_arn or not args.image_uri:
            print("ERROR: --role-arn and --image-uri are required for 'create'")
            sys.exit(1)
        create_runtime(args.region, args.role_arn, args.image_uri, args.kb_id)
    elif args.action == "status":
        get_status(args.region)
    elif args.action == "delete":
        delete_runtime(args.region)
    elif args.action == "update":
        print("Update: delete + create with new image URI")
        delete_runtime(args.region)
        time.sleep(5)
        if not args.role_arn or not args.image_uri:
            print("ERROR: --role-arn and --image-uri are required for 'update'")
            sys.exit(1)
        create_runtime(args.region, args.role_arn, args.image_uri, args.kb_id)


if __name__ == "__main__":
    main()
