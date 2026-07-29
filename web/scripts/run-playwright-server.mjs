import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const webDirectory = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const serverScript = path.resolve(webDirectory, "../tests/run_ui7_playwright_server.py");
const configuredPython = process.env.PYTHON?.trim();
const localPython = path.resolve(
  webDirectory,
  process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python",
);
const candidates = configuredPython
  ? [[configuredPython]]
  : [
      ...(existsSync(localPython) ? [[localPython]] : []),
      ...(process.platform === "win32"
        ? [["py", "-3"], ["python"], ["python3"]]
        : [["python3"], ["python"]]),
    ];

function start(index) {
  if (index >= candidates.length) {
    console.error("Python 3 was not found. Set PYTHON or install python3/python.");
    process.exit(1);
  }
  const [command, ...prefixArgs] = candidates[index];
  const child = spawn(command, [...prefixArgs, serverScript], {
    cwd: path.resolve(webDirectory, ".."),
    env: {
      ...process.env,
      PYTHONPATH: [path.resolve(webDirectory, "../src"), process.env.PYTHONPATH]
        .filter(Boolean)
        .join(path.delimiter),
    },
    stdio: "inherit",
  });
  child.once("error", (error) => {
    if (error.code === "ENOENT") start(index + 1);
    else {
      console.error(`Could not start ${command}: ${error.message}`);
      process.exit(1);
    }
  });
  child.once("exit", (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    else process.exit(code ?? 1);
  });
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.once(signal, () => child.kill(signal));
  }
}

start(0);
