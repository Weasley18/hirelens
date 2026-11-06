# Docker, Kubernetes and container operations

## Images, layers and build time

Ask what makes a Docker build slow and what they did about it. Expect layer caching, ordering
the Dockerfile so dependency installation comes before copying source, and multi-stage builds
to keep the runtime image small. A useful probe: what is actually in your production image
that does not need to be, and how would you find out? Candidates who have only written a
Dockerfile from a template will describe the file but not its size or its attack surface.

## Container versus virtual machine

For less senior candidates, ask what a container shares with the host that a VM does not.
The answer is the kernel: containers are isolated processes using namespaces and cgroups,
not separate machines. Follow up with why that makes startup fast and why it makes kernel
version assumptions dangerous.

## Kubernetes core objects

Ask them to explain the path from a Deployment to a running container: Deployment manages a
ReplicaSet, ReplicaSet manages Pods, a Pod is one or more containers sharing a network
namespace. Then ask what a Service actually does, and listen for stable virtual IP and label
selectors rather than "it exposes the app". A candidate who has only used a managed platform
often knows the YAML but not what reconciles it.

## Debugging a failing pod

Give a scenario: a pod is in CrashLoopBackOff. Walk me through your first five minutes.
Strong answers are ordered — describe the pod for events, check logs including the previous
container's logs, check the readiness and liveness probes, check resource limits for an OOM
kill, then check whether it is config or image. Listen for someone who checks events before
guessing.

## Requests, limits and eviction

Ask the difference between a resource request and a limit. Requests drive scheduling, limits
drive throttling and OOM kills. A good follow-up: what happens to a container that exceeds
its CPU limit versus its memory limit? CPU is throttled, memory is killed. Candidates who
have run production workloads usually have an opinion about setting CPU limits at all.

## Rolling deployments and readiness

Ask how Kubernetes avoids sending traffic to a pod that is still starting. Readiness probes
should come up, and the distinction from liveness probes: readiness removes a pod from the
Service, liveness restarts it. Ask what goes wrong when a liveness probe is pointed at an
endpoint that depends on a downstream service — cascading restarts during an unrelated outage.

## Probing a candidate whose experience stops at Docker Compose

If the resume shows Compose but the role needs Kubernetes, do not ask Kubernetes trivia. Ask
what they expect to be genuinely different about operating the same service on Kubernetes,
and what they would want to learn first. Candidates who reason about scheduling, self-healing,
and declarative reconciliation are showing transferable understanding; candidates who say it
is "basically Compose at scale" are showing the gap without knowing it.

## Secrets and configuration

Ask how configuration reaches their containers, and how secrets differ from config. Expect
environment variables or mounted files, ConfigMaps and Secrets, and awareness that a
Kubernetes Secret is base64-encoded rather than encrypted by default. Senior candidates will
mention an external secret store and rotation.
