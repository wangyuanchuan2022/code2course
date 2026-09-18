# code2course/tests/test_trace_collect.py - v1.19.0 E4 selftest for the trace collectors.
# Covers trace_collect.py (python arm: line+call events, edges) and trace_node.mjs (node
# arm: coverage conversion, edges==[]) on synthetic tmp repos plus the real click/express
# corpora (honest skip when absent). Includes injected-fail negative cases (bad repo-root,
# bad/empty/corrupt coverage). Final line: "test_trace_collect: N passed / F failed /
# K skipped"; exit 1 when F > 0. ASCII output only.
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)                      # code2course/
WS = os.path.dirname(SKILL)                        # workspace root
V119 = os.path.join(WS, "agent-out", "v119")
TMP = os.path.join(V119, ".tmp-selftest")
SMOKE = os.path.join(V119, "e4-smoke")
PY_COLLECTOR = os.path.join(SKILL, "trace_collect.py")
NODE_COLLECTOR = os.path.join(SKILL, "trace_node.mjs")
PY = sys.executable
NODE = os.environ.get("E4_NODE", "node")
CLICK_ROOT = os.path.join(SKILL, "tests", "corpus", "python", "click-6.7")
EXPRESS_ROOT = os.path.join(SKILL, "tests", "corpus", "javascript", "express-4.0.0")

SCHEMA_KEYS = {"schema", "repo", "runtime", "command", "duration_s", "files", "edges"}

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


class SkipCase(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def run(cmd, timeout=180):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, cwd=SKILL)
    return p.returncode, p.stdout, p.stderr


def fresh_dirs():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP)
    os.makedirs(SMOKE, exist_ok=True)


