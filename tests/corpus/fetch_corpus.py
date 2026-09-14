#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch pinned real-world code corpora for analyze_structure.py smoke tests.

Zero-dependency (stdlib only). Downloads pinned GitHub tarballs through the
local proxy (codeload.github.com), extracts each into
tests/corpus/<lang>/<repo>-<ref>/ (optionally restricted to one subdir), then
smoke-runs `analyze_structure.py analyze` on every corpus dir via subprocess:
asserts exit 0, a parseable structure-facts.json, and symbols > 0.

Idempotent: an existing non-empty target dir is skipped; --force re-downloads.
A single repo failure prints [WARN] and the run continues; exit 1 only when
ALL repos fail. All console output is ASCII (GBK-console safe).

Usage:
  python fetch_corpus.py [--force] [--only python,go] [--skip-smoke] [--list]
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

PROXY = "http://127.0.0.1:7897"
MAX_ATTEMPTS = 3                    # 1 initial try + 2 retries, then give up
MAX_EXTRACT_BYTES = 64 * 1024 * 1024
SMOKE_TIMEOUT = 600                 # seconds per analyze run

# (lang, owner/repo, pinned ref, subdir restrict ('' = whole repo), license)
CORPUS = [
    ("python",     "pallets/click",          "6.7",            "click",         "BSD-3-Clause"),
    ("javascript", "expressjs/express",      "4.0.0",          "",              "MIT"),
    ("typescript", "TypeStrong/ts-node",     "v9.1.1",         "",              "MIT"),
    ("go",         "gin-gonic/gin",          "v1.1",           "",              "MIT"),
    ("rust",       "dtolnay/anyhow",         "1.0.20",         "",              "MIT OR Apache-2.0"),
    ("java",       "square/javapoet",        "javapoet-1.0.0", "",              "Apache-2.0"),
    ("c",          "jqlang/jq",              "jq-1.4",         "",              "MIT (COPYING)"),
    ("cpp",        "fmtlib/fmt",             "3.0.2",          "fmt",           "MIT"),
    ("csharp",     "Humanizr/Humanizer",     "v1.0.0",         "src/Humanizer", "Apache-2.0"),
    ("ruby",       "sinatra/sinatra",        "v1.2.0",         "",              "MIT"),
    ("lua",        "leafo/lapis",            "v1.0.0",         "",              "MIT (declared in README)"),
    ("php",        "Seldaek/monolog",        "1.10.0",         "src/Monolog",   "MIT"),
    ("kotlin",     "mockito/mockito-kotlin", "2.0.0",          "",              "MIT"),
    ("swift",      "Alamofire/Alamofire",    "4.7.3",          "Source",        "MIT"),
]

