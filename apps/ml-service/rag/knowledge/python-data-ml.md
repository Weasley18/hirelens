# Python, data engineering and machine learning

## Python fundamentals worth probing

Ask about mutable default arguments, or what a generator gives you that a list does not.
For anyone claiming performance work, ask what the GIL prevents and what it does not —
threads still help for IO-bound work, and multiprocessing or native extensions are the answer
for CPU-bound work. Candidates who describe the GIL as making Python single-threaded for all
purposes are repeating a summary rather than reasoning.

## Pipelines and orchestration

Ask how a scheduled pipeline recovers from a failed run halfway through. Expect idempotent
tasks, partitioned outputs that can be rewritten safely, and backfill as a first-class
operation rather than a manual rerun. Follow up: how does a downstream consumer know the data
for yesterday is complete? Listen for explicit completion markers or data quality checks
rather than trusting a schedule.

## Data quality

Ask what checks run on their data before anyone consumes it. Row counts against expectation,
null rates, referential checks, and distribution drift are all real answers. Ask what happens
when a check fails — alerting without a defined stop condition means bad data still reaches
dashboards.

## SQL for analytics

Ask them to describe a window function they have used and why a GROUP BY would not have
worked. Ask about deduplicating rows while keeping the most recent per key; ROW_NUMBER with
a partition is the expected shape. Candidates who only know ORM query builders often stall
here, which is useful to know for a data role.

## Model evaluation

Ask why accuracy is the wrong metric for their problem, and what they used instead. Expect
class imbalance to come up, along with precision and recall and which one the business cares
about. A strong probe: what threshold did you pick and who decided the cost of a false
positive? That question separates people who trained a model from people who shipped one.

## Train-test discipline

Ask how they split their data and whether anything leaked. Time-based splits for temporal
data, grouping by entity so the same user does not appear on both sides, and fitting scalers
only on the training set are the signals. Anyone who reports a suspiciously high score should
be asked what they did to rule out leakage.

## Serving and monitoring models

Ask what happens to a deployed model six months later. Expect drift in inputs, changed
upstream data, and the need for monitoring predictions rather than just service health. Ask
how they would roll back a bad model, and listen for versioned artifacts and a way to
reproduce a prediction after the fact.

## Working with LLMs

For candidates claiming LLM experience, ask what they did beyond calling an API. Useful
signals: they can explain why retrieval helped for their problem, what chunking strategy
they chose and what they rejected, how they evaluated output quality, and what their fallback
is when the model returns something unparseable. Ask about cost and latency, which is where
prototype work and production work diverge most sharply.
