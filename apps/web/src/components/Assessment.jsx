import { useState } from "react";
import Icon from "./Icon";
import { context } from "@/lib/citations";
const SEVERITY_LABEL = { minor: "Worth a question", moderate: "Needs probing", severe: "Likely blocker" };

/** A claim's quote. Clicking shows it highlighted in its original document, in context. */
function Quote({ text, source, label }) {
    const [open, setOpen] = useState(false);
    const found = open && source ? context(text, source) : null;
    return <div className="citation">
        <button type="button" className="quote" aria-expanded={open} onClick={() => setOpen(!open)}
            title={open ? "Hide context" : `Show this quote in the ${label.toLowerCase()}`}>
            <span className="quote-source">{label}</span>“{text}”</button>
        {open && <blockquote className="quote-context" aria-label={`Quote in the ${label.toLowerCase()}`}>
            {found ? <>{found.before}<mark>{found.match}</mark>{found.after}</>
                : <span className="quote-missing">The original document is not available in this browser session.</span>}
        </blockquote>}
    </div>;
}

function Verification({ citations }) {
    if (!citations) return null;
    const kept = citations.checked - citations.removed;
    const claims = kept === 1 ? "claim quotes" : "claims quote";
    return <p className="verification enter" role="status"><Icon name="check"/>
        {citations.removed ? `${kept} ${claims} the documents · ${citations.removed} unsupported ${citations.removed === 1 ? "claim" : "claims"} removed`
            : `All ${kept} ${claims} the documents`}</p>;
}

export default function Assessment({ result, citations, sources }) {
    return <div className="assessment">
    {result.fitScore !== undefined && <div className="score-block enter"><div><p className="eyebrow">ROLE ALIGNMENT</p><div className="score-number">{result.fitScore}<span>/100</span></div></div>
      <svg className="score-ring" width="104" height="104" viewBox="0 0 104 104" aria-hidden="true"><circle cx="52" cy="52" r="43" fill="none" stroke="currentColor" strokeWidth="4" opacity=".12"/><circle cx="52" cy="52" r="43" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeDasharray={`${result.fitScore * 2.702} 270.2`} transform="rotate(-90 52 52)"/><path d="m36 52 10 10 22-22" fill="none" stroke="currentColor" strokeWidth="2"/></svg>
    </div>}
    {result.verdict && <p className="verdict enter">{result.verdict}</p>}
    <Verification citations={citations}/>
    {result.strengths && <section className="assessment-section enter"><h2><span className="section-symbol"><Icon name="check"/></span> What the resume supports <span className="section-count">{String(result.strengths.length).padStart(2, "0")}</span></h2>
      <ul className="strength-list">{result.strengths.map((strength, index) => <li key={index}><span aria-hidden="true"/>
        <div>{strength.text}<Quote text={strength.evidence} source={sources?.resume} label="Resume"/></div></li>)}</ul>
    </section>}
    {result.gaps?.length > 0 && <section className="assessment-section enter" style={{ animationDelay: "100ms" }}><h2><span className="section-symbol gap-symbol" aria-hidden="true">↗</span> Areas to explore <span className="section-count">{String(result.gaps.length).padStart(2, "0")}</span></h2>
      <ul className="gap-list">{result.gaps.map((gap, index) => <li key={index}><div><h3>{gap.skill}</h3><span className={`severity severity-${gap.severity}`}>{SEVERITY_LABEL[gap.severity]}</span></div><p>{gap.note}</p>
        <Quote text={gap.requirement} source={sources?.jd} label="Job description"/></li>)}</ul>
    </section>}
    {result.interviewQuestions && <section className="assessment-section enter"><h2><span className="section-symbol"><Icon name="spark"/></span> Questions worth asking <span className="section-count">{String(result.interviewQuestions.length).padStart(2, "0")}</span></h2>
      <ol className="question-list">{result.interviewQuestions.map((item, index) => <li key={index}><span className="question-number">{String(index + 1).padStart(2, "0")}</span><div><p>{item.question}</p><span className="question-meta">{item.targets} <span aria-hidden="true">·</span> {item.difficulty} level</span></div></li>)}</ol>
    </section>}
  </div>;
}
