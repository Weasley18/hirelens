/**
 * Locate a quoted excerpt in the original document so it can be highlighted in context.
 * Mirrors the ML service's matching (apps/ml-service/inference/citations.py): case, whitespace,
 * quote and dash styles, bullets, and "…" between pieces are ignored; wording is not.
 */
const FOLD = { "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "“": '"', "”": '"',
    "„": '"', "″": '"', "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    "•": " ", "·": " ", "▪": " ", "●": " ", "‣": " ", " ": " " };

/** Normalized text plus, for each normalized character, its index in the original. */
function fold(text) {
    let out = "";
    const map = [];
    for (let i = 0; i < text.length; i++) {
        let ch = (FOLD[text[i]] ?? text[i]).toLowerCase();
        if (/\s/.test(ch)) {
            if (!out.length || out.endsWith(" ")) continue;
            ch = " ";
        }
        out += ch;
        map.push(i);
    }
    return { text: out.trimEnd(), map };
}

function pieces(excerpt) {
    return fold(excerpt).text.replace(/^[\s"']+|[\s"']+$/g, "")
        .split(/\s*(?:\.\.\.+|…)\s*/)
        .map(piece => piece.replace(/^[\s"'.,;:]+|[\s"'.,;:]+$/g, ""))
        .filter(Boolean);
}

/** { start, end } in the original document, or null when the excerpt is not there. */
export function locate(excerpt, document) {
    if (!excerpt || !document) return null;
    const parts = pieces(excerpt);
    if (!parts.length || parts.join("").length < 8) return null;
    const haystack = fold(document);
    let from = 0, first = -1, last = -1;
    for (const part of parts) {
        const found = haystack.text.indexOf(part, from);
        if (found < 0) return null;
        if (first < 0) first = found;
        last = found + part.length - 1;
        from = found + part.length;
    }
    return { start: haystack.map[first], end: haystack.map[last] + 1 };
}

/** The excerpt with up to `radius` characters of surrounding text, cut at word boundaries. */
export function context(excerpt, document, radius = 140) {
    const span = locate(excerpt, document);
    if (!span) return null;
    let from = Math.max(0, span.start - radius), to = Math.min(document.length, span.end + radius);
    if (from > 0) from = document.indexOf(" ", from) + 1 || from;
    if (to < document.length) to = document.lastIndexOf(" ", to) > span.end ? document.lastIndexOf(" ", to) : to;
    return { before: (from > 0 ? "…" : "") + document.slice(from, span.start), match: document.slice(span.start, span.end),
        after: document.slice(span.end, to) + (to < document.length ? "…" : "") };
}
