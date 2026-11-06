# Cloud, AWS and operations

## Serverless tradeoffs

Ask when they would not use a Lambda. Good answers name cold starts for latency-sensitive
paths, execution time limits for long jobs, and the cost crossover where steady traffic makes
a container cheaper than per-invocation billing. Ask how they handled a cold start, and
listen for smaller packages, provisioned concurrency, and an honest admission of the cost.

## Infrastructure as code

Ask what breaks when infrastructure is changed by hand in the console. Drift, unreproducible
environments, and a review process that only covers application code. Ask what happens when
a Terraform apply fails halfway; state, partial application, and the recovery path are what
distinguish someone who has used it from someone who has read the tutorial.

## IAM and least privilege

Ask how they decide what permissions a service gets. The strong pattern is starting from
nothing and adding what fails, rather than starting broad and intending to narrow later. Ask
what a wildcard resource in a policy actually allows, and whether they have ever audited one.

## CI/CD pipelines

Ask what runs between a merge and production, and what can stop a deploy. Tests, build,
artifact publication, and a deployment gate are the expected stages. Follow up on rollback:
how long does it take and has it been used? A pipeline nobody has rolled back is a pipeline
nobody has tested.

## Cost awareness

Ask about a cloud bill they reduced or a cost they were surprised by. Data transfer between
availability zones, idle provisioned capacity, and log retention are common real answers.
This question also reveals whether they see infrastructure as something they own or something
another team pays for.

## Monitoring and alerting

Ask what pages them at 3am and whether it should. Good answers distinguish alerts that
require human action from dashboards that inform. Ask how they reduced alert noise; deleting
an alert is a legitimate and underrated answer.

## Deployment strategies

Ask them to compare blue-green with a rolling deploy and with a canary. What matters is
whether they can say what each one costs — duplicate capacity, slower rollout, or the
observability required to judge a canary. Ask what signal would abort their rollout.

## Incident response

Ask them to describe an incident they were part of, specifically what they did and what they
learned. Listen for structure: detection, mitigation before diagnosis, communication, and a
follow-up that changed something. Blameless framing and a concrete action item afterwards are
strong signals; a story that ends with the fix and no prevention is incomplete.