EXTS = {
    "python": (".py",),
    "javascript": (".js", ".mjs", ".cjs"),
    "typescript": (".ts", ".tsx"),
    "go": (".go",),
    "rust": (".rs",),
    "java": (".java",),
    "c": (".c", ".h"),
    "cpp": (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"),
    "csharp": (".cs",),
    "ruby": (".rb",),
    "lua": (".lua",),
    "php": (".php",),
    "kotlin": (".kt", ".kts"),
    "swift": (".swift",),
}

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ANALYZE = os.path.join(REPO_ROOT, "analyze_structure.py")
SMOKE_ROOT = os.path.join(HERE, "_smoke")

SOURCE_BUDGET = 300 * 1024          # per-repo dominant-language source budget


def log(msg):
    print(msg, flush=True)


def http_get(url):
    """GET through the local proxy; max 3 attempts total, then raise."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(
        {"http": PROXY, "https": PROXY}))
    err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with opener.open(url, timeout=120) as resp:
                return resp.read()
        except Exception as exc:                     # noqa: BLE001 - report and retry
            err = exc
            if attempt < MAX_ATTEMPTS:
                log("  [RETRY] attempt %d/%d failed: %s" % (attempt, MAX_ATTEMPTS, exc))
                time.sleep(2)
    raise err


def safe_extract(data, dest, sub):
    """Extract a tar.gz (bytes) into dest, refusing path escapes.

    sub='' keeps the whole tree (minus the tarball's top-level dir); a non-empty
    sub keeps only members under sub/, re-rooted at dest. Returns
    (files_written, license_file_rel_or_None).
    """
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        prefix = sub.rstrip("/") + "/" if sub else ""
        os.makedirs(dest, exist_ok=True)
        n_files = 0
        total = 0
        lic = None
        for m in tf.getmembers():
            name = m.name.replace("\\", "/")
            parts = name.split("/")
            if len(parts) < 2 or name.startswith("/"):
                continue
            if ".." in parts:
                raise ValueError("unsafe tar member: %s" % name)
            if m.issym() or m.islnk() or m.isdev():
                continue
            rel = "/".join(parts[1:])
            base = parts[-1].upper()
            if (m.isfile() and lic is None
                    and base.startswith(("LICENSE", "LICENCE", "COPYING"))):
                lic = rel
            if prefix:
                if not rel.startswith(prefix):
                    continue
                rel = rel[len(prefix):]
                if not rel:
                    continue
            target = os.path.join(dest, *rel.split("/"))
            if m.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            if not m.isfile():
                continue
            os.makedirs(os.path.dirname(target) or dest, exist_ok=True)
            fobj = tf.extractfile(m)
            if fobj is None:
                continue
            payload = fobj.read()
            total += len(payload)
            if total > MAX_EXTRACT_BYTES:
                raise ValueError("extract budget exceeded (%d bytes)" % MAX_EXTRACT_BYTES)
            with open(target, "wb") as w:
                w.write(payload)
            n_files += 1
    return n_files, lic


def measure_lang(dest, lang):
    exts = EXTS.get(lang, ())
    n = 0
    total = 0
    for root, _dirs, files in os.walk(dest):
        for fn in files:
            if fn.lower().endswith(exts):
                total += os.path.getsize(os.path.join(root, fn))
                n += 1
    return n, total


def smoke(lang, dest):
    """Run analyze on dest; return (stats, None) or (None, reason)."""
    outdir = os.path.join(SMOKE_ROOT, lang)
    if os.path.isdir(outdir):
        shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir, exist_ok=True)
    cmd = [sys.executable, ANALYZE, "analyze", dest, "--outdir", outdir]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=SMOKE_TIMEOUT)
    except Exception as exc:                         # noqa: BLE001
        return None, "analyze spawn failed: %r" % (exc,)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-300:]
        return None, "analyze exit %d; stderr: %s" % (proc.returncode, tail)
    fpath = os.path.join(outdir, "structure-facts.json")
    if not os.path.isfile(fpath):
        return None, "analyze produced no structure-facts.json"
    try:
        with open(fpath, "r", encoding="utf-8") as fh:
            facts = json.load(fh)
    except Exception as exc:                         # noqa: BLE001
        return None, "facts JSON unparsable: %r" % (exc,)
    symbols = facts.get("symbols") or []
    if len(symbols) == 0:
        return None, "facts parsed but symbols == 0"
    file_lang = {}
    for row in facts.get("files") or []:
        key = row.get("path") or row.get("file")
        if key:
            file_lang[key] = row.get("language")
    per_lang = {}
    for sym in symbols:
        lg = file_lang.get(sym.get("file"))
        if lg:
            per_lang[lg] = per_lang.get(lg, 0) + 1
    shutil.rmtree(outdir, ignore_errors=True)
    return {"symbols": len(symbols), "per_lang": per_lang}, None


def corpus_list(only):
    for lang, repo, ref, sub, lic in CORPUS:
        if only and lang not in only:
            continue
        yield lang, repo, ref, sub, lic


def main():
    ap = argparse.ArgumentParser(description="Fetch pinned real-code corpus "
                                             "for analyze_structure.py smoke tests.")
    ap.add_argument("--force", action="store_true",
                    help="re-download even if the target dir is non-empty")
    ap.add_argument("--only", default="",
                    help="comma-separated languages to process (default: all)")
    ap.add_argument("--skip-smoke", action="store_true",
                    help="download/extract only, skip analyze smoke runs")
    ap.add_argument("--list", action="store_true",
                    help="print the corpus table and exit")
    args = ap.parse_args()

    only = set(x.strip() for x in args.only.split(",") if x.strip())
    if args.list:
        for lang, repo, ref, sub, lic in corpus_list(only):
            print("%-10s %-24s %-16s sub=%-14s %s" % (lang, repo, ref, sub or "-", lic))
        return 0
    if not os.path.isfile(ANALYZE):
        log("[FATAL] analyze_structure.py not found at %s" % ANALYZE)
        return 2

    os.makedirs(SMOKE_ROOT, exist_ok=True)
    results = []
    failures = []
    t0 = time.time()
    for lang, repo, ref, sub, lic in corpus_list(only):
        short = repo.split("/")[-1]
        dest = os.path.join(HERE, lang, "%s-%s" % (short, ref))
        log("== [%s] %s @ %s (license %s)" % (lang, repo, ref, lic))
        try:
            if os.path.isdir(dest) and os.listdir(dest) and not args.force:
                log("  [SKIP] %s already present (%s)" % (dest, "use --force to refetch"))
            else:
                url = "https://codeload.github.com/%s/tar.gz/%s" % (repo, ref)
                data = http_get(url)
                part = dest + ".part"
                if os.path.isdir(part):
                    shutil.rmtree(part, ignore_errors=True)
                n_files, lic_file = safe_extract(data, part, sub)
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                os.rename(part, dest)
                over = "" if not sub else " (subdir %s)" % sub
                log("  [OK] extracted %d files%s license-file=%s"
                    % (n_files, over, lic_file or "none"))
        except Exception as exc:                     # noqa: BLE001
            log("  [WARN] fetch failed: %r" % (exc,))
            failures.append("%s:%s (%r)" % (lang, repo, exc))
            results.append((lang, repo, ref, None, None, None, None))
            continue

        n_src, src_bytes = measure_lang(dest, lang)
        flag = "" if src_bytes <= SOURCE_BUDGET else "  [WARN] over %dKB budget" % (SOURCE_BUDGET // 1024)
        log("  [SIZE] %s files, %dKB dominant-language source%s" % (n_src, src_bytes // 1024, flag))
        if args.skip_smoke:
            results.append((lang, repo, ref, n_src, src_bytes, None, None))
            continue
        stats, err = smoke(lang, dest)
        if err is not None:
            log("  [WARN] smoke failed: %s" % err)
            failures.append("%s:%s (smoke: %s)" % (lang, repo, err))
            results.append((lang, repo, ref, n_src, src_bytes, None, None))
        else:
            top = sorted(stats["per_lang"].items(), key=lambda kv: -kv[1])[:2]
            log("  [SMOKE] symbols=%d per-lang=%s" % (stats["symbols"], top))
            results.append((lang, repo, ref, n_src, src_bytes, stats["symbols"], stats["per_lang"]))

    log("")
    log("== SUMMARY (%d repos, %.1fs) ==" % (len(results), time.time() - t0))
    ok = 0
    for lang, repo, ref, n_src, src_bytes, syms, per in results:
        if syms is None and not args.skip_smoke:
            log("  [FAIL] %-10s %-28s %-16s" % (lang, repo, ref))
            continue
        ok += 1
        log("  [PASS] %-10s %-28s %-16s src=%dKB files=%d symbols=%s"
            % (lang, repo, ref, (src_bytes or 0) // 1024, n_src or 0,
               syms if syms is not None else "n/a"))
    if failures:
        log("failures (%d):" % len(failures))
        for f in failures:
            log("  - %s" % f)
    log("total: %d/%d passed" % (ok, len(results)))
    if ok == 0:
        log("[FATAL] every repo failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
