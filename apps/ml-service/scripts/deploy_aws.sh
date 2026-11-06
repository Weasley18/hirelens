#!/usr/bin/env bash
# Deploy a private Lambda. The worker needs lambda:InvokeFunction on this function only.
set -euo pipefail
REGION="${AWS_REGION:-ap-south-1}"
REPO="${ECR_REPO:-hirelens-ml}"
FUNCTION="${LAMBDA_FUNCTION:-hirelens-inference}"
ROLE_NAME="${LAMBDA_ROLE:-hirelens-lambda-role}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
: "${DATABASE_URL:?set DATABASE_URL}"
: "${ML_SERVICE_TOKEN:?set ML_SERVICE_TOKEN to a random 32-byte hex token}"
[[ "$ML_SERVICE_TOKEN" =~ ^[a-f0-9]{64}$ ]] || { echo "Invalid service token format" >&2; exit 1; }
cd "$HERE"
[ -f hirelens-q4.gguf ] || { echo "Model artifact missing" >&2; exit 1; }
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
TAG="$(date -u +%Y%m%d%H%M%S)"
IMAGE="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}"
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document "file://${HERE}/scripts/lambda-trust-policy.json" >/dev/null
  aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  sleep 15
fi
ROLE_ARN="$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)"
aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

# Restrict secret-file permissions; never interpolate credentials into AWS CLI arguments/output.
umask 077
ENV_FILE="$(mktemp)"
trap 'rm -f "$ENV_FILE" "${HERE}/analysis.schema.json"' EXIT
export DATABASE_URL ML_SERVICE_TOKEN
python3 - "$ENV_FILE" <<'PY'
import json, os, sys
with open(sys.argv[1], "w") as f:
    json.dump({"Variables": {"DATABASE_URL": os.environ["DATABASE_URL"],
              "ML_SERVICE_TOKEN": os.environ["ML_SERVICE_TOKEN"],
              "MODEL_BACKEND": "gguf", "APP_ENV": "production"}}, f)
PY
cp ../../packages/shared/analysis.schema.json ./analysis.schema.json
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"
if aws lambda get-function --function-name "$FUNCTION" --region "$REGION" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FUNCTION" --image-uri "$IMAGE" --region "$REGION" >/dev/null
  aws lambda wait function-updated --function-name "$FUNCTION" --region "$REGION"
  aws lambda update-function-configuration --function-name "$FUNCTION" --memory-size 3008 --timeout 80 \
    --environment "file://${ENV_FILE}" --region "$REGION" >/dev/null
else
  aws lambda create-function --function-name "$FUNCTION" --package-type Image --code "ImageUri=$IMAGE" \
    --role "$ROLE_ARN" --memory-size 3008 --timeout 80 --environment "file://${ENV_FILE}" --region "$REGION" >/dev/null
  aws lambda wait function-active-v2 --function-name "$FUNCTION" --region "$REGION"
fi
aws lambda wait function-updated --function-name "$FUNCTION" --region "$REGION"
# Bound account-level compute even if a worker credential is misused.
aws lambda put-function-concurrency --function-name "$FUNCTION" --reserved-concurrent-executions 2 --region "$REGION" >/dev/null
# Revoke the public gateway grant installed by the old version of this script.
POLICY="$(aws lambda get-policy --function-name "$FUNCTION" --region "$REGION" --query Policy --output text 2>/dev/null || true)"
if [[ "$POLICY" == *'apigw-invoke'* ]]; then
  aws lambda remove-permission --function-name "$FUNCTION" --statement-id apigw-invoke --region "$REGION"
fi
if aws lambda get-function-url-config --function-name "$FUNCTION" --region "$REGION" >/dev/null 2>&1; then
  aws lambda delete-function-url-config --function-name "$FUNCTION" --region "$REGION"
fi
printf 'ML_LAMBDA_FUNCTION=%s\nAWS_REGION=%s\n' "$FUNCTION" "$REGION"
printf 'Grant the worker IAM role lambda:InvokeFunction only on arn:aws:lambda:%s:%s:function:%s\n' "$REGION" "$ACCOUNT" "$FUNCTION"
