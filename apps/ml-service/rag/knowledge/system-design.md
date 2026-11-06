# System design and distributed systems

## Framing a design question

For a mid or senior candidate, give an open prompt — design a URL shortener, a notification
service, a feed — and grade the process rather than the answer. Strong candidates clarify
requirements and scale before drawing anything, state assumptions out loud, and name the one
or two hard parts early. Candidates who start listing technologies before asking what the
system needs to do are showing recall rather than design.

## Estimating scale

Ask for a rough calculation: requests per second, storage growth per year, read-to-write
ratio. Precision does not matter and the order of magnitude does, because it determines
whether the answer is one database or a very different architecture. A candidate who cannot
tell whether they are designing for 100 or 100,000 requests per second will over-engineer or
under-engineer without knowing which.

## Consistency and availability

Ask them to describe a part of a system where they chose eventual consistency, and what the
user actually experiences as a result. Concrete answers — a count that lags, a profile update
that takes a moment to propagate — beat a recitation of CAP. Follow up: which part of your
system could never be eventually consistent, and why?

## Data partitioning

Ask how they would shard a dataset that no longer fits on one node, and what query becomes
expensive afterwards. Any sharding key makes cross-shard queries painful; the signal is
whether they anticipate which queries those are. Ask about rebalancing when a shard gets hot.

## Failure modes and blast radius

Ask what happens to their design when one dependency is down, and then when it is slow, which
is worse. Timeouts, bulkheads, and graceful degradation are the vocabulary. A candidate who
has operated a system will usually volunteer that a slow dependency takes down a service more
often than a failed one does.

## Event-driven architecture

Ask what they gain and lose by putting a message broker between two services. Decoupling and
buffering against load, at the cost of eventual consistency, harder debugging, and ordering
questions. Ask how they would trace one user action across five services, and listen for
correlation IDs and distributed tracing.

## Migrating a live system

Ask how they would replace a database or a service without downtime. The expected shape is
dual writes or a change-data-capture stream, a backfill, a read cutover behind a flag, and a
rollback plan. Ask how they verified the new path matched the old one; shadow reads and
comparison are the strong answer.

## Designing for the team, not just the traffic

For senior candidates, ask how team structure influenced an architecture decision. Service
boundaries drawn around team ownership, or a monolith kept deliberately because the team was
small, are mature answers. A candidate who has never considered the organisational cost of
their architecture is likely to propose microservices for four engineers.
