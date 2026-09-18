// code2course/trace_node.mjs - v1.19.0 E4: node collector producing trace-facts-v2.
// Merged port of the v19-exp pair (cov_run.mjs orchestration + v8_lines.mjs conversion):
// spawns the target under NODE_V8_COVERAGE with fd-based stdio, optionally polls
// --port/--url until 200 (or --timeout), finishes it via the grace/kill ladder, then walks
// the coverage JSON files and maps V8 ranges (UTF-16 offsets, innermost-range semantics)
// to hit lines. V8 has no call events, so "edges" is honestly always [].
// Usage: node trace_node.mjs <repoRoot> <script> --covdir DIR [--port N | --url U]
//        [--timeout ms] [--grace-ms ms] [--out FILE] [-- target args...]
// stdout: empty when --out is given, else the JSON line; diagnostics go to stderr.
// Exit: target's code, or 2 usage error, or 1 when the coverage dir is missing/empty/corrupt.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const SCHEMA = 'trace-facts-v2';

function warn(msg) {
  process.stderr.write('[trace_node] ' + msg + '\n');
}

function usage(exitCode) {
  process.stderr.write(
    'usage: node trace_node.mjs <repoRoot> <script> --covdir DIR [--port N | --url U]' +
    ' [--timeout ms] [--grace-ms ms] [--out FILE] [-- target args...]\n' +
    '  <script> is relative to <repoRoot> (absolute paths also accepted); the child runs' +
    ' with cwd=<repoRoot>.\n' +
    '  exit: child code, 2 usage error, 1 bad coverage dir (missing/empty/corrupt).\n'
  );
  process.exit(exitCode);
}

function parseArgs(argv) {
  const opts = {
    repoRoot: null, script: null, covdir: null, url: null, port: null,
    timeout: 20000, graceMs: 2500, out: null, help: false, targetArgs: [],
  };
  const pos = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--') { opts.targetArgs = argv.slice(i + 1); break; }
    else if (a === '-h' || a === '--help') opts.help = true;
    else if (a === '--covdir') { if (i + 1 >= argv.length) usage(2); opts.covdir = argv[++i]; }
    else if (a === '--url') { if (i + 1 >= argv.length) usage(2); opts.url = argv[++i]; }
    else if (a === '--port') { if (i + 1 >= argv.length) usage(2); opts.port = Number(argv[++i]); }
    else if (a === '--timeout') { if (i + 1 >= argv.length) usage(2); opts.timeout = Number(argv[++i]); }
    else if (a === '--grace-ms') { if (i + 1 >= argv.length) usage(2); opts.graceMs = Number(argv[++i]); }
    else if (a === '--out') { if (i + 1 >= argv.length) usage(2); opts.out = argv[++i]; }
    else pos.push(a);
  }
  if (opts.help) usage(0);
  opts.repoRoot = pos[0] || null;
  opts.script = pos[1] || null;
  if (!opts.repoRoot || !opts.script) usage(2);
  if (!opts.covdir) { warn('error: --covdir is required'); usage(2); }
  if (opts.port !== null && (!Number.isInteger(opts.port) || opts.port <= 0)) {
    warn('error: --port must be a positive integer');
    usage(2);
  }
  if (!opts.url && opts.port !== null) opts.url = 'http://127.0.0.1:' + opts.port + '/';
  return opts;
}

function probeOnce(url) {
  return new Promise((resolve) => {
    let req;
    try {
      req = http.get(url, { timeout: 1000 }, (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      });
    } catch (e) {
      resolve(false);
      return;
    }
    req.on('timeout', () => { req.destroy(); resolve(false); });
    req.on('error', () => resolve(false));
  });
}

