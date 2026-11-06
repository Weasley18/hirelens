import { fileURLToPath } from "node:url";

const api = new URL(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3000");
if (!["http:", "https:"].includes(api.protocol) || api.username || api.password) throw new Error("Invalid API origin");
const production = process.env.NODE_ENV === "production";
if (production && api.protocol !== "https:" && !["localhost", "127.0.0.1"].includes(api.hostname)) throw new Error("Public API connections require HTTPS");
const csp = [
  "default-src 'self'", `script-src 'self' 'unsafe-inline'${production ? "" : " 'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'", `connect-src 'self' ${api.origin}`,
  "img-src 'self' data:", "object-src 'none'", "base-uri 'self'", "frame-ancestors 'none'", "form-action 'self'",
].join("; ");
/** @type {import('next').NextConfig} */
export default {
  transpilePackages: ["@hirelens/shared"],
  outputFileTracingRoot: fileURLToPath(new URL("../../", import.meta.url)),
  poweredByHeader: false,
  async headers() { return [{ source: "/:path*", headers: [
    { key: "Content-Security-Policy", value: csp },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "no-referrer" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  ] }]; },
};
