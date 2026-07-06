#!/usr/bin/env node
/**
 * S6 grader — Frontend: fetch + render a status component from a mocked API
 * (Tier 2-3, work_class=frontend). Deterministic, no LLM-judge:
 *   (a) BUILD: `npm run build` (whatever package.json's build script is)
 *   (b) RENDER: load the built bundle in jsdom, stub fetch, assert the
 *       data-testid contract against the baseline fixture.
 *   (c) REAL-DATA PROOF: rerun against a MUTATED fixture, assert DOM changes.
 *       A component that still renders the original data is hardcoded/static
 *       -> feature-inert, fails hard (S2's frontend twin).
 *   (d) SCOPE: only src/**, index.html, dist/** (generated) may differ from
 *       the baseline fixture-fe repo.
 *
 * Usage: node s6.js --worktree <dir> --baseline fixtures-fe
 * Emits one JSON line: {score, verdict, gate, reason}
 */
const fs = require("fs");
const path = require("path");
const { execFileSync, spawnSync } = require("child_process");
const { JSDOM } = require(path.join(__dirname, "..", "node_modules", "jsdom"));

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--worktree") out.worktree = argv[++i];
    if (argv[i] === "--baseline") out.baseline = argv[++i];
  }
  if (!out.worktree || !out.baseline) {
    console.log(JSON.stringify({ score: 0, verdict: "BLOCK", gate: "fail", reason: "usage: --worktree <dir> --baseline <dir>" }));
    process.exit(2);
  }
  return out;
}

function verdictFromScore(score) {
  if (score >= 90) return "MERGE";
  if (score >= 50) return "FIXES";
  return "BLOCK";
}

function emit(score, gate, reason) {
  score = Math.max(0, Math.min(100, Math.round(score)));
  console.log(JSON.stringify({ score, verdict: verdictFromScore(score), gate, reason }));
  return score;
}

function walkFiles(root) {
  const out = new Set();
  const IGNORE = new Set(["node_modules", ".git", "dist"]);
  (function rec(dir) {
    for (const name of fs.readdirSync(dir)) {
      if (IGNORE.has(name)) continue;
      const p = path.join(dir, name);
      const rel = path.relative(root, p);
      if (fs.statSync(p).isDirectory()) rec(p);
      else out.add(rel);
    }
  })(root);
  return out;
}

function changedFiles(baseline, worktree) {
  const b = walkFiles(baseline);
  const w = walkFiles(worktree);
  const changed = [];
  for (const rel of new Set([...b, ...w])) {
    const bp = path.join(baseline, rel);
    const wp = path.join(worktree, rel);
    const inB = b.has(rel), inW = w.has(rel);
    if (!inB || !inW) { changed.push(rel); continue; }
    if (!fs.readFileSync(bp).equals(fs.readFileSync(wp))) changed.push(rel);
  }
  return changed.sort();
}

function scopeOk(changed) {
  const forbiddenExact = new Set([
    "fixtures/status.json",
    "fixtures/status.mutated.json",
    "vite.config.js",
    "package.json",
    "package-lock.json",
  ]);
  const allowedPrefixes = ["src/", "dist/"];
  const allowedExact = new Set(["index.html"]);
  const violations = [];
  for (const rel of changed) {
    if (forbiddenExact.has(rel)) { violations.push(rel); continue; }
    if (allowedExact.has(rel)) continue;
    if (allowedPrefixes.some((p) => rel.startsWith(p))) continue;
    violations.push(rel);
  }
  return { ok: violations.length === 0, violations };
}

function runBuild(worktree) {
  if (!fs.existsSync(path.join(worktree, "node_modules"))) {
    const install = spawnSync("npm", ["install", "--no-audit", "--no-fund"], {
      cwd: worktree, timeout: 180000, encoding: "utf8",
    });
    if (install.status !== 0) {
      return { ok: false, reason: "npm install failed: " + (install.stderr || "").slice(-500) };
    }
  }
  let pkg;
  try {
    pkg = JSON.parse(fs.readFileSync(path.join(worktree, "package.json"), "utf8"));
  } catch (e) {
    return { ok: false, reason: "package.json unreadable/invalid: " + e.message };
  }
  if (!pkg.scripts || !pkg.scripts.build) {
    return { ok: false, reason: "package.json has no scripts.build" };
  }
  const build = spawnSync("npm", ["run", "build"], { cwd: worktree, timeout: 120000, encoding: "utf8" });
  if (build.status !== 0) {
    return { ok: false, reason: "npm run build failed: " + (build.stderr || build.stdout || "").slice(-500) };
  }
  // Don't hardcode a bundler: prefer dist/bundle.js, else the newest *.js under dist/.
  const distDir = path.join(worktree, "dist");
  if (!fs.existsSync(distDir)) return { ok: false, reason: "build exited 0 but no dist/ output directory" };
  const preferred = path.join(distDir, "bundle.js");
  if (fs.existsSync(preferred)) return { ok: true, bundle: preferred };
  const jsFiles = [];
  (function rec(dir) {
    for (const name of fs.readdirSync(dir)) {
      const p = path.join(dir, name);
      if (fs.statSync(p).isDirectory()) rec(p);
      else if (name.endsWith(".js")) jsFiles.push(p);
    }
  })(distDir);
  if (jsFiles.length === 0) return { ok: false, reason: "build produced dist/ but no .js output" };
  jsFiles.sort((a, b) => fs.statSync(b).size - fs.statSync(a).size);
  return { ok: true, bundle: jsFiles[0] };
}

