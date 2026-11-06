"""Pull the technologies out of a resume and a job description.

This runs on every request, ahead of the model, purely to decide what to retrieve. A second
LLM call would be more flexible and would also double the latency and the cost of the slowest
part of the request, so it is a dictionary lookup instead. Retrieval is forgiving: a missed
skill means slightly less context, not a wrong answer.

Aliases matter more than coverage here — a JD saying "k8s" and a knowledge base filed under
"Kubernetes" must end up at the same chunks.
"""

from __future__ import annotations

import re

# canonical name -> spellings that should map to it
SKILL_ALIASES: dict[str, list[str]] = {
    "Python": ["python"],
    "JavaScript": ["javascript", "js", "es6"],
    "TypeScript": ["typescript", "ts"],
    "Java": ["java"],
    "Go": ["golang", "go lang"],
    "Rust": ["rust"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", ".net", "dotnet"],
    "Ruby": ["ruby", "rails", "ruby on rails"],
    "PHP": ["php", "laravel"],
    "Swift": ["swift", "swiftui"],
    "Kotlin": ["kotlin"],
    "SQL": ["sql"],
    "React": ["react", "react.js", "reactjs"],
    "React Native": ["react native"],
    "Next.js": ["next.js", "nextjs"],
    "Vue": ["vue", "vue.js", "vuejs"],
    "Angular": ["angular"],
    "Node.js": ["node.js", "nodejs", "node"],
    "Express": ["express", "express.js"],
    "Fastify": ["fastify"],
    "NestJS": ["nestjs", "nest.js"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi"],
    "Spring": ["spring", "spring boot"],
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "MySQL": ["mysql", "mariadb"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "opensearch"],
    "DynamoDB": ["dynamodb"],
    "Cassandra": ["cassandra"],
    "Kafka": ["kafka"],
    "RabbitMQ": ["rabbitmq"],
    "GraphQL": ["graphql", "apollo"],
    "REST APIs": ["rest", "restful", "rest api", "rest apis"],
    "gRPC": ["grpc"],
    "Docker": ["docker", "containerization", "containerisation"],
    "Kubernetes": ["kubernetes", "k8s", "eks", "gke"],
    "Terraform": ["terraform", "infrastructure as code", "iac"],
    "AWS": ["aws", "amazon web services", "lambda", "s3", "ec2"],
    "GCP": ["gcp", "google cloud"],
    "Azure": ["azure"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "github actions", "jenkins", "gitlab ci"],
    "Linux": ["linux", "unix", "bash"],
    "Observability": ["observability", "prometheus", "grafana", "datadog", "opentelemetry"],
    "Microservices": ["microservice", "microservices"],
    "System design": ["system design", "distributed systems", "scalability"],
    "Testing": ["unit test", "integration test", "pytest", "jest", "playwright", "cypress", "tdd"],
    "Security": ["owasp", "penetration testing", "threat model", "appsec", "security"],
    "Machine learning": ["machine learning", "ml", "scikit-learn", "sklearn"],
    "Deep learning": ["deep learning", "pytorch", "tensorflow", "neural network"],
    "LLMs": ["llm", "large language model", "rag", "fine-tuning", "fine tuning", "prompt engineering"],
    "Data engineering": ["etl", "elt", "airflow", "dbt", "spark", "data pipeline", "data warehouse"],
    "pandas": ["pandas", "numpy"],
    "Statistics": ["statistics", "a/b test", "ab testing", "experimentation", "hypothesis test"],
    "Git": ["git", "github", "gitlab", "version control"],
    "Agile": ["agile", "scrum", "kanban", "sprint"],
    "Mentoring": ["mentor", "mentoring", "mentored", "coaching"],
    "Technical leadership": ["tech lead", "technical lead", "team lead", "leading a team"],
    "Accessibility": ["accessibility", "a11y", "wcag"],
    "Performance": ["performance optimization", "performance optimisation", "latency", "profiling"],
}

# Longest aliases first so "react native" is matched before "react".
_ORDERED = sorted(
    ((alias, canonical) for canonical, aliases in SKILL_ALIASES.items() for alias in aliases),
    key=lambda pair: -len(pair[0]),
)


def extract_skills(*texts: str, limit: int = 12) -> list[str]:
    """Canonical skill names found in the given text, most-mentioned first.

    Ordering by mention count is what makes the retrieval budget go to the technologies the
    documents actually centre on, rather than something listed once in a footer.
    """
    haystack = " ".join(texts).lower()
    counts: dict[str, int] = {}

    for alias, canonical in _ORDERED:
        pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
        found = len(re.findall(pattern, haystack))
        if found:
            counts[canonical] = counts.get(canonical, 0) + found

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [skill for skill, _ in ranked[:limit]]


def jd_only_skills(resume: str, jd: str, limit: int = 6) -> list[str]:
    """Skills the job description asks for and the resume never mentions.

    These are the likely gaps, and they are the most valuable thing to retrieve context
    for — the questions that probe a gap are the hardest ones for the model to invent well.
    """
    resume_skills = set(extract_skills(resume, limit=100))
    return [s for s in extract_skills(jd, limit=100) if s not in resume_skills][:limit]
