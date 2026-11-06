# PostgreSQL and relational data modelling

## Indexing and query plans

Probe whether the candidate has read a query plan rather than guessed at one. Ask them to
describe a query they made faster and what `EXPLAIN ANALYZE` showed before and after. Strong
answers mention seeing a sequential scan on a large table, a bad row estimate, or a nested
loop that should have been a hash join. Follow up with: why does adding an index sometimes
not help, and when does the planner ignore one? Expect mentions of low selectivity, functions
applied to the indexed column, or type mismatches in the predicate. A candidate who has only
ever added indexes speculatively will describe the index but not the measurement.

## Composite indexes and column order

Ask why the order of columns in a composite index matters, and when an index on (a, b) serves
a query filtering only on b. Mid-level candidates should know the leftmost-prefix rule.
Senior candidates should be able to describe choosing order by selectivity and by which
column appears in range predicates versus equality predicates. A good scenario question:
given a table queried by tenant_id plus a date range, what index would you create and why.

## Transactions and isolation levels

Ask what problem READ COMMITTED still allows that REPEATABLE READ does not. Expect
non-repeatable reads and phantom reads to come up by name or by description. A practical
follow-up: two concurrent requests both read a balance, both subtract from it, both write.
What happens under each isolation level, and how would you prevent the lost update? Strong
answers reach for SELECT FOR UPDATE, an atomic UPDATE with an arithmetic expression, or an
optimistic version column, and can say what each costs under contention.

## Schema design and normalisation

Give them a scenario: a multi-tenant SaaS product where every table needs to be scoped to a
customer. Ask them to walk through the options — a tenant_id column on every table, a schema
per tenant, a database per tenant — and name the tradeoffs in migration cost, isolation, and
the blast radius of a bug. Listen for whether they consider row-level security and how they
would stop a missing WHERE clause from leaking data across tenants.

## Migrations against a live table

Ask what happens when you add a NOT NULL column with a default to a 50-million-row table in
production. Candidates with real operational experience will mention table rewrites, lock
duration, and that recent PostgreSQL versions handle the default case without a full rewrite.
Ask how they would add an index without blocking writes; CREATE INDEX CONCURRENTLY should
come up, along with the fact that it can fail and leave an invalid index behind.

## Partitioning and large tables

For candidates claiming large-scale data work, ask how they chose a partition key and what
queries got worse as a result. Partitioning helps when the partition key is in the predicate
and hurts when it is not, because the planner then touches every partition. Ask what they do
with old partitions, and listen for detaching rather than deleting rows.

## Connection pooling

Ask why a serverless or high-concurrency application needs a connection pooler in front of
PostgreSQL. Expect: every connection is a backend process with real memory cost, and
connection count does not scale the way request concurrency does. PgBouncer in transaction
mode is the common answer; a strong candidate knows that transaction mode breaks session-level
features like prepared statements and advisory locks.

## JSON columns and when to avoid them

Ask when they would reach for jsonb instead of a normalised table. Good answers: genuinely
schemaless attributes, third-party payloads stored verbatim, sparse fields. Good warnings:
you lose referential integrity and column-level constraints, queries get harder to index, and
jsonb becomes a way to avoid making a schema decision rather than a decision in itself.
