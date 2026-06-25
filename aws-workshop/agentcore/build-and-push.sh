#!/usr/bin/env bash
#
# Build the agent container and push to ECR.
#
# Prerequisites:
#   export REPO_URI=<ecr-repo-uri>
#   export AWS_REGION=<region>
#
# Usage:
#   chmod +x agentcore/build-and-push.sh
#   ./agentcore/build-and-push.sh

set -euo pipefail

: "${REPO_URI:?Set REPO_URI from setup-prerequisites.sh}"
: "${AWS_REGION:?Set AWS_REGION}"

ACCOUNT_ID=$(echo "$REPO_URI" | cut -d. -f1)

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Building & Pushing Agent Container"
echo "  Repo: $REPO_URI"
echo "  Region: $AWS_REGION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Authenticate Docker to ECR
echo ""
echo "→ Authenticating to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin \
  "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Build
echo ""
echo "→ Building container image..."
docker build -t cartesia-workshop-agent -f agentcore/Dockerfile .

# Tag
echo ""
echo "→ Tagging image..."
docker tag cartesia-workshop-agent:latest "${REPO_URI}:latest"

# Push
echo ""
echo "→ Pushing to ECR..."
docker push "${REPO_URI}:latest"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Image pushed: ${REPO_URI}:latest"
echo ""
echo "  Next: Deploy to AgentCore Runtime"
echo ""
echo "  python -m agentcore.deploy create \\"
echo "    --region $AWS_REGION \\"
echo "    --role-arn \$ROLE_ARN \\"
echo "    --image-uri ${REPO_URI}:latest \\"
echo "    --kb-id \$BEDROCK_KB_ID"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
