import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const repoRoot = fileURLToPath(new URL("../../", import.meta.url));

export default defineConfig(({ mode, command, isPreview }) => {
  // Only public prefixes are read here. Private server credentials are never defined in client code.
  const env = loadEnv(mode, repoRoot, ["VITE_", "NEXT_PUBLIC_"]);
  const api = new URL(process.env.VITE_API_URL ?? env.VITE_API_URL
    ?? process.env.NEXT_PUBLIC_API_URL ?? env.NEXT_PUBLIC_API_URL ?? "http://localhost:3000");
  if (!["http:", "https:"].includes(api.protocol) || api.username || api.password
    || api.pathname !== "/" || api.search || api.hash) throw new Error("VITE_API_URL must be an HTTP(S) origin without credentials or a path");
  // Who generates the assessment. Set to the provider's name (e.g. "Anthropic") when the ML service
  // uses MODEL_BACKEND=hosted, so the privacy notice tells users documents are sent there.
  const provider = (process.env.VITE_INFERENCE_PROVIDER ?? env.VITE_INFERENCE_PROVIDER ?? "").trim();
  if (!/^[A-Za-z0-9 .&-]{0,40}$/.test(provider)) throw new Error("VITE_INFERENCE_PROVIDER must be a short plain-text name");
  const production = command === "build" || isPreview;
  if (production && api.protocol !== "https:" && !["localhost", "127.0.0.1"].includes(api.hostname)) {
    throw new Error("Public API connections require HTTPS");
  }
  const directives = [
    "default-src 'self'",
    `script-src 'self'${production ? "" : " 'unsafe-inline'"}`,
    "style-src 'self' 'unsafe-inline'",
    `connect-src 'self' ${api.origin}${production ? "" : " ws://localhost:3001 ws://127.0.0.1:3001"}`,
    "img-src 'self' data:", "object-src 'none'", "base-uri 'self'", "form-action 'self'",
  ];
  const headers = {
    "Content-Security-Policy": [...directives, "frame-ancestors 'none'"].join("; "),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  };
  return {
    envDir: repoRoot,
    // Keep the old variable as a migration fallback, but expose only the validated origin.
    define: { "import.meta.env.VITE_API_URL": JSON.stringify(api.origin),
      "import.meta.env.VITE_INFERENCE_PROVIDER": JSON.stringify(provider) },
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) }, dedupe: ["react", "react-dom"] },
    plugins: [react(), {
      name: "hirelens-security-headers",
      transformIndexHtml() {
        // CSP in HTML also protects deployments whose static host doesn't support _headers.
        // frame-ancestors requires an HTTP header and is therefore excluded from this meta tag.
        return [{ tag: "meta", attrs: { "http-equiv": "Content-Security-Policy", content: directives.join("; ") }, injectTo: "head-prepend" }];
      },
      generateBundle() {
        this.emitFile({ type: "asset", fileName: "_headers",
          source: "/*\n" + Object.entries(headers).map(([name, value]) => `  ${name}: ${value}`).join("\n") + "\n" });
      },
    }],
    server: { host: "127.0.0.1", port: 3001, strictPort: true, headers },
    preview: { host: "127.0.0.1", port: 3001, strictPort: true, headers },
    build: { outDir: "dist", target: "es2022", sourcemap: false },
  };
});
