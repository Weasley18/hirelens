import { useRef, useState } from "react";
import Icon from "./Icon";

export default function DocumentField({ kind, label, multiple, min, max, value, onChange, locked }) {
    const [error, setError] = useState("");
    const input = useRef(null);
    const pdf = value.mode === "pdf";
    function select(files) {
        const incoming = Array.from(files);
        if (!incoming.length) return;
        if (incoming.some(file => !/\.pdf$/i.test(file.name) || file.size > 10 * 1024 * 1024 || !file.size)) {
            setError("Choose nonempty PDF files up to 10 MB each.");
            return;
        }
        setError("");
        onChange({ ...value, files: multiple ? [...value.files, ...incoming] : [incoming[0]] });
    }
    return <section className="document-card" aria-labelledby={kind + "-title"}>
        <div className="card-head"><span className="document-icon"><Icon name={multiple ? "file" : "briefcase"}/></span>
            <h2 id={kind + "-title"}>{label}</h2>
            <div className="mode-switch" aria-label={label + " input method"}>
                {["pdf", "text"].map(mode => <button key={mode} type="button" aria-pressed={value.mode === mode}
                    disabled={locked} onClick={() => { setError(""); onChange({ ...value, mode }); }}>
                    {mode === "pdf" ? "PDF" : "Text"}</button>)}
            </div>
        </div>
        {pdf ? <>
            <input ref={input} type="file" accept=".pdf,application/pdf" multiple={multiple} hidden
                aria-label={multiple ? "Upload resume PDFs" : "Upload job description PDF"}
                disabled={locked} onChange={e => { select(e.target.files); e.target.value = ""; }}/>
            <button type="button" className="file-picker" disabled={locked} onClick={() => input.current.click()}
                onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!locked && (multiple || e.dataTransfer.files.length === 1)) select(e.dataTransfer.files);
                    else if (!locked) setError("Choose a single job description PDF."); }}>
                <Icon name="upload"/><strong>{multiple ? (value.files.length ? "Add more resumes" : "Choose resume PDFs") : (value.files.length ? "Replace job description" : "Choose job description PDF")}</strong>
                <span>{multiple ? "One or more text PDFs" : "One text PDF"} · up to 10 MB each</span>
            </button>
            {value.files.length > 0 && <ul className="selected-files" aria-label={label + " files"}>{value.files.map((file, index) =>
                <li key={index}><Icon name="file"/><span title={file.name}>{file.name}</span><button type="button" disabled={locked}
                    aria-label={`Remove ${file.name}`} onClick={() => onChange({ ...value, files: value.files.filter((_, i) => i !== index) })}><Icon name="close"/></button></li>)}</ul>}
        </> : <>
            <textarea id={kind} aria-label={multiple ? "Resume" : "Job description"} disabled={locked} value={value.text} maxLength={max}
                placeholder={multiple ? "Paste the candidate’s resume here…" : "Paste the role’s requirements here…"}
                onChange={e => onChange({ ...value, text: e.target.value })}/>
            <p className="field-help"><span>At least {min} characters</span><span>{value.text.trim().length.toLocaleString()} / {max.toLocaleString()}</span></p>
        </>}
        {error && <p className="input-error" role="alert">{error}</p>}
    </section>;
}
