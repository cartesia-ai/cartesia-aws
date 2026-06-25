# AgentCore Runtime Expansion — Cartesia × AWS Workshop

This branch adds an **Amazon Bedrock AgentCore Runtime** deployment path to the workshop. Instead of calling Bedrock directly via LiteLLM, the agent reasoning runs inside AgentCore's managed microVM infrastructure.

## Architecture Change

**Before (main branch):**
```
Caller → Cartesia Line → main.py → LiteLLM → Bedrock Converse (Claude)
                                                     ↓
                                              Bedrock Knowledge Base
```

**After (this branch):**
```
Caller → Cartesia Line → main_agentcore.py → InvokeAgentRuntime API
                                                     ↓
                                          AgentCore Runtime (microVM)
                                              ┌──────────────┐
                                              │ Strands Agent │
                                              │  + KB tool    │
                                              │  + end_call   │
                                              └──────┬───────┘
                                                     ↓
                                          Bedrock Claude + KB (inside microVM)
```

## Why AgentCore?

| Feature | Direct Bedrock | AgentCore Runtime |
|---------|---------------|-------------------|
| Session isolation | You manage it | Dedicated microVM per session |
| Infrastructure | You scale it | Serverless auto-scaling |
| Memory/state | You build it | Built-in short/long-term memory |
| Observability | You wire it | Auto-tracing (CloudWatch/X-Ray) |
| Cost model | Pay for full duration | Pay only for active CPU |
| Tools security | Your responsibility | Sandboxed in microVM |
| Session duration | N/A | Up to 8 hours |

## Quick Start

### Option A: Deploy Agent to AgentCore + Use Voice (Full Path)

```bash
cd aws-workshop

# 1. Set up IAM role + ECR repo
chmod +x agentcore/setup-prerequisites.sh
./agentcore/setup-prerequisites.sh us-west-2 YOUR_KB_ID

# 2. Export the values printed by the script
export ROLE_ARN=arn:aws:iam::ACCOUNT:role/CartesiaWorkshopAgentCoreRole
export REPO_URI=ACCOUNT.dkr.ecr.us-west-2.amazonaws.com/cartesia-workshop-agent
export AWS_REGION=us-west-2
export BEDROCK_KB_ID=YOUR_KB_ID

# 3. Build and push the agent container
chmod +x agentcore/build-and-push.sh
./agentcore/build-and-push.sh

# 4. Deploy to AgentCore Runtime
uv sync --extra agentcore
python -m agentcore.deploy create \
  --region $AWS_REGION \
  --role-arn $ROLE_ARN \
  --image-uri $REPO_URI:latest \
  --kb-id $BEDROCK_KB_ID

# 5. Run the Cartesia voice app pointing at AgentCore
AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:ACCOUNT:runtime/cartesia-workshop-agent-XXXXX \
AWS_REGION_NAME=us-west-2 \
uv run python main_agentcore.py
```

### Option B: Test Agent Locally (No Deployment)

```bash
cd aws-workshop
uv sync --extra agentcore

# Run the agent server locally (same contract as AgentCore)
AWS_ACCESS_KEY_ID=AKIA... \
AWS_SECRET_ACCESS_KEY=... \
AWS_REGION=us-west-2 \
BEDROCK_KB_ID=YOUR_KB_ID \
python -m agentcore.agent

# In another terminal, test it:
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "I need to file a claim for a car accident"}}'
```

### Option C: Invoke Deployed Agent (No Voice)

```bash
# After deployment (step 4 above):
python -m agentcore.invoke \
  --arn arn:aws:bedrock-agentcore:us-west-2:ACCOUNT:runtime/cartesia-workshop-agent-XXXXX \
  --prompt "I need to file a claim"
```

## File Structure

```
aws-workshop/
├── main.py                    # Original: Cartesia + direct Bedrock (unchanged)
├── main_agentcore.py          # NEW: Cartesia + AgentCore Runtime
├── pyproject.toml             # Updated with [agentcore] optional deps
├── agentcore/
│   ├── __init__.py
│   ├── agent.py               # Strands Agent + HTTP server (/ping, /invocations)
│   ├── invoke.py              # Client to call InvokeAgentRuntime
│   ├── deploy.py              # Deploy/status/delete commands
│   ├── Dockerfile             # Container image for AgentCore
│   ├── requirements-agent.txt # Container-only deps
│   ├── setup-prerequisites.sh # IAM role + ECR repo creation
│   ├── build-and-push.sh      # Docker build + ECR push
│   └── README.md              # This file
└── README.md                  # Original workshop README (unchanged)
```

## IAM Permissions

The `setup-prerequisites.sh` script creates a role with:
- `bedrock:InvokeModel`, `bedrock:Converse`, `bedrock:ConverseStream` (all foundation models)
- `bedrock:Retrieve` (Knowledge Base access)
- `logs:*` (CloudWatch for observability)
- `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage` (container pull)

The role trusts `bedrock-agentcore.amazonaws.com` as its principal.

## How It Works

### AgentCore Service Contract

AgentCore Runtime requires your container to expose:
- `GET /ping` → `200 {"status": "healthy"}` (health check, polled every 10s)
- `POST /invocations` → agent response (your inference endpoint)

The `agentcore/agent.py` file implements both using Python's built-in `http.server`.

### Conversation Flow

1. Caller speaks → Cartesia Line transcribes to text
2. `main_agentcore.py` receives transcription
3. Thin local LLM (Haiku) calls `ask_agentcore_agent` tool with the message
4. Tool calls `InvokeAgentRuntime` → routes to the microVM
5. Inside the microVM, Strands Agent reasons with Claude + KB tools
6. Response flows back → Cartesia TTS speaks it to the caller

### Session Continuity

Each phone call uses `call_id` as the `runtimeSessionId`. AgentCore maintains the microVM for the duration of the call, preserving conversation state between turns without any manual context management.

## Cost Comparison

For a typical claims intake call (5 turns, ~30s total processing):

| Component | Direct Bedrock | Via AgentCore |
|-----------|---------------|---------------|
| Model inference | ~$0.003 | ~$0.003 (same) |
| Compute | N/A | ~$0.0001 (only active CPU) |
| I/O wait (LLM thinking) | N/A | $0 (not charged!) |
| KB retrieval | ~$0.0005 | ~$0.0005 (same) |
| **Total per call** | **~$0.0035** | **~$0.0036** |

The marginal AgentCore cost is negligible for voice agents because most time is spent waiting on model inference (which isn't billed by AgentCore). The value is in managed infrastructure, isolation, and observability.

## Cleanup

```bash
# Delete the AgentCore Runtime
python -m agentcore.deploy delete --region us-west-2

# Delete ECR images (optional)
aws ecr batch-delete-image \
  --repository-name cartesia-workshop-agent \
  --image-ids imageTag=latest \
  --region us-west-2

# Delete ECR repo (optional)
aws ecr delete-repository \
  --repository-name cartesia-workshop-agent \
  --region us-west-2 --force

# Delete IAM role (optional)
aws iam delete-role-policy \
  --role-name CartesiaWorkshopAgentCoreRole \
  --policy-name AgentCoreExecutionPolicy
aws iam delete-role --role-name CartesiaWorkshopAgentCoreRole
```

## References

- [Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [Strands Agents → AgentCore Deployment](https://strandsagents.com/docs/user-guide/deploy/deploy_to_bedrock_agentcore/)
- [AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- [Nova Sonic + AgentCore WebSocket Sample](https://github.com/aws-samples/sample-nova-sonic-websocket-agentcore)
- [Cartesia Line SDK](https://docs.cartesia.ai/line/sdk/overview)
