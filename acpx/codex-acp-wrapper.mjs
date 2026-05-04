#!/usr/bin/env node
import { existsSync } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const codexHome = fileURLToPath(new URL("./codex-home/", import.meta.url));
const env = {
  ...process.env,
  CODEX_HOME: codexHome,
};
const configuredArgs = process.argv.slice(2);

function resolveNpmCliPath() {
  const candidate = path.resolve(
    path.dirname(process.execPath),
    "..",
    "lib",
    "node_modules",
    "npm",
    "bin",
    "npm-cli.js",
  );
  return existsSync(candidate) ? candidate : undefined;
}

const npmCliPath = resolveNpmCliPath();
const installedBinPath = "/Users/bishop/.openclaw/plugin-runtime-deps/openclaw-2026.4.27-da6bdffc3d96/node_modules/@zed-industries/codex-acp/bin/codex-acp.js";
let defaultCommand;
let defaultArgs;
if (installedBinPath) {
  defaultCommand = process.execPath;
  defaultArgs = [installedBinPath];
} else if (npmCliPath) {
  defaultCommand = process.execPath;
  defaultArgs = [npmCliPath, "exec", "--yes", "--package", "@zed-industries/codex-acp@^0.12.0", "--", "codex-acp"];
} else {
  defaultCommand = process.platform === "win32" ? "npx.cmd" : "npx";
  defaultArgs = ["--yes", "--package", "@zed-industries/codex-acp@^0.12.0", "--", "codex-acp"];
}
const command =
  configuredArgs[0] === "--openclaw-run-configured" ? configuredArgs[1] : defaultCommand;
const args =
  configuredArgs[0] === "--openclaw-run-configured"
    ? configuredArgs.slice(2)
    : [...defaultArgs, ...configuredArgs];

if (!command) {
  console.error("[openclaw] missing configured Codex ACP command");
  process.exit(1);
}

const child = spawn(command, args, {
  env,
  stdio: "inherit",
  windowsHide: true,
});

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.once(signal, () => {
    child.kill(signal);
  });
}

child.on("error", (error) => {
  console.error(`[openclaw] failed to launch Codex ACP wrapper: ${error.message}`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (code !== null) {
    process.exit(code);
  }
  process.exit(signal ? 1 : 0);
});
