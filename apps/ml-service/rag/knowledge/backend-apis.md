# Backend services, APIs and queues

## API design and versioning

Ask how they would add a required field to a response that mobile clients depend on. Good
answers separate additive changes from breaking ones and describe a versioning strategy they
have actually lived with. Follow up: how do you know when nobody is using v1 any more? The
answer involves telemetry per version, which distinguishes people who have deprecated an API
from people who have only designed one.

## Idempotency

Give a scenario: a payment request times out at the client and is retried. How do you make
sure the customer is not charged twice? Expect an idempotency key supplied by the client,
stored with the result, so a repeat of the same key returns the original outcome rather than
performing the work again. Strong candidates mention where that record lives and what happens
when two identical requests arrive concurrently.

## Job queues and background work

Ask why a slow operation belongs in a queue rather than in the request. Then push on the
hard parts: what happens when a worker dies mid-job, how do you avoid running the same job
twice, and how does the client learn the result? Listen for at-least-once delivery, visibility
timeouts or stalled-job detection, retries with backoff, and either polling or a push channel
for results. A candidate who says "we use a queue" without describing failure handling has
used one without operating one.

## Retries, backoff and the thundering herd

Ask what is wrong with retrying a failed downstream call three times immediately. Expect
amplification of load on an already-struggling service. Good answers add exponential backoff
and jitter, and a circuit breaker so a hard-down dependency fails fast rather than consuming
every worker thread.

## Caching and invalidation

Ask what they cache and how it gets invalidated. Push on the second part — TTL, explicit
invalidation on write, or versioned keys — and on what happens when the cache is empty and
every request misses at once. Cache stampede protection, single-flight, and stale-while-
revalidate are strong signals. Ask about the consequences of serving stale data in their
specific domain; the right answer differs for a price and for a profile photo.

## Authentication and sessions

Ask them to compare a server-side session with a stateless JWT. Expect the tradeoff to come
out as revocation versus scaling: sessions can be invalidated immediately but need shared
state, tokens scale without lookups but stay valid until they expire. Ask how they would
revoke a JWT before expiry, and listen for short expiry plus refresh tokens, or a denylist
that reintroduces the state they were avoiding.

## Rate limiting

Ask how they would stop one client from exhausting a shared service. Fixed window, sliding
window, and token bucket are all acceptable; what matters is that they can describe the
burst behaviour of the one they picked. Follow up: what do you rate limit by when your users
are behind a corporate NAT?

## Observability and debugging production

Ask about the last production incident they debugged and what told them where to look.
Strong answers name a signal — a latency percentile, an error rate, a saturated pool — rather
than "we checked the logs". Ask what they would add to make the next incident faster, and
listen for structured logs with a request ID, tracing across services, and alerting on
symptoms rather than causes.

## Latency percentiles

Ask why p99 matters when the average looks fine. Expect an explanation that averages hide the
tail and that a user making several requests per page is likely to hit the tail at least once.
Candidates who have done performance work will mention where the tail came from: garbage
collection, connection pool waits, a cold cache, or a chatty N+1 query pattern.
