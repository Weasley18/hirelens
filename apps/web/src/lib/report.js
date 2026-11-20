import { fetchReportPdf } from "@/lib/api";

function section(row, index) {
    const heading = `${index + 1}. ${row.document.name}`;
    if (!row.result) return [heading, row.status, row.error].filter(Boolean).join("\n");
    const { result, metadata } = row.result;
    return [
        heading,
        metadata.backend === "stub" ? "Demo mode — simulated keyword-based assessment." : "Model-generated assessment.",
        !metadata.grounded && "Reference material was unavailable. Review claims against the original documents.",
        `Role alignment: ${result.fitScore}/100`,
        result.verdict,
        "Strengths\n" + result.strengths.map(item => "• " + item).join("\n"),
        "Areas to explore\n" + (result.gaps.map(gap => `• ${gap.skill} (${gap.severity}) — ${gap.note}`).join("\n") || "No gaps reported."),
        "Interview questions\n" + result.interviewQuestions.map((item, i) => `${i + 1}. ${item.question}\n   ${item.targets} · ${item.difficulty}`).join("\n"),
    ].filter(Boolean).join("\n\n");
}

function save(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const baseName = (rows) => rows.length === 1
    ? `HireLens-${rows[0].document.name.replace(/\.pdf$/i, "").replace(/[^\p{L}\p{N} ._-]/gu, "_")}`
    : "HireLens-batch-report";

export function downloadTextReport(rows, roleName) {
    const text = ["HireLens assessment report", roleName, "For human review.", ...rows.map(section)].join("\n\n────────────────────────\n\n");
    save(new Blob([text], { type: "text/plain;charset=utf-8" }), `${baseName(rows)}.txt`);
}

/**
 * A designed PDF rendered by the API from the stored results. Falls back to the plain-text report
 * if the PDF service is unavailable (for example on a deployment without Chromium) or a result has
 * already expired on the server.
 */
export async function downloadReport(rows, roleName) {
    const finished = rows.filter(row => row.result && row.handle);
    if (finished.length) {
        try {
            const pdf = await fetchReportPdf(finished.map(row => ({ handle: row.handle, label: row.document.name })), roleName);
            save(pdf, `${baseName(rows)}.pdf`);
            return "pdf";
        } catch { /* fall through to the text report */ }
    }
    downloadTextReport(rows, roleName);
    return "text";
}
