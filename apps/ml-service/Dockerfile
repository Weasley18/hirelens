# Phase 8.2: Lambda runs this as a container image rather than a zip, because the model file
# alone is well past the 250MB zip limit. Images may be up to 10GB.
FROM public.ecr.aws/lambda/python:3.12

# llama-cpp-python compiles native code. The Lambda base image ships no toolchain, and the
# failure without this is a wall of C errors partway through pip install.
RUN dnf install -y gcc gcc-c++ make cmake && dnf clean all

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image. Fetching it on first request would add tens of
# seconds to an already slow cold start, and nothing is shared between invocations.
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY common.py ${LAMBDA_TASK_ROOT}/
# Staged into this directory by scripts/deploy_aws.sh — Docker cannot COPY outside the
# build context, and the canonical copy lives in packages/shared.
COPY analysis.schema.json ${LAMBDA_TASK_ROOT}/
COPY inference/ ${LAMBDA_TASK_ROOT}/inference/
COPY rag/ ${LAMBDA_TASK_ROOT}/rag/
COPY hirelens-q4.gguf ${LAMBDA_TASK_ROOT}/

ENV APP_ENV=production
ENV MODEL_BACKEND=gguf
ENV MODEL_PATH=/var/task/hirelens-q4.gguf
ENV LLAMA_THREADS=4

CMD ["inference.lambda_handler.handler"]
