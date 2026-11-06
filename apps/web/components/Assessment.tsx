import type { AnalysisResult } from "@hirelens/shared";

const SEVERITY_LABEL: Record<string, string> = {
  minor: "worth a question",
  moderate: "needs probing",
  severe: "likely blocker",
};

/**
 * The score is the one loud element on the page. It is a numeral with a marker stroke under
 * it, because the gesture a recruiter actually makes on a resume is annotation, not a gauge.
 */
function Score({ value }: { value: number }) {
  return (
    <div className="flex items-baseline gap-4">
      <div className="relative">
        <span className="font-document text-[5.5rem] leading-[0.85] tracking-tight">{value}</span>
        <svg
          className="absolute -bottom-2 left-0 w-full"
          height="10"
          viewBox="0 0 120 10"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path
            d="M2 7 C 28 3, 52 8, 78 4 S 112 6, 118 3"
            fill="none"
            stroke="var(--mark)"
            strokeWidth="4"
            strokeLinecap="round"
            opacity="0.85"
          />
        </svg>
      </div>
      <span className="font-ui text-sm text-ink-soft">out of 100</span>
    </div>
  );
}

export default function Assessment({ result }: { result: AnalysisResult }) {
  return (
    <div className="settle">
      <Score value={result.fitScore} />

      <p className="measure mt-8 text-[1.15rem] leading-relaxed">{result.verdict}</p>

      <section className="mt-10 border-t border-rule pt-6">
        <h2 className="font-ui text-sm font-semibold text-ink-soft">What the resume supports</h2>
        <ul className="mt-3 space-y-2">
          {result.strengths.map((strength) => (
            <li key={strength} className="measure flex gap-3">
              <span aria-hidden="true" className="mt-[0.55em] h-[6px] w-[6px] shrink-0 bg-mark" />
              <span>{strength}</span>
            </li>
          ))}
        </ul>
      </section>

      {result.gaps.length > 0 && (
        <section className="mt-10 border-t border-rule pt-6">
          <h2 className="font-ui text-sm font-semibold text-ink-soft">
            What the role asks for and the resume does not show
          </h2>
          <ul className="mt-4 space-y-5">
            {result.gaps.map((gap) => (
              <li key={gap.skill} className="measure border-l-2 border-flag pl-4">
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <span className="font-semibold">{gap.skill}</span>
                  <span className="font-ui text-xs text-flag">
                    {SEVERITY_LABEL[gap.severity] ?? gap.severity}
                  </span>
                </div>
                <p className="mt-1 text-[0.97rem] text-ink-soft">{gap.note}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-10 border-t border-rule pt-6">
        {/* Numbered because an interviewer works through these in order — it is a sequence. */}
        <h2 className="font-ui text-sm font-semibold text-ink-soft">Questions to ask</h2>
        <ol className="mt-4 space-y-6">
          {result.interviewQuestions.map((item, index) => (
            <li key={item.question} className="measure flex gap-4">
              <span className="font-document text-xl text-ink-soft" aria-hidden="true">
                {index + 1}
              </span>
              <div>
                <p>{item.question}</p>
                <p className="mt-1 font-ui text-xs text-ink-soft">
                  Probes {item.targets}, pitched at {item.difficulty} level
                </p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
