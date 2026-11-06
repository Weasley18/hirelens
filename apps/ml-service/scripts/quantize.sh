#!/usr/bin/env bash
# Phase 5: merged HF weights -> GGUF -> 4-bit quantized GGUF.
# Usage: bash scripts/quantize.sh hirelens-merged
set -euo pipefail

MERGED_DIR="${1:-hirelens-merged}"
QUANT="${QUANT:-Q4_K_M}"

if [ ! -d "$MERGED_DIR" ]; then
  echo "No such directory: $MERGED_DIR — run training/merge_and_export.py first." >&2
  exit 1
fi

if [ ! -d llama.cpp ]; then
  git clone --depth 1 https://github.com/ggerganov/llama.cpp
  pip install -r llama.cpp/requirements.txt
  cmake -B llama.cpp/build -S llama.cpp -DCMAKE_BUILD_TYPE=Release
  cmake --build llama.cpp/build --config Release -j --target llama-quantize llama-cli
fi

python llama.cpp/convert_hf_to_gguf.py "$MERGED_DIR" --outfile hirelens-f16.gguf

# Q4_K_M gives more bits to the layers that are most sensitive to precision loss, which is
# why it holds up better than a flat 4-bit cast. Q5_K_M is the fallback if output degrades.
./llama.cpp/build/bin/llama-quantize hirelens-f16.gguf hirelens-q4.gguf "$QUANT"

rm -f hirelens-f16.gguf
ls -lh hirelens-q4.gguf

echo
echo "Check it before deploying it:"
echo "  ./llama.cpp/build/bin/llama-cli -m hirelens-q4.gguf -p 'RESUME: ... JOB DESCRIPTION: ...' -n 512"
