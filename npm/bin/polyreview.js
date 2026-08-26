#!/usr/bin/env node
/**
 * PolyReview npm launcher.
 *
 * Thin wrapper: finds a Python (uv > python3 > python), installs the Python
 * package from GitHub (first run only, cached by pip/uv), then forwards all
 * args to the real `polyreview` CLI.
 *
 * Env overrides:
 *   POLYREVIEW_PY     explicit python executable
 *   POLYREVIEW_SKIP_INSTALL=1   assume backend already installed
 */

const { execFileSync, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const BACKEND = "git+https://github.com/b0o0wen/PolyReview.git";

function sh(cmd, args, opts = {}) {
  return spawnSync(cmd, args, { encoding: "utf8", ...opts });
}

function findPython() {
  if (process.env.POLYREVIEW_PY) return process.env.POLYREVIEW_PY;
  // uv 的附带 python 优先（有 pip 语义完整的 ensurepip），其次 python3/python
  const candidates = [
    ...sh("sh", ["-c", "ls ~/.local/share/uv/python/*/bin/python3 2>/dev/null || true"]).stdout
      .trim().split("\n").filter(Boolean),
    "python3", "python",
  ];
  for (const c of candidates) {
    const probe = c.endsWith("python3") && c.includes("/")
      ? sh(c, ["-c", "import ensurepip; print(1)"])
      : sh("sh", ["-c", `command -v ${c} >/dev/null && echo 1 || true`]);
    if (probe.status === 0 && probe.stdout.trim()) {
      // macOS 无 pip 的系统 python 过滤掉
      const hasPip = sh(c, ["-m", "pip", "--version"]);
      if (hasPip.status === 0) return c;
    }
  }
  return null;
}

function backendInstalled(py) {
  const r = sh(py, ["-m", "polyreview", "--version"]);
  return r.status === 0;
}

function main() {
  const py = findPython();
  if (!py) {
    console.error(`PolyReview needs Python 3.10+ (with pip). Easiest fix:
  curl -LsSf https://astral.sh/uv/install.sh | sh
then retry. Or set POLYREVIEW_PY=/path/to/python3`);
    process.exit(1);
  }

  if (!process.env.POLYREVIEW_SKIP_INSTALL && !backendInstalled(py)) {
    console.error("▸ first run: installing PolyReview backend (git+https://github.com/b0o0wen/PolyReview.git)…");
    const inst = sh(py, ["-m", "pip", "install", "--user", BACKEND]);
    if (inst.status !== 0) {
      // --user 在某些环境(如 venv/管理 python)不可用，回落普通 install
      const retry = sh(py, ["-m", "pip", "install", BACKEND]);
      if (retry.status !== 0) {
        console.error("✗ backend install failed:\n" + (inst.stderr || retry.stderr || ""));
        console.error("manual: " + py + " -m pip install " + BACKEND);
        process.exit(1);
      }
    }
    console.error("▸ backend installed.");
  }

  const r = spawnSync(py, ["-m", "polyreview", ...process.argv.slice(2)], {
    stdio: "inherit",
  });
  process.exit(r.status === null ? 1 : r.status);
}

main();
