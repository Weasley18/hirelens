"""The spread of the training set, written down explicitly.

Fine-tuning on 300 backend-engineer examples produces a model that only understands
backend engineers. These axes are multiplied together in make_pairs.py so the dataset
covers roles, levels and awkward cases rather than one narrow pattern.
"""

ROLES = [
    ("Backend engineer", "Node.js, PostgreSQL, Redis, REST APIs, job queues"),
    ("Frontend engineer", "React, TypeScript, state management, accessibility, build tooling"),
    ("Full-stack engineer", "React plus Python or Node, relational databases, deployment"),
    ("Data engineer", "Python, Spark, Airflow, data warehousing, dbt, SQL"),
    ("Data scientist", "Python, pandas, scikit-learn, experimentation, statistics"),
    ("ML engineer", "PyTorch, model serving, feature pipelines, evaluation"),
    ("DevOps / platform engineer", "Kubernetes, Terraform, CI/CD, observability, AWS"),
    ("Mobile engineer", "React Native or Swift/Kotlin, offline sync, app store release"),
    ("QA / automation engineer", "Playwright or Selenium, test strategy, CI integration"),
    ("Security engineer", "threat modelling, SAST/DAST, IAM, incident response"),
]

SENIORITIES = [
    ("junior", "0-2 years, one or two employers or internships, mostly feature work"),
    ("mid", "3-5 years, owns services or features end to end, some design input"),
    ("senior", "6-10 years, leads projects, mentors, makes architecture decisions"),
]

# Cases that break a model trained only on clean, well-matched pairs.
TWISTS = [
    "a strong, straightforward match for the role",
    "a near-miss: right level, adjacent tech stack (e.g. Django where the JD wants Rails)",
    "a career changer from a non-CS background with a bootcamp and one relevant project",
    "over-qualified: clearly more senior than the job description asks for",
    "under-qualified: one level below what the job description asks for",
    "a generalist applying to a specialist role",
    "a candidate with a two-year employment gap, since returned to work",
    "strong on paper but with vague, unquantified achievements",
]
