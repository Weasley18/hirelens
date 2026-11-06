import json
from pathlib import Path

from common import validate_analysis
from data_gen.curate import consistency_issues, grounding_issues, review
from inference.llm import _generate_stub
from inference.prompt import MAX_CONTEXT_CHARS, build_chat_prompt, build_user_turn, format_context
from inference.skills import extract_skills, jd_only_skills
from training.evaluate import evaluate_generations

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[3] / "packages" / "shared" / "fixtures" / "sample-analysis.json").read_text()
)

RESUME = """Senior backend engineer with six years building Node.js services.
Built a Fastify API backed by PostgreSQL and Redis, processing 2M jobs per day.
Cut p95 latency from 800ms to 120ms by fixing N+1 queries and adding a read-through cache.
Containerised the service with Docker and shipped it through GitHub Actions.
Skills: TypeScript, Node.js, PostgreSQL, Redis, Docker, REST APIs."""

JD = """We are hiring a senior backend engineer.
You will own services running on Kubernetes, provisioned with Terraform on AWS.
Requirements: strong Node.js and PostgreSQL, 2+ years of Kubernetes in production,
experience with Terraform, and a track record of mentoring junior engineers."""

CHUNKS = [
    {"id": "1", "content": "Kubernetes core objects. Ask them to explain the path from a Deployment to a running container.",
     "source": "Docker, Kubernetes and container operations: Kubernetes core objects", "similarity": 0.7},
    {"id": "2", "content": "Indexing and query plans. Probe whether the candidate has read a query plan.",
     "source": "PostgreSQL and relational data modelling: Indexing and query plans", "similarity": 0.6},
]


class TestSkillExtraction:
    def test_finds_skills_in_a_resume(self):
        skills = extract_skills(RESUME)
        assert "PostgreSQL" in skills and "Redis" in skills and "Docker" in skills

    def test_matches_aliases(self):
        assert "Kubernetes" in extract_skills("We run k8s in production")
        assert "TypeScript" in extract_skills("Strong TS background")
        assert "CI/CD" in extract_skills("Pipelines built with GitHub Actions")

    def test_prefers_the_longest_alias(self):
        skills = extract_skills("Built mobile apps with React Native")
        assert "React Native" in skills

    def test_does_not_match_inside_other_words(self):
        assert "Go" not in extract_skills("Good at going fast; a goal-oriented engineer")
        assert "Rust" not in extract_skills("Trustworthy and robust")

    def test_ranks_by_mention_count(self):
        text = "PostgreSQL PostgreSQL PostgreSQL and a little Docker"
        assert extract_skills(text)[0] == "PostgreSQL"

    def test_jd_only_skills_are_the_likely_gaps(self):
        gaps = jd_only_skills(RESUME, JD)
        assert "Kubernetes" in gaps and "Terraform" in gaps

    def test_jd_only_excludes_what_the_resume_has(self):
        gaps = jd_only_skills(RESUME, JD)
        assert "PostgreSQL" not in gaps and "Node.js" not in gaps

    def test_empty_input_is_not_an_error(self):
        assert extract_skills("") == []
        assert jd_only_skills("", "") == []


class TestPrompt:
    def test_user_turn_contains_both_documents(self):
        turn = build_user_turn(RESUME, JD)
        assert "RESUME:" in turn and "JOB DESCRIPTION:" in turn

    def test_context_block_only_appears_when_there_is_context(self):
        assert "RELEVANT REFERENCE MATERIAL" not in build_user_turn(RESUME, JD)
        assert "RELEVANT REFERENCE MATERIAL" in build_user_turn(RESUME, JD, CHUNKS)

    def test_context_carries_the_source_label(self):
        assert 'source: "PostgreSQL' in build_user_turn(RESUME, JD, CHUNKS)

    def test_context_is_capped_so_the_resume_still_fits(self):
        many = [{"content": "x" * 500, "source": "s"} for _ in range(20)]
        assert len(format_context(many)) <= MAX_CONTEXT_CHARS + 600

    def test_chat_prompt_uses_qwens_template_and_ends_ready_to_generate(self):
        prompt = build_chat_prompt(RESUME, JD, CHUNKS)
        assert prompt.startswith("<|im_start|>system\n")
        assert prompt.count("<|im_end|>") == 2
        assert prompt.endswith("<|im_start|>assistant\n")


