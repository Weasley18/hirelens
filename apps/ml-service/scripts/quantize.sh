#!/usr/bin/env bash
# Supply an immutable llama.cpp commit tested with the deployed llama-cpp-python runtime.
set -euo pipefail
MERGED_DIR="${1:-hirelens-merged}"
QUANT="${QUANT:-Q4_K_M}"
: "${LLAMA_CPP_REVISION:?set LLAMA_CPP_REVISION to an exact tested commit hash}"
[[ "$LLAMA_CPP_REVISION" =~ ^[0-9a-f]{40}$ ]] || { echo "Expected a 40-character commit" >&2; exit 1; }
[ -f "$MERGED_DIR/training-manifest.json" ] || { echo "Merged model provenance missing" >&2; exit 1; }
# Each revision owns a checkout/build: interrupted builds can be resumed safely.
TOOL_DIR=".toolchains/llama-${LLAMA_CPP_REVISION}"
if [ ! -d "$TOOL_DIR/.git" ]; then
  mkdir -p "$TOOL_DIR"
  git -C "$TOOL_DIR" init
  git -C "$TOOL_DIR" remote add origin https://github.com/ggerganov/llama.cpp
fi
git -C "$TOOL_DIR" fetch --depth 1 origin "$LLAMA_CPP_REVISION"
git -C "$TOOL_DIR" checkout --detach "$LLAMA_CPP_REVISION"
[ -z "$(git -C "$TOOL_DIR" status --porcelain --untracked-files=no)" ] || { echo "Toolchain has modified tracked files" >&2; exit 1; }
python -m pip install -r "$TOOL_DIR/requirements.txt"
cmake -B "$TOOL_DIR/build" -S "$TOOL_DIR" -DCMAKE_BUILD_TYPE=Release
cmake --build "$TOOL_DIR/build" --config Release -j --target llama-quantize llama-cli
python "$TOOL_DIR/convert_hf_to_gguf.py" "$MERGED_DIR" --outfile hirelens-f16.gguf
"$TOOL_DIR/build/bin/llama-quantize" hirelens-f16.gguf hirelens-q4.gguf "$QUANT"
python - "$MERGED_DIR" "$LLAMA_CPP_REVISION" "$QUANT" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
artifact = Path('hirelens-q4.gguf')
digest = hashlib.sha256()
with artifact.open('rb') as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
manifest = json.loads(Path(sys.argv[1], 'training-manifest.json').read_text())
manifest.update(llama_cpp_revision=sys.argv[2], quantization=sys.argv[3], gguf_sha256=digest.hexdigest())
Path('hirelens-q4.manifest.json').write_text(json.dumps(manifest, indent=2))
Path('quantization-requirements.lock').write_text(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True))
PY
rm -f hirelens-f16.gguf
printf 'Exported hirelens-q4.gguf and provenance manifest. Evaluate with the deployed runtime before release.\n'
