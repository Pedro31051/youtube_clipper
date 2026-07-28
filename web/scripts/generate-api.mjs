import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const webDirectory = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const exporter = path.resolve(webDirectory, "../scripts/export_openapi.py");
const output = path.resolve(webDirectory, "openapi.json");

const configuredPython = process.env.PYTHON?.trim();
const localPython = path.resolve(
  webDirectory,
  process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python",
);
const defaultCandidates = [
  ...(existsSync(localPython) ? [[localPython]] : []),
  ...(process.platform === "win32"
    ? [["py", "-3"], ["python"], ["python3"]]
    : [["python3"], ["python"]]),
];
const candidates = configuredPython
  ? [[configuredPython]]
  : defaultCandidates;

for (const [command, ...prefixArgs] of candidates) {
  const result = spawnSync(
    command,
    [...prefixArgs, exporter, "--output", output],
    {
      cwd: webDirectory,
      env: {
        ...process.env,
        PYTHONPATH: [path.resolve(webDirectory, "../src"), process.env.PYTHONPATH]
          .filter(Boolean)
          .join(path.delimiter),
      },
      stdio: "inherit",
    },
  );

  if (result.error?.code === "ENOENT") {
    continue;
  }
  if (result.error) {
    console.error(`Could not start ${command}: ${result.error.message}`);
    process.exit(1);
  }
  process.exit(result.status ?? 1);
}

console.error(
  "Python 3 was not found. Set the PYTHON environment variable or install python3/python.",
);
process.exit(1);