class TestCuration:
    def test_a_clean_analysis_has_no_issues(self):
        assert consistency_issues(FIXTURE) == []

    def test_high_score_with_a_severe_gap_is_flagged(self):
        analysis = {**FIXTURE, "fitScore": 92}
        analysis["gaps"] = [{"skill": "Go", "severity": "severe", "note": "n" * 20}]
        assert consistency_issues(analysis) != []

    def test_high_score_with_many_gaps_is_flagged(self):
        analysis = {**FIXTURE, "fitScore": 95}
        assert consistency_issues(analysis) != []

    def test_low_score_with_no_gaps_is_flagged(self):
        analysis = {**FIXTURE, "fitScore": 20, "gaps": []}
        assert consistency_issues(analysis) != []

    def test_duplicate_questions_are_flagged(self):
        analysis = {**FIXTURE}
        analysis["interviewQuestions"] = [FIXTURE["interviewQuestions"][0]] * 2
        assert any("duplicate" in issue for issue in consistency_issues(analysis))

    def test_gap_grounded_in_the_jd_passes(self):
        assert grounding_issues({"jd": JD, "output": {"gaps": [{"skill": "Kubernetes"}]}}) == []

    def test_gap_the_jd_never_mentions_is_flagged(self):
        issues = grounding_issues({"jd": JD, "output": {"gaps": [{"skill": "COBOL"}]}})
        assert len(issues) == 1 and "COBOL" in issues[0]

    def test_multiword_gap_is_resolved_through_the_skill_vocabulary(self):
        # "Team mentoring" resolves to Mentoring, which the JD asks for in different words.
        assert grounding_issues({"jd": JD, "output": {"gaps": [{"skill": "Team mentoring"}]}}) == []

    def test_unresolvable_phrase_is_left_alone_rather_than_wrongly_flagged(self):
        # The JD says "mentoring junior engineers"; no lexical overlap, but not an invention.
        assert grounding_issues({"jd": JD, "output": {"gaps": [{"skill": "Team leadership"}]}}) == []

    def test_alias_spelling_still_counts_as_grounded(self):
        jd = "You will run services on k8s and provision them with Terraform."
        assert grounding_issues({"jd": jd, "output": {"gaps": [{"skill": "Kubernetes"}]}}) == []

    def test_review_combines_schema_and_heuristic_failures(self):
        broken = {"resume": RESUME, "jd": JD, "output": {**FIXTURE, "fitScore": 999}}
        assert len(review(broken)) >= 1

    def test_review_accepts_a_good_example(self):
        assert review({"resume": RESUME, "jd": JD, "output": FIXTURE}) == []


class TestStubBackend:
    def test_output_matches_the_shared_schema(self):
        assert validate_analysis(_generate_stub(RESUME, JD, CHUNKS)) == []

    def test_output_is_valid_without_any_retrieved_context(self):
        assert validate_analysis(_generate_stub(RESUME, JD, [])) == []

    def test_gaps_come_from_the_job_description(self):
        skills = {gap["skill"] for gap in _generate_stub(RESUME, JD, CHUNKS)["gaps"]}
        assert "Kubernetes" in skills

    def test_questions_are_drawn_from_retrieved_context(self):
        questions = _generate_stub(RESUME, JD, CHUNKS)["interviewQuestions"]
        assert any("Deployment" in q["question"] for q in questions)

    def test_is_deterministic(self):
        assert _generate_stub(RESUME, JD, CHUNKS) == _generate_stub(RESUME, JD, CHUNKS)

    def test_a_close_match_scores_higher_than_a_poor_one(self):
        unrelated = "Pastry chef with eight years in fine dining. Skills: lamination, plating."
        assert (
            _generate_stub(RESUME, JD, [])["fitScore"]
            > _generate_stub(unrelated, JD, [])["fitScore"]
        )


class TestEvaluation:
    def test_perfect_generations_report_full_rates(self):
        raw = [json.dumps(FIXTURE)]
        report = evaluate_generations(raw, [{"output": FIXTURE}])
        assert report["json_valid_rate"] == 1.0
        assert report["schema_valid_rate"] == 1.0
        assert report["score_mae"] == 0

    def test_unparseable_output_is_counted_and_explained(self):
        report = evaluate_generations(["I cannot do that"], [{"output": FIXTURE}])
        assert report["json_valid_rate"] == 0.0
        assert "unparseable" in report["failures"][0]["reason"]

    def test_parseable_but_wrong_shape_separates_the_two_rates(self):
        report = evaluate_generations(['{"fitScore": 80}'], [{"output": FIXTURE}])
        assert report["json_valid_rate"] == 1.0
        assert report["schema_valid_rate"] == 0.0

    def test_score_mae_measures_distance_from_the_teacher(self):
        off_by_ten = {**FIXTURE, "fitScore": FIXTURE["fitScore"] + 10}
        report = evaluate_generations([json.dumps(off_by_ten)], [{"output": FIXTURE}])
        assert report["score_mae"] == 10

    def test_empty_run_does_not_divide_by_zero(self):
        assert evaluate_generations([], [])["json_valid_rate"] == 0.0
