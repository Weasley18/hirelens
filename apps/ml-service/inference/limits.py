"""Size limits shared by training, inference and the API's input caps.

One number drives the model's context window everywhere: the training sequence length, the
llama.cpp context at serving time, and the merge/eval loaders. A model served with a different
window from the one it was trained on degrades quietly, so changing CONTEXT_TOKENS means
retraining, re-exporting and re-evaluating.

The character caps are sized so a maximum-length resume plus job description, the retrieval
budget and the system prompt still leave OUTPUT_TOKENS of room at roughly 3.5 characters per
token (typical for English resume text with names and numbers). The real tokenizer check in
inference.llm remains the final gate for unusually dense text.

packages/shared/src/analysis.ts mirrors RESUME_MAX and JD_MAX; tests/test_limits.py fails if
the two drift apart.
"""

CONTEXT_TOKENS = 6144
OUTPUT_TOKENS = 800

RESUME_MIN = 80
RESUME_MAX = 8000
JD_MIN = 60
JD_MAX = 6000

# Conservative characters-per-token figure used only for the static budget check.
CHARS_PER_TOKEN_ESTIMATE = 3.5
