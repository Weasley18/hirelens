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

export function downloadReport(rows, roleName) {
    const text = ["HireLens assessment report", roleName, "For human review.", ...rows.map(section)].join("\n\n────────────────────────\n\n");
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = rows.length === 1 ? `HireLens-${rows[0].document.name.replace(/\.pdf$/i, "").replace(/[^\p{L}\p{N} ._-]/gu, "_")}.txt` : "HireLens-batch-report.txt";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
