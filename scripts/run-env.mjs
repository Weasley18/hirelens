// Explicit root .env loading for local commands. Deployment environment values win.
import { config } from "dotenv";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
const root = fileURLToPath(new URL("../", import.meta.url));
config({ path: resolve(root, ".env"), quiet: true });
const [service, ...args] = process.argv.slice(2);
const commands = {
  ml: [resolve(root, "apps/ml-service/.venv/bin/python"), resolve(root, "apps/ml-service")],
  prisma: [resolve(root, "node_modules/.bin/prisma"), resolve(root, "apps/api")],
};
if (!(service in commands)) throw new Error("Expected ml or prisma");
const [command, cwd] = commands[service];
const child = spawn(command, args, { cwd, env: process.env, stdio: "inherit" });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
child.on("error", () => { console.error("Command unavailable. Follow README setup."); process.exitCode = 1; });
child.on("exit", code => { process.exitCode = code ?? 1; });