async function renderWithFixture(bundlePath, fixtureData) {
  const bundleCode = fs.readFileSync(bundlePath, "utf8");
  // The bundle script is included INLINE in the initial HTML (not appended
  // after construction) so jsdom executes it synchronously during parsing,
  // BEFORE `DOMContentLoaded` fires (fired from `documentImpl.close()`,
  // which runs after parsing). A legit solution that gates its render on
  // `document.addEventListener("DOMContentLoaded", ...)` registers that
  // listener during the synchronous script execution and DOES get called -
  // previously the script was appended after construction returned, by
  // which point DOMContentLoaded had already fired, so such a solution
  // rendered 0 rows and was mis-scored as broken (40). `beforeParse` runs
  // before parsing starts, so the fetch stub is in place before the inline
  // script (which may call fetch synchronously on load) executes.
  const html = `<!doctype html><body><div id="app"></div><script>${bundleCode}</script></body>`;
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    resources: "usable",
    url: "http://localhost/",
    beforeParse(window) {
      window.fetch = async () => ({ ok: true, status: 200, json: async () => fixtureData });
    },
  });

  const deadline = Date.now() + 4000;
  let rows = [];
  while (Date.now() < deadline) {
    rows = Array.from(dom.window.document.querySelectorAll('[data-testid="provider-row"]'));
    if (rows.length > 0) break;
    await new Promise((r) => setTimeout(r, 50));
  }
  // settle one more tick so all rows (not just the first) are painted
  await new Promise((r) => setTimeout(r, 100));
  rows = Array.from(dom.window.document.querySelectorAll('[data-testid="provider-row"]'));

  const rendered = rows.map((r) => ({
    name: r.querySelector('[data-testid="name"]')?.textContent ?? null,
    cost_class: r.querySelector('[data-testid="cost_class"]')?.textContent ?? null,
    status: r.querySelector('[data-testid="status"]')?.textContent ?? null,
  }));
  dom.window.close();
  return rendered;
}

function sameShape(rendered, fixture) {
  if (rendered.length !== fixture.length) return false;
  for (let i = 0; i < fixture.length; i++) {
    const r = rendered[i], f = fixture[i];
    if (!r) return false;
    if (r.name !== f.name || r.cost_class !== f.cost_class || r.status !== f.status) return false;
  }
  return true;
}

async function main() {
  const { worktree, baseline } = parseArgs(process.argv.slice(2));

  const changed = changedFiles(baseline, worktree);
  const { ok: scopeIsOk, violations } = scopeOk(changed);

  const build = runBuild(worktree);
  if (!build.ok) {
    emit(0, "fail", "BUILD failed: " + build.reason);
    return;
  }

  const fixture = JSON.parse(fs.readFileSync(path.join(baseline, "fixtures/status.json"), "utf8"));
  const mutated = JSON.parse(fs.readFileSync(path.join(baseline, "fixtures/status.mutated.json"), "utf8"));

  let renderedOriginal, renderedMutated;
  try {
    renderedOriginal = await renderWithFixture(build.bundle, fixture);
    renderedMutated = await renderWithFixture(build.bundle, mutated);
  } catch (e) {
    emit(40, "fail", "RENDER crashed while executing the bundle in jsdom: " + e.message);
    return;
  }

  const renderOk = sameShape(renderedOriginal, fixture);
  const realDataOk = renderOk && !sameShape(renderedMutated, fixture) && sameShape(renderedMutated, mutated);

  const reasonBits = [
    `scope_ok=${scopeIsOk}${violations.length ? " violations=" + JSON.stringify(violations) : ""}`,
    `render_ok=${renderOk} rendered=${JSON.stringify(renderedOriginal)}`,
    `real_data_proof=${realDataOk} rendered_after_mutation=${JSON.stringify(renderedMutated)}`,
  ];
  const reason = reasonBits.join("; ");

  let score;
  if (!renderOk) {
    score = 40;
  } else if (!realDataOk) {
    // builds+renders correctly once, but static/hardcoded - fails the
    // anti-dodge gate. This is the frontend twin of S2's #6 signature: the
    // feature LOOKS done (renders once) but is fake. A dodge that fakes
    // doneness must score BELOW the "honest, real, but partial" bands - not
    // above them - so this lands in BLOCK (<50), tied with (not above) the
    // renderOk-fails case, never FIXES/MERGE.
    score = 40;
  } else {
    score = 100;
  }

  if (!scopeIsOk) {
    score = Math.min(score, 25);
  }

  const gate = build.ok && renderOk ? "pass" : "fail";
  emit(score, gate, reason);
}

main().catch((e) => {
  emit(0, "fail", "grader crashed: " + (e && e.stack || e));
});