MAIN_SRC = (
    "import helper\n"
    "\n"
    "\n"
    "def main():\n"
    "    a = helper.add(2, 3)\n"
    "    b = helper.twice(a)\n"
    "    c = helper.add(a, b)\n"
    "    helper.show(a, b, c)\n"
    "    return (a, b, c)\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

HELPER_SRC = (
    "def add(x, y):\n"
    "    return x + y\n"
    "\n"
    "\n"
    "def twice(x):\n"
    "    return add(x, x)\n"
    "\n"
    "\n"
    "def show(*vals):\n"
    "    return vals\n"
)

RECUR_SRC = (
    "def fact(n):\n"
    "    if n <= 1:\n"
    "        return 1\n"
    "    return n * fact(n - 1)\n"
    "\n"
    "\n"
    "def main():\n"
    "    return fact(5)\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    main()\n"
)

NODE_SERVER_SRC = (
    "import http from 'node:http';\n"
    "const port = Number(process.argv[2] || 0);\n"
    "const server = http.createServer((req, res) => {\n"
    "  res.writeHead(200, { 'content-type': 'text/plain' });\n"
    "  res.end('e4-ok');\n"
    "  setTimeout(() => process.exit(0), 400);\n"
    "});\n"
    "server.listen(port, '127.0.0.1', () => {\n"
    "  fetch(`http://127.0.0.1:${server.address().port}/`).then((r) => r.text()).catch(() => {});\n"
    "});\n"
)

CRASH_SRC = (
    "import helper\n"
    "\n"
    "\n"
    "def boom():\n"
    "    raise RuntimeError('e4-boom')\n"
    "\n"
    "\n"
    "boom()\n"
)


def make_repo(name, files):
    root = os.path.join(TMP, name)
    os.makedirs(root)
    for fname, src in files.items():
        with open(os.path.join(root, fname), "w", encoding="ascii", newline="\n") as fh:
            fh.write(src)
    return root


def load_doc(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def v2_ok(doc, label):
    check(isinstance(doc, dict), label + ": doc not a dict")
    check(set(doc.keys()) == SCHEMA_KEYS,
          label + ": schema keys not closed: %r" % sorted(doc.keys()))
    check(doc["schema"] == "trace-facts-v2", label + ": wrong schema value")
    check(doc["runtime"] in ("python", "node"), label + ": bad runtime")
    check(isinstance(doc["duration_s"], (int, float)) and doc["duration_s"] >= 0,
          label + ": duration_s not a measured non-negative number")
    check(isinstance(doc["command"], str) and doc["command"], label + ": command missing")
    check(isinstance(doc["files"], dict), label + ": files not a dict")
    check(isinstance(doc["edges"], list), label + ": edges not a list")
    for rel, lines in doc["files"].items():
        check("\\" not in rel and ":" not in rel and not rel.startswith(".."),
              label + ": non-posix/escaping key: %r" % rel)
        check(lines == sorted(set(lines)) and all(x >= 1 for x in lines),
              label + ": lines not ascending-dedup for %s" % rel)
    prev = None
    for e in doc["edges"]:
        check(set(e.keys()) == {"caller_file", "caller_line", "callee_file", "callee_line"},
              label + ": edge keys not closed: %r" % sorted(e.keys()))
        cur = (e["caller_file"], e["caller_line"], e["callee_file"], e["callee_line"])
        check(e["caller_line"] >= 1 and e["callee_line"] >= 1, label + ": non-positive line")
        if prev is not None:
            check(prev < cur, label + ": edges not strictly ascending: %r after %r" % (cur, prev))
        prev = cur


def line_of(src, needle):
    for i, ln in enumerate(src.splitlines(), 1):
        if needle in ln:
            return i
    raise AssertionError("needle %r not found" % needle)


@case("C1 python line trace + v2 closed schema + import chain")
def c1_py_lines():
    root = make_repo("c1", {"main.py": MAIN_SRC, "helper.py": HELPER_SRC})
    out = os.path.join(TMP, "c1.json")
    rc, so, se = run([PY, "-B", PY_COLLECTOR, "--repo-root", root,
                      os.path.join(root, "main.py"), "--out", out])
    check(rc == 0, "C1 rc=%d stderr=%s" % (rc, se[-400:]))
    jlines = [ln for ln in so.splitlines() if ln.startswith("{")]
    check(len(jlines) == 1, "C1 stdout must be exactly the JSON line, got %d" % len(jlines))
    doc = json.loads(jlines[0])
    v2_ok(doc, "C1")
    check(doc["repo"] == "c1", "C1 repo=%r" % doc["repo"])
    check(doc["runtime"] == "python", "C1 runtime")
    check("main.py" in doc["files"] and "helper.py" in doc["files"],
          "C1 import chain broken: %r" % sorted(doc["files"]))
    check(not any("runpy" in k or "importlib" in k for k in doc["files"]),
          "C1 stdlib leaked: %r" % sorted(doc["files"]))
    check(os.path.isfile(out), "C1 --out missing")
    # expected lines are computed from the fixture text itself (no magic numbers)
    want_main = [i for i, ln in enumerate(MAIN_SRC.splitlines(), 1)
                 if ln.strip() and not ln.startswith("if __name")]
    for ln in want_main:
        check(ln in doc["files"]["main.py"], "C1 line %d of main.py not traced" % ln)


@case("C2 call events produce exact caller->callee edge pairs")
def c2_py_edges_exact():
    root = make_repo("c2", {"main.py": MAIN_SRC, "helper.py": HELPER_SRC})
    out = os.path.join(TMP, "c2.json")
    rc, _so, se = run([PY, "-B", PY_COLLECTOR, "--repo-root", root,
                       os.path.join(root, "main.py"), "--out", out])
    check(rc == 0, "C2 rc=%d stderr=%s" % (rc, se[-400:]))
    doc = load_doc(out)
    edges = [(e["caller_file"], e["caller_line"], e["callee_file"], e["callee_line"])
             for e in doc["edges"]]
    expected = sorted([
        ("main.py", 5, "helper.py", line_of(HELPER_SRC, "def add(")),
        ("main.py", 6, "helper.py", line_of(HELPER_SRC, "def twice(")),
        ("main.py", 7, "helper.py", line_of(HELPER_SRC, "def add(")),
        ("main.py", 8, "helper.py", line_of(HELPER_SRC, "def show(")),
        ("main.py", line_of(MAIN_SRC, "    main()"), "main.py", line_of(MAIN_SRC, "def main():")),
        ("helper.py", line_of(HELPER_SRC, "return add(x, x)"), "helper.py",
         line_of(HELPER_SRC, "def add(")),
    ])
    check(edges == expected,
          "C2 edges mismatch\n  got      %r\n  expected %r" % (edges, expected))


@case("C3 recursion yields self-edge, deduplicated to one")
def c3_py_recursion():
    root = make_repo("c3", {"rec.py": RECUR_SRC})
    out = os.path.join(TMP, "c3.json")
    rc, _so, se = run([PY, "-B", PY_COLLECTOR, "--repo-root", root,
                       os.path.join(root, "rec.py"), "--out", out])
    check(rc == 0, "C3 rc=%d stderr=%s" % (rc, se[-400:]))
    doc = load_doc(out)
    edges = [(e["caller_file"], e["caller_line"], e["callee_file"], e["callee_line"])
             for e in doc["edges"]]
    self_edge = ("rec.py", line_of(RECUR_SRC, "return n * fact("), "rec.py",
                 line_of(RECUR_SRC, "def fact("))
    check(edges.count(self_edge) == 1,
          "C3 self-edge must appear exactly once, got %r in %r" % (self_edge, edges))
    check(("rec.py", line_of(RECUR_SRC, "    return fact(5)"), "rec.py",
           line_of(RECUR_SRC, "def fact(")) in edges, "C3 top call edge missing: %r" % edges)


@case("C4 every edge endpoint stays inside the repo (out-of-repo caller dropped)")
def c4_edges_in_repo_only():
    root = make_repo("c4", {"main.py": MAIN_SRC, "helper.py": HELPER_SRC})
    out = os.path.join(TMP, "c4.json")
    rc, _so, se = run([PY, "-B", PY_COLLECTOR, "--repo-root", root,
                       os.path.join(root, "main.py"), "--out", out])
    check(rc == 0, "C4 rc=%d stderr=%s" % (rc, se[-400:]))
    doc = load_doc(out)
    in_repo = set(doc["files"].keys()) | {"main.py", "helper.py"}
    for e in doc["edges"]:
        check(e["caller_file"] in in_repo,
              "C4 out-of-repo caller leaked: %r" % (e,))
        check(e["callee_file"] in in_repo,
              "C4 out-of-repo callee leaked: %r" % (e,))
    # the very first frame's caller is runpy (outside the repo): no such edge may exist
    check(not any("runpy" in (e["caller_file"] + e["callee_file"]) for e in doc["edges"]),
          "C4 runpy edge leaked")


@case("C5 edges sort ascending and deduplicate across duplicate calls")
def c5_edges_order():
    root = make_repo("c5", {"main.py": MAIN_SRC, "helper.py": HELPER_SRC})
    out = os.path.join(TMP, "c5.json")
    rc, _so, se = run([PY, "-B", PY_COLLECTOR, "--repo-root", root,
                       os.path.join(root, "main.py"), "--out", out])
    check(rc == 0, "C5 rc=%d stderr=%s" % (rc, se[-400:]))
    doc = load_doc(out)
    keys = [(e["caller_file"], e["caller_line"], e["callee_file"], e["callee_line"])
            for e in doc["edges"]]
    check(len(keys) == len(set(keys)), "C5 duplicate edges present")
    check(keys == sorted(keys), "C5 edges not sorted")


@case("C6 --path inserts before first site-packages entry (v3 semantics)")
def c6_path_insert():
    root = make_repo("c6", {"main.py": MAIN_SRC, "helper.py": HELPER_SRC,
                            "probe.py": PATHPROBE_SRC})
    pathdir = os.path.join(TMP, "c6-pathdir")
    os.makedirs(pathdir)
    with open(os.path.join(pathdir, "onlyhere.py"), "w", encoding="ascii", newline="\n") as fh:
        fh.write("MARK = 'onlyhere-ok'\n")
    rc, _so, se = run([PY, "-B", PY_COLLECTOR, "--repo-root", root, "--path", pathdir,
                       os.path.join(root, "probe.py"), pathdir])
    check(rc == 0, "C6 rc=%d stderr=%s" % (rc, se[-400:]))
    check("imported onlyhere-ok" in se, "C6 --path dir not importable: %s" % se[-300:])
    m1 = re.search(r"path-idx (\d+)", se)
    m2 = re.search(r"site-idx (-?\d+)", se)
    check(m1 and m2, "C6 probe indices missing: %s" % se[-300:])
    idx, site_idx = int(m1.group(1)), int(m2.group(1))
    check(0 <= idx < site_idx,
          "C6 --path idx=%d must precede site-packages idx=%d" % (idx, site_idx))


@case("C7 junction paths normalize to real repo files (realpath)")
def c7_junction_realpath():
    stage = None
    for cand in (os.path.join(V119, "stage-click", "click"),
                 os.path.join(WS, "agent-out", "v19-exp", "stage-click", "click")):
        if os.path.isdir(cand):
            stage = cand
            break
    click_init = os.path.join(CLICK_ROOT, "__init__.py")
    if not (stage and os.path.isfile(click_init)):
        raise SkipCase("no stage-click junction and/or click corpus; skip realpath check")
    sys.path.insert(0, SKILL)
    import trace_collect as tc
    filt = tc.RepoFilter(CLICK_ROOT)
    got = filt.rel_of(os.path.join(stage, "core.py"))
    check(got == "core.py", "C7 junction not normalized: %r" % got)
    check(filt.rel_of(os.path.join(V119, "e4-report.md")) is None,
          "C7 out-of-repo file must be filtered")


@case("C8 -B discipline: no __pycache__ left in traced repos")
def c8_no_pycache():
    root = make_repo("c8", {"main.py": MAIN_SRC, "helper.py": HELPER_SRC})
    rc, _so, se = run([PY, "-B", PY_COLLECTOR, "--repo-root", root,
                       os.path.join(root, "main.py")])
    check(rc == 0, "C8 rc=%d stderr=%s" % (rc, se[-300:]))
    check(not os.path.isdir(os.path.join(root, "__pycache__")),
          "C8 __pycache__ written into traced repo")
    check(not os.path.isdir(os.path.join(root, "helper.__pycache__")),
          "C8 stray pycache variant")


@case("C9 node arm end to end: schema v2, files traced, edges honestly []")
def c9_node_chain():
    root = make_repo("c9n", {"serve_once.mjs": NODE_SERVER_SRC})
    covdir = os.path.join(TMP, "c9-cov")
    out = os.path.join(TMP, "c9.json")
    port = free_port()
    rc, so, se = run([NODE, NODE_COLLECTOR, root, "serve_once.mjs",
                      "--covdir", covdir, "--port", str(port), "--timeout", "8000",
                      "--out", out, "--", str(port)], timeout=90)
    check(rc == 0, "C9 rc=%d stderr=%s" % (rc, se[-500:]))
    check(so.strip() == "", "C9 stdout must stay empty when --out is given")
    doc = load_doc(out)
    v2_ok(doc, "C9")
    check(doc["runtime"] == "node", "C9 runtime")
    check(doc["edges"] == [], "C9 edges must be honestly empty, got %r" % doc["edges"])
    check("serve_once.mjs" in doc["files"] and len(doc["files"]["serve_once.mjs"]) >= 5,
          "C9 target under-traced: %r" % sorted(doc["files"]))
    check(not any("node_modules" in k for k in doc["files"]), "C9 node_modules leaked")
    check("reached 200" in se, "C9 probe did not log 200: %s" % se[-300:])


@case("C10 real corpus: click 6.7 -> trace-facts-v2 with edges>0 (smoke artifact)")
def c10_click_real():
    if not os.path.isfile(os.path.join(CLICK_ROOT, "__init__.py")):
        raise SkipCase("click corpus missing; restore via tests/corpus/fetch_corpus.py")
    out = os.path.join(SMOKE, "click-trace.json")
    probe = os.path.join(TMP, "click_probe.py")
    with open(probe, "w", encoding="ascii", newline="\n") as fh:
        fh.write(CLICK_PROBE)
    rc, _so, se = run([PY, "-B", PY_COLLECTOR, "--repo-root", CLICK_ROOT, probe,
                       CLICK_ROOT, "--out", out], timeout=300)
    if rc == 7:
        raise SkipCase("click 6.7 not importable on this interpreter (%s)" % PY)
    check(rc == 0, "C10 rc=%d stderr=%s" % (rc, se[-600:]))
    doc = load_doc(out)
    v2_ok(doc, "C10")
    check(len(doc["edges"]) > 0,
          "C10 real-corpus trace must carry edges>0, got %d" % len(doc["edges"]))
    for want in ("core.py", "decorators.py", "__init__.py"):
        check(want in doc["files"], "C10 click source %s missing" % want)


@case("C11 real corpus: express arm runs the cov path with edges==[] (smoke artifact)")
def c11_express_real():
    if not os.path.isdir(os.path.join(EXPRESS_ROOT, "node_modules")):
        raise SkipCase("express node_modules absent; run the corpus npm install first")
    out = os.path.join(SMOKE, "express-trace.json")
    shim = os.path.join(SMOKE, "shim_express.cjs")
    with open(shim, "w", encoding="ascii", newline="\n") as fh:
        fh.write(EXPRESS_SHIM)
    covdir = os.path.join(TMP, "c11-cov")
    rc, so, se = run([NODE, NODE_COLLECTOR, EXPRESS_ROOT, shim,
                      "--covdir", covdir, "--grace-ms", "3000", "--out", out,
                      "--", EXPRESS_ROOT], timeout=180)
    check(rc == 0, "C11 rc=%d stderr=%s" % (rc, se[-600:]))
    doc = load_doc(out)
    v2_ok(doc, "C11")
    check(doc["runtime"] == "node" and doc["edges"] == [],
          "C11 node arm must carry edges==[]")
    check(any(k.startswith("lib/") for k in doc["files"]),
          "C11 express lib/ not traced: %r" % sorted(doc["files"])[:8])
    check("index.js" in doc["files"], "C11 express entry not traced")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


PATHPROBE_SRC = (
    "import sys\n"
    "\n"
    "marker = sys.argv[1]\n"
    "idx = -1\n"
    "for i, entry in enumerate(sys.path):\n"
    "    if entry and entry == marker:\n"
    "        idx = i\n"
    "        break\n"
    "site_idx = -1\n"
    "for i, entry in enumerate(sys.path):\n"
    "    if 'site-packages' in entry.lower():\n"
    "        site_idx = i\n"
    "        break\n"
    "sys.stdout.write('path-idx %d\\n' % idx)\n"
    "sys.stdout.write('site-idx %d\\n' % site_idx)\n"
    "import onlyhere\n"
    "sys.stdout.write('imported %s\\n' % onlyhere.MARK)\n"
)

# Loads the flat-layout click corpus (the corpus dir itself is the package dir) as
# package "click" via importlib, then runs one real command through it.
CLICK_PROBE = (
    "import importlib.util\n"
    "import os\n"
    "import sys\n"
    "\n"
    "root = sys.argv[1]\n"
    "spec = importlib.util.spec_from_file_location(\n"
    "    'click', os.path.join(root, '__init__.py'),\n"
    "    submodule_search_locations=[root])\n"
    "mod = importlib.util.module_from_spec(spec)\n"
    "sys.modules['click'] = mod\n"
    "try:\n"
    "    spec.loader.exec_module(mod)\n"
    "\n"
    "    import click\n"
    "\n"
    "    @click.command()\n"
    "    @click.option('--name', default='e4')\n"
    "    def hello(name):\n"
    "        click.echo('hello %s' % name)\n"
    "\n"
    "    hello.main(args=['--name', 'e4'], standalone_mode=False)\n"
    "except SystemExit:\n"
    "    raise\n"
    "except Exception as exc:\n"
    "    sys.stderr.write('CLICK_IMPORT_FAIL %s: %s\\n' % (type(exc).__name__, exc))\n"
    "    sys.exit(7)\n"
    "sys.stderr.write('click-smoke-ok version=%s\\n' % click.__version__)\n"
)

# Boots the express package (corpus root passed as argv[2]) on an ephemeral port,
# self-requests once, and self-exits so the V8 coverage flush actually happens.
EXPRESS_SHIM = (
    "const http = require('node:http');\n"
    "const express = require(process.argv[2]);\n"
    "const app = express();\n"
    "app.get('/', (req, res) => {\n"
    "  res.status(200).send('e4-ok');\n"
    "});\n"
    "const server = app.listen(0, '127.0.0.1', () => {\n"
    "  const port = server.address().port;\n"
    "  http.get('http://127.0.0.1:' + port + '/', (r) => {\n"
    "    r.resume();\n"
    "    setTimeout(() => process.exit(0), 300);\n"
    "  });\n"
    "});\n"
)


@case("N1 node arm: missing covdir is auto-created and collection proceeds")
def n1_node_missing_covdir():
    root = make_repo("n1", {"a.mjs": NODE_SERVER_SRC})
    covdir = os.path.join(TMP, "n1-auto-cov")
    out = os.path.join(TMP, "n1.json")
    port = free_port()
    rc, so, se = run([NODE, NODE_COLLECTOR, root, "a.mjs", "--covdir", covdir,
                      "--port", str(port), "--timeout", "8000", "--out", out,
                      "--", str(port)], timeout=90)
    check(rc == 0, "N1 rc=%d stderr=%s" % (rc, se[-400:]))
    check(os.path.isdir(covdir), "N1 covdir not auto-created")
    check(load_doc(out)["schema"] == "trace-facts-v2", "N1 doc schema")


@case("N2 node arm: covdir without reports fails loud with exit 1")
def n2_node_empty_covdir():
    root = make_repo("n2", {"a.mjs": NODE_SERVER_SRC})
    covdir = os.path.join(TMP, "n2-empty")
    os.makedirs(covdir)
    rc, so, se = run([NODE, NODE_COLLECTOR, root, "a.mjs",
                      "--covdir", covdir, "--timeout", "1500", "--grace-ms", "400"],
                     timeout=60)
    check(rc == 1, "N2 rc=%d (want 1)" % rc)
    check("no JSON" in se, "N2 stderr not loud: %r" % se[:200])


@case("N3 node arm: corrupt coverage JSON fails loud naming the file")
def n3_node_corrupt_json():
    root = make_repo("n3", {"a.mjs": "process.stdout.write('x\\n');\n"})
    covdir = os.path.join(TMP, "n3-cov")
    os.makedirs(covdir)
    with open(os.path.join(covdir, "coverage-bad.json"), "w", encoding="ascii") as fh:
        fh.write("{not json at all")
    rc, so, se = run([NODE, NODE_COLLECTOR, root, "a.mjs", "--covdir", covdir],
                     timeout=60)
    check(rc == 1, "N3 rc=%d (want 1)" % rc)
    check("corrupt" in se and "coverage-bad.json" in se,
          "N3 stderr must name the corrupt file: %r" % se[:300])


@case("N4 python arm: bad --repo-root exits 2 without writing --out")
def n4_bad_repo_root():
    out = os.path.join(TMP, "n4.json")
    rc, so, se = run([PY, "-B", PY_COLLECTOR, "--repo-root", os.path.join(TMP, "nope"),
                      os.path.join(TMP, "main.py"), "--out", out], timeout=60)
    check(rc == 2, "N4 rc=%d (want 2)" % rc)
    check("--repo-root" in se, "N4 stderr not loud: %r" % se[:200])
    check(not os.path.isfile(out), "N4 --out must not be written on usage error")


@case("N5 python arm: crashing target keeps partial trace and exits 3")
def n5_partial_trace():
    root = make_repo("n5", {"main.py": MAIN_SRC, "helper.py": HELPER_SRC,
                            "crash.py": CRASH_SRC})
    out = os.path.join(TMP, "n5.json")
    rc, so, se = run([PY, "-B", PY_COLLECTOR, "--repo-root", root,
                      os.path.join(root, "crash.py"), "--out", out], timeout=60)
    check(rc == 3, "N5 rc=%d (want 3 for partial trace)" % rc)
    check("RuntimeError" in se, "N5 traceback missing on stderr")
    doc = load_doc(out)
    v2_ok(doc, "N5")
    check("helper.py" in doc["files"],
          "N5 pre-crash import chain lost: %r" % sorted(doc["files"]))
    check("crash.py" in doc["files"], "N5 crashing target file lost")


def main():
    fresh_dirs()
    t0 = time.time()
    passed = failed = skipped = 0
    for name, fn in CASES:
        t1 = time.time()
        try:
            fn()
            passed += 1
            print("[OK]   %s (%.1fs)" % (name, time.time() - t1))
        except SkipCase as exc:
            skipped += 1
            print("[SKIP] %s -- %s" % (name, exc))
        except AssertionError as exc:
            failed += 1
            print("[FAIL] %s -- %s" % (name, exc))
        except Exception as exc:  # harness-level surprise counts as a failure
            failed += 1
            print("[FAIL] %s -- unexpected %r" % (name, exc))
        sys.stdout.flush()
    print("test_trace_collect: %d passed / %d failed / %d skipped (%.1fs total)"
          % (passed, failed, skipped, time.time() - t0))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
