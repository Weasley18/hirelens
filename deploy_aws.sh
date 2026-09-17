#!/usr/bin/env bash
# Phase 8: build the inference image, push it to ECR, and point a Lambda at it.
# Usage: AWS_REGION=ap-south-1 bash scripts/deploy_aws.sh
# Safe to re-run: creates what is missing, updates what exists.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
REPO="${ECR_REPO:-hirelens-ml}"
FUNCTION="${LAMBDA_FUNCTION:-hirelens-inference}"
ROLE_NAME="${LAMBDA_ROLE:-hirelens-lambda-role}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

cd "$HERE"

if [ ! -f hirelens-q4.gguf ]; then
  echo "hirelens-q4.gguf is missing. Run scripts/quantize.sh first." >&2
  exit 1
fi

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
IMAGE="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:latest"

# --- IAM role: logging only. Nothing else is needed, so nothing else is granted. ---
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document "file://${HERE}/scripts/lambda-trust-policy.json"
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "waiting for the role to propagate..."
  sleep 15
fi
ROLE_ARN="$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)"

# --- ECR ---
aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --region "$REGION"

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

# The schema is canonical in packages/shared; stage a copy so the Docker context can see it.
cp ../../packages/shared/analysis.schema.json ./analysis.schema.json
trap 'rm -f "${HERE}/analysis.schema.json"' EXIT

docker build --platform linux/amd64 -t "$REPO" .
docker tag "${REPO}:latest" "$IMAGE"
docker push "$IMAGE"

# --- Lambda ---
if aws lambda get-function --function-name "$FUNCTION" --region "$REGION" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FUNCTION" \
    --image-uri "$IMAGE" --region "$REGION" >/dev/null
  echo "updated $FUNCTION"
else
  aws lambda create-function --function-name "$FUNCTION" \
    --package-type Image --code "ImageUri=$IMAGE" --role "$ROLE_ARN" \
    --memory-size 3008 --timeout 60 --region "$REGION" >/dev/null
  echo "created $FUNCTION"
fi

aws lambda wait function-updated --function-name "$FUNCTION" --region "$REGION"

# Memory buys CPU on Lambda, and this workload is entirely CPU-bound matrix maths, so 3008MB
# is not about the model fitting in RAM — it is about how many vCPUs the function gets.
aws lambda update-function-configuration --function-name "$FUNCTION" \
  --environment "Variables={DATABASE_URL=${DATABASE_URL:?set DATABASE_URL},MODEL_BACKEND=gguf}" \
  --region "$REGION" >/dev/null

# --- API Gateway ---
API_ID="$(aws apigatewayv2 get-apis --region "$REGION" \
  --query "Items[?Name=='hirelens-api'].ApiId | [0]" --output text)"

if [ "$API_ID" = "None" ] || [ -z "$API_ID" ]; then
  API_ID="$(aws apigatewayv2 create-api --name hirelens-api --protocol-type HTTP \
    --target "arn:aws:lambda:${REGION}:${ACCOUNT}:function:${FUNCTION}" \
    --region "$REGION" --query ApiId --output text)"
  aws lambda add-permission --function-name "$FUNCTION" \
    --statement-id apigw-invoke --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${REGION}:${ACCOUNT}:${API_ID}/*" \
    --region "$REGION" >/dev/null
fi

ENDPOINT="$(aws apigatewayv2 get-api --api-id "$API_ID" --region "$REGION" \
  --query ApiEndpoint --output text)"

echo
echo "ML_SERVICE_URL=${ENDPOINT}"
echo "Set that in the API and worker environment, then check it:"
echo "  curl -s ${ENDPOINT}/health"
