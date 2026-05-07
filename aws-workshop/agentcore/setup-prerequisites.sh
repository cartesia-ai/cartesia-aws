#!/usr/bin/env bash
#
# Creates the IAM execution role and ECR repository needed for AgentCore Runtime.
#
# Usage:
#   chmod +x agentcore/setup-prerequisites.sh
#   ./agentcore/setup-prerequisites.sh [REGION] [KB_ID]
#
# Defaults:
#   REGION = us-west-2
#   KB_ID  = (optional, for Knowledge Base access)

set -euo pipefail

REGION="${1:-us-west-2}"
KB_ID="${2:-}"
ROLE_NAME="CartesiaWorkshopAgentCoreRole"
ECR_REPO="cartesia-workshop-agent"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AgentCore Prerequisites Setup"
echo "  Account: $ACCOUNT_ID"
echo "  Region:  $REGION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── 1. IAM Role ──────────────────────────────────────────────────────────────

echo ""
echo "→ Creating IAM role: $ROLE_NAME"

TRUST_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "bedrock-agentcore.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
)

aws iam create-role \
  --role-name "$ROLE_NAME" \
  --assume-role-policy-document "$TRUST_POLICY" \
  --description "Execution role for Cartesia workshop AgentCore Runtime" \
  2>/dev/null || echo "  (Role already exists, continuing...)"

# Inline policy for Bedrock model access + KB + CloudWatch + ECR
POLICY_DOC=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInference",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Converse",
        "bedrock:ConverseStream"
      ],
      "Resource": "arn:aws:bedrock:${REGION}::foundation-model/*"
    },
    {
      "Sid": "BedrockKnowledgeBase",
      "Effect": "Allow",
      "Action": ["bedrock:Retrieve"],
      "Resource": "arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:knowledge-base/*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:${REGION}:${ACCOUNT_ID}:*"
    },
    {
      "Sid": "ECRPull",
      "Effect": "Allow",
      "Action": [
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    }
  ]
}
EOF
)

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "AgentCoreExecutionPolicy" \
  --policy-document "$POLICY_DOC"

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "  ✅ Role ARN: $ROLE_ARN"

# ─── 2. ECR Repository ────────────────────────────────────────────────────────

echo ""
echo "→ Creating ECR repository: $ECR_REPO"

aws ecr create-repository \
  --repository-name "$ECR_REPO" \
  --region "$REGION" \
  2>/dev/null || echo "  (Repository already exists, continuing...)"

REPO_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"
echo "  ✅ Repo URI: $REPO_URI"

# ─── 3. Summary ───────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Prerequisites created!"
echo ""
echo "  Export these for the next steps:"
echo ""
echo "  export ROLE_ARN=$ROLE_ARN"
echo "  export REPO_URI=$REPO_URI"
echo "  export AWS_REGION=$REGION"
if [ -n "$KB_ID" ]; then
echo "  export BEDROCK_KB_ID=$KB_ID"
fi
echo ""
echo "  Next: ./agentcore/build-and-push.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
