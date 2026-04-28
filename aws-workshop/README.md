# Voice Agent on AWS Bedrock — Workshop

A Cartesia [Line](https://docs.cartesia.ai/line/sdk/overview) voice agent that runs entirely on AWS:

- **LLM inference** — Anthropic Claude Haiku 4.5 on **Amazon Bedrock** (via the Converse API, routed through LiteLLM).
- **Domain knowledge** — an **Amazon Bedrock Knowledge Base** queried at runtime through a tool call.
- **Auth** — a single IAM user with programmatic access keys, scoped by a minimal policy.

The example agent is a fictional insurance claims-intake specialist for "Northwind Mutual" — it can take a first-notice-of-loss and answer policy questions from documents you've ingested into your knowledge base.

## Architecture

```
caller (phone / web)
        │
        ▼
   Cartesia Line  ─── HTTP / WebSocket ───▶ this agent (main.py)
        │                                          │
        │                                          ├── litellm ──▶ Bedrock Converse  (Claude Haiku 4.5)
        │                                          │
        │                                          └── boto3   ──▶ Bedrock Agent Runtime
        ▼                                                              │
   Cartesia voice (Sonic TTS / Ink STT)                                ▼
                                                            Bedrock Knowledge Base
                                                            (S3 docs + vector index)
```

## Prerequisites

1. An **AWS account** with Bedrock available in your region (e.g. `us-east-1`, `us-west-2`).
2. **Model access** for Anthropic Claude Haiku 4.5 enabled in the Bedrock console: *Bedrock → Model access → Manage model access*. Approval is typically immediate.
3. A **Bedrock Knowledge Base** populated with whatever documents the agent should ground on (for the included Northwind claims-intake demo, anything resembling a personal-lines auto/home insurance policy works). Upload your documents to an S3 bucket and create a KB pointing at that bucket. AWS guide: <https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-create.html>. Sync the data source after creation. Make a note of the **Knowledge Base ID** (looks like `ABCD1234XY`).
4. Python 3.10+ and [`uv`](https://docs.astral.sh/uv/).
5. A Cartesia account to point a phone number / web client at this agent. See <https://docs.cartesia.ai/line/sdk/overview>.

## IAM setup

Create a dedicated IAM user for the workshop with **programmatic access** (no console password needed).

> AWS doesn't have "service accounts" the way Google Cloud does. The closest equivalent for local development is an IAM user with access keys; on AWS compute (EC2, ECS, Lambda) you'd use an IAM role and skip the keys entirely. This code works with both — when `api_key=None`, LiteLLM falls back to the standard AWS credential chain, which auto-resolves to instance/role credentials when running on AWS.

Attach this minimal inline policy. Replace `ACCOUNT_ID`, `REGION`, and `KB_ID`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockClaudeInference",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:Converse",
        "bedrock:ConverseStream"
      ],
      "Resource": "arn:aws:bedrock:REGION::foundation-model/anthropic.claude-haiku-4-5-*"
    },
    {
      "Sid": "BedrockKnowledgeBaseRetrieve",
      "Effect": "Allow",
      "Action": ["bedrock:Retrieve"],
      "Resource": "arn:aws:bedrock:REGION:ACCOUNT_ID:knowledge-base/KB_ID"
    }
  ]
}
```

## Run

```bash
cd aws-workshop
uv sync

AWS_ACCESS_KEY_ID=AKIA...           \
AWS_SECRET_ACCESS_KEY=...            \
AWS_REGION_NAME=us-east-1            \
BEDROCK_KB_ID=ABCD1234XY             \
uv run python main.py
```

The agent listens on `http://localhost:8000`. Point your Cartesia phone number or the Cartesia web client at this URL and place a call.

## How AWS is wired in

### 1. Bedrock as the LLM provider

The Line SDK uses LiteLLM under the hood, which has first-class Bedrock support. Selecting Bedrock is a single string change:

```python
LlmAgent(
    model="bedrock/converse/anthropic.claude-haiku-4-5-20251001-v1:0",
    api_key=None,  # LiteLLM picks up AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION_NAME
    ...
)
```

- The `bedrock/converse/` prefix routes the call through Bedrock's Converse API, which has the cleanest tool-calling surface.
- We pass `api_key=None` because Bedrock auths off the standard AWS credential chain, not an API key. LiteLLM reads `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION_NAME` from the environment automatically.
- LiteLLM Bedrock provider docs: <https://docs.litellm.ai/docs/providers/bedrock>.

To swap to Sonnet for stronger reasoning at higher latency, change the model ID to the Sonnet 4.5 Bedrock ID listed in the [Bedrock model catalog](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html).

### 2. Bedrock Knowledge Base as a tool

`query_policy_kb` (in `main.py`) is the agent's RAG tool. The LLM decides when to call it based on its docstring and parameter description.

```python
@loopback_tool(is_background=True)
async def query_policy_kb(ctx: ToolEnv, question: Annotated[str, "..."]) -> str:
    client = boto3.client("bedrock-agent-runtime", region_name=...)
    resp = await asyncio.to_thread(
        client.retrieve,
        knowledgeBaseId=os.environ["BEDROCK_KB_ID"],
        retrievalQuery={"text": question},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 4}},
    )
    chunks = [r["content"]["text"] for r in resp.get("retrievalResults", [])]
    return "\n\n---\n\n".join(chunks) if chunks else "No matching policy information found."
```

Three things to notice:

1. **`is_background=True`.** Bedrock KB retrieve calls take 300 ms–1 s. With background mode, the LLM can speak filler ("let me look that up") while the call completes, instead of going silent.
2. **`asyncio.to_thread`.** `boto3` is synchronous and would block the asyncio event loop without it.
3. **Errors are returned as strings, not raised.** The Line SDK treats a tool exception as fatal and ends the call. Returning an explanatory string lets the agent recover and tell the caller what happened.

The `bedrock-agent-runtime` client is the **runtime** API — it queries the KB. The separate `bedrock-agent` client is the **management** API for creating and configuring KBs. AWS Retrieve API reference: <https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_Retrieve.html>.

### 3. Auth

There's no AWS-specific code in this agent for auth. We rely on the standard AWS credential resolution chain:

1. Environment variables (`AWS_ACCESS_KEY_ID`, etc.) — used here.
2. Shared credentials file (`~/.aws/credentials` + `AWS_PROFILE`).
3. EC2 / ECS / Lambda instance metadata or task role.

The same `main.py` runs unchanged on a laptop with env vars and on an ECS task with an IAM task role attached.

## Customizing for your own domain

- **System prompt** — replace the `SYSTEM_PROMPT` in `main.py` with your own intake script. The structure (role / personality / instructions / conversation states) is well-suited to scripted, multi-turn intake flows; tear it down to a single sentence for free-form Q&A.
- **KB tool** — keep `query_policy_kb` as-is; only the docstring matters to the LLM (it's how the model decides when to call the tool). Rename and reword for your domain.
- **Model** — try Sonnet 4.5 for stronger tool selection if Haiku 4.5 is making poor calls; the latency tradeoff is real (typically 2-3x).

## Reference links

- Line SDK overview — <https://docs.cartesia.ai/line/sdk/overview>
- Calls API — <https://docs.cartesia.ai/line/integrations/calls-api>
- Bedrock model access — <https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html>
- Bedrock Knowledge Bases — <https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html>
- IAM identity-based policies for Bedrock — <https://docs.aws.amazon.com/bedrock/latest/userguide/security-iam.html>
- LiteLLM Bedrock provider — <https://docs.litellm.ai/docs/providers/bedrock>