async function pollUntilOk(url, timeoutMs) {
  const t0 = Date.now();
  let n = 0;
  for (;;) {
    if (await probeOnce(url)) return Date.now() - t0;
    if (Date.now() - t0 >= timeoutMs) return -1;
    await sleep(n < 5 ? 50 : 150);
    n += 1;
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function spawnChild(covdirAbs, repoRootAbs, scriptAbs, targetArgs) {
  fs.mkdirSync(covdirAbs, { recursive: true });
  const logPath = path.join(covdirAbs, 'child-output.log');
  const fd = fs.openSync(logPath, 'a'); // fd stdio: the sandbox forbids 'pipe' capture
  const env = Object.assign({}, process.env, { NODE_V8_COVERAGE: covdirAbs });
  const child = spawn(process.execPath, [scriptAbs].concat(targetArgs), {
    cwd: repoRootAbs,
    env,
    stdio: ['ignore', fd, fd],
    detached: process.platform === 'win32', // own process group so SIGBREAK can target it
    windowsHide: true,
  });
  return { child, fd, logPath };
}

async function finishChild(child, graceMs) {
  const exited = new Promise((resolve) => child.once('exit', (c) => resolve({ code: c })));
  if (child.exitCode !== null) {
    warn('child already exited (code=' + child.exitCode + ')');
    return child.exitCode;
  }
  // Grace window: a self-exiting target flushes V8 coverage on its own exit; killing it
  // early would lose the report (Windows: signal death skips exit hooks). Only a target
  // that outlives the grace window gets the kill ladder.
  let done = await Promise.race([exited, sleep(graceMs).then(() => null)]);
  if (!done) {
    warn('child alive after ' + graceMs + ' ms grace; sending finish signals');
    // NOTE: child.kill() stamps signalCode optimistically, so "still alive" must be
    // judged by the exit event only, never by signalCode.
    if (process.platform === 'win32') {
      try { child.kill('SIGBREAK'); } catch (e) { warn('SIGBREAK failed: ' + e.message); }
    } else {
      try { child.kill('SIGTERM'); } catch (e) { warn('SIGTERM failed: ' + e.message); }
    }
    done = await Promise.race([exited, sleep(2000).then(() => null)]);
    if (!done) {
      warn('graceful signal did not finish child; hard kill');
      try { child.kill(); } catch (e) { warn('kill failed: ' + e.message); }
      done = await Promise.race([exited, sleep(10000).then(() => null)]);
    }
  }
  if (!done) {
    warn('child still alive 10s after kill (continuing, not crashing)');
    return null;
  }
  return done.code;
}

function listCoverageFiles(dir) {
  const found = [];
  const stack = [dir];
  while (stack.length) {
    const cur = stack.pop();
    let names;
    try {
      names = fs.readdirSync(cur, { withFileTypes: true });
    } catch (e) {
      continue;
    }
    for (const ent of names) {
      const p = path.join(cur, ent.name);
      if (ent.isDirectory()) stack.push(p);
      else if (ent.isFile() && ent.name.endsWith('.json')) found.push(p);
    }
  }
  return found;
}

// Classification contract: keep only file:// URLs that realpath inside the repo and are
// not under any node_modules segment; drop builtins (node:), other schemes, and missing
// files. Reasons are tallied for one aggregate stderr line (real repos skip 150+ builtins).
function classifyScriptUrl(url, rootReal) {
  if (typeof url !== 'string' || !url.startsWith('file:')) return { skip: 'non-file' };
  let p;
  try {
    p = fileURLToPath(url);
  } catch (e) {
    return { skip: 'non-file' };
  }
  let real;
  try {
    real = fs.realpathSync(p);
  } catch (e) {
    return { skip: 'missing' };
  }
  const rel = path.relative(rootReal, real);
  if (!rel || rel === '..' || rel.startsWith('..' + path.sep) || path.isAbsolute(rel)) {
    return { skip: 'outside' };
  }
  const parts = rel.split(/[\\/]+/);
  if (parts.includes('node_modules')) return { skip: 'node_modules' };
  return { rel: rel.replace(/\\/g, '/') };
}

// V8 range offsets are UTF-16 code units (never Buffer.byteLength: CJK sources shift
// everything). Node strips a leading BOM before V8 sees the source, so we do too.
function buildLineStarts(src) {
  if (src.charCodeAt(0) === 0xfeff) src = src.slice(1);
  const starts = [0];
  for (let i = 0; i < src.length; i++) {
    if (src.charCodeAt(i) === 10) starts.push(i + 1);
  }
  return { src, starts };
}

// Innermost-range line semantics (c8 style, tt-cov-summarize lessons): ranges nest;
// parents sort before children by (start asc, end desc); a sweeping stack keeps the
// innermost active range whose count decides each line. Merging across processes happens
// by unioning per-file line sets later (never by pooling raw ranges).
function hitLinesForEntry(entry, absPath) {
  const { src, starts } = buildLineStarts(fs.readFileSync(absPath, 'utf8'));
  const ranges = [];
  for (const fn of entry.functions || []) {
    for (const r of fn.ranges || []) {
      if (r.endOffset > r.startOffset) {
        ranges.push({ start: r.startOffset, end: r.endOffset, count: r.count });
      }
    }
  }
  ranges.sort((a, b) => (a.start - b.start) || (b.end - a.end));
  const hits = new Set();
  const stack = [];
  let next = 0;
  for (let ln = 0; ln < starts.length; ln++) {
    const off = starts[ln];
    if (off >= src.length && ln === starts.length - 1) break; // phantom line after trailing \n
    while (next < ranges.length && ranges[next].start <= off) stack.push(ranges[next++]);
    while (stack.length && stack[stack.length - 1].end <= off) stack.pop();
    if (stack.length && stack[stack.length - 1].count > 0) hits.add(ln + 1);
  }
  return hits;
}

async function run(opts) {
  const t0 = Date.now();
  const covdirAbs = path.resolve(opts.covdir);
  const repoRootAbs = path.resolve(opts.repoRoot);
  if (!fs.statSync(repoRootAbs, { throwIfNoEntry: false })?.isDirectory()) {
    warn('error: repoRoot is not a directory: ' + opts.repoRoot);
    usage(2);
  }
  const scriptAbs = path.resolve(repoRootAbs, opts.script); // relative to repoRoot; absolute resolves to itself
  if (!fs.statSync(scriptAbs, { throwIfNoEntry: false })?.isFile()) {
    warn('error: script not found: ' + opts.script);
    usage(2);
  }
  const { child, fd, logPath } = spawnChild(covdirAbs, repoRootAbs, scriptAbs, opts.targetArgs);
  warn('spawned pid=' + child.pid + ' node ' + opts.script +
    ' (cwd=' + repoRootAbs + ' covdir=' + covdirAbs + ' log=' + logPath + ')');

  if (opts.url) {
    const ms = await pollUntilOk(opts.url, opts.timeout);
    if (ms < 0) warn('probe ' + opts.url + ' did not reach 200 within ' + opts.timeout + ' ms');
    else warn('probe ' + opts.url + ' reached 200 in ' + ms + ' ms');
  }

  const childCode = await finishChild(child, opts.graceMs);
  try { fs.closeSync(fd); } catch (e) { /* already closed */ }

  // ---- conversion stage (v8_lines port) ----
  if (!fs.statSync(covdirAbs, { throwIfNoEntry: false })?.isDirectory()) {
    warn('error: coverage dir vanished: ' + covdirAbs);
    return 1;
  }
  const covFiles = listCoverageFiles(covdirAbs);
  if (covFiles.length === 0) {
    warn('error: coverage dir contains no JSON reports: ' + covdirAbs +
      ' (a killed child on Windows skips the V8 flush; prefer a self-exiting target)');
    return 1;
  }
  const rootReal = fs.realpathSync(repoRootAbs);
  const byFile = new Map();
  const skipTally = {};
  for (const f of covFiles) {
    let report;
    try {
      report = JSON.parse(fs.readFileSync(f, 'utf8'));
    } catch (e) {
      warn('error: corrupt coverage JSON ' + f + ': ' + e.message);
      return 1;
    }
    for (const entry of report.result || []) {
      const cls = classifyScriptUrl(entry.url, rootReal);
      if (cls.skip !== undefined) {
        skipTally[cls.skip] = (skipTally[cls.skip] || 0) + 1;
        continue;
      }
      const abs = path.join(rootReal, ...cls.rel.split('/'));
      for (const l of hitLinesForEntry(entry, abs)) {
        let set = byFile.get(cls.rel);
        if (!set) byFile.set(cls.rel, (set = new Set()));
        set.add(l);
      }
    }
  }
  const skipParts = Object.keys(skipTally).sort().map((k) => k + '=' + skipTally[k]);
  if (skipParts.length) warn('skipped scripts by reason: ' + skipParts.join(' '));

  const filesSorted = {};
  for (const rel of [...byFile.keys()].sort()) {
    const lines = [...byFile.get(rel)].sort((a, b) => a - b);
    if (lines.length) filesSorted[rel] = lines;
  }
  if (Object.keys(filesSorted).length === 0) {
    warn('warning: 0 in-repo files matched under ' + repoRootAbs + ' -- check repoRoot');
  }
  // V8 has no call events: edges stays honestly empty (SPEC 2.4 node arm).
  const doc = {
    command: 'node trace_node.mjs ' + process.argv.slice(2).join(' '),
    duration_s: Math.round(Date.now() - t0) / 1000,
    edges: [],
    files: filesSorted,
    repo: path.basename(repoRootAbs),
    runtime: 'node',
    schema: SCHEMA,
  };
  const text = JSON.stringify(doc) + '\n';
  if (opts.out) {
    const outAbs = path.resolve(opts.out);
    fs.mkdirSync(path.dirname(outAbs), { recursive: true });
    fs.writeFileSync(outAbs, text);
    warn('wrote ' + outAbs + ' (files=' + Object.keys(filesSorted).length + ' edges=0)');
  } else {
    process.stdout.write(text);
  }
  warn('child exit code=' + String(childCode));
  return childCode === null || childCode === undefined ? 0 : childCode;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  return run(opts);
}

main().then(
  (code) => process.exit(code),
  (err) => {
    warn('fatal: ' + ((err && err.stack) || err));
    process.exit(1);
  }
);
