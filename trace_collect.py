# code2course/trace_collect.py - v1.19.0 E4: python collector producing trace-facts-v2.
# Ported from the v19-exp prototype (tools/trace_py.py) and upgraded with EDGE-LEVEL call
# events: on every 'call' the current frame (caller) -> new frame (callee) pair is recorded
# when BOTH sides resolve (realpath) inside --repo-root; line events fill "files" as before.
# Carries the three prototype safeguards: realpath normalization (junctions), -B (no
# __pycache__), --path inserted before the first site-packages entry. stdout = the JSON only.
# Exit codes: 0 ok, 2 usage/config error, 3 target crashed (partial trace still written).
import json
import os
import runpy
import sys
import time
import traceback

SCHEMA = "trace-facts-v2"


def warn(msg):
    """One diagnostic line to stderr (ASCII only)."""
    sys.stderr.write("[trace_collect] %s\n" % msg)


def parse_args(argv):
    """Known flags (--repo-root/--path/--out) anywhere; first bare word = TARGET; the rest
    pass through verbatim as target args (SPEC v19-exp recipe shape)."""
    repo_root = None
    out = None
    target = None
    target_args = []
    extra_paths = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            sys.stderr.write(
                "usage: python -B trace_collect.py --repo-root DIR [--path DIR]..."
                " [--out FILE] TARGET [target args...]\n"
                "  known flags may also trail the target; --path dirs are inserted before\n"
                "  the first site-packages entry (never PYTHONPATH, never plain append).\n"
                "  trace-facts-v2 JSON goes to --out and stdout; diagnostics to stderr.\n"
                "  exit: 0 ok, 2 usage error, 3 target crashed (partial trace kept).\n"
            )
            sys.exit(0)
        elif a == "--repo-root":
            i += 1
            if i >= len(argv):
                warn("error: --repo-root needs a value")
                sys.exit(2)
            repo_root = argv[i]
        elif a == "--path":
            i += 1
            if i >= len(argv):
                warn("error: --path needs a value")
                sys.exit(2)
            extra_paths.append(argv[i])
        elif a == "--out":
            i += 1
            if i >= len(argv):
                warn("error: --out needs a value")
                sys.exit(2)
            out = argv[i]
        elif target is None and not a.startswith("--"):
            target = a
        else:
            target_args.append(a)
        i += 1
    if repo_root is None:
        warn("error: --repo-root is required")
        sys.exit(2)
    if target is None:
        warn("error: TARGET script is required")
        sys.exit(2)
    return repo_root, extra_paths, out, target, target_args


class RepoFilter:
    """realpath-normalized repo membership; returns posix relpath or None."""

    def __init__(self, repo_root):
        self.root = os.path.realpath(repo_root)

    def rel_of(self, path):
        if not path:
            return None
        real = os.path.realpath(path)
        rel = os.path.relpath(real, self.root)
        if os.path.isabs(rel) or rel == os.pardir or rel.startswith(os.pardir + os.sep):
            return None
        return rel.replace(os.sep, "/")


def make_tracer(filt, lines_by_file, edges, cache):
    """Global settrace callable: 'call' records caller->callee edges (both sides in-repo),
    'line' records hit lines for in-repo frames; out-of-repo frames return None for lines
    only - their nested calls still dispatch here (thread-level global tracer)."""
    def tracer(frame, event, arg):
        code = frame.f_code
        if event == "call":
            callee = cache.get(code, "?")
            if callee == "?":
                callee = filt.rel_of(code.co_filename)
                cache[code] = callee
            if callee is None:
                return None
            back = frame.f_back
            if back is not None:
                caller = cache.get(back.f_code, "?")
                if caller == "?":
                    caller = filt.rel_of(back.f_code.co_filename)
                    cache[back.f_code] = caller
                if caller is not None:
                    caller_line = back.f_lineno
                    callee_line = frame.f_lineno
                    if caller_line >= 1 and callee_line >= 1:
                        edges.add((caller, caller_line, callee, callee_line))
            entry = lines_by_file.setdefault(callee, set())
            if frame.f_lineno >= 1:
                entry.add(frame.f_lineno)
        elif event == "line":
            rel = cache.get(code)
            if rel is not None:
                lines_by_file[rel].add(frame.f_lineno)
        return tracer
    return tracer


def build_doc(repo_root, command_argv, duration_s, lines_by_file, edges):
    """Closed trace-facts-v2 document; edges sorted by (caller_file, caller_line,
    callee_file, callee_line), deduplicated; keys alphabetical (sort_keys shape)."""
    files = {}
    for rel in sorted(lines_by_file):
        lines = sorted(lines_by_file[rel])
        if lines:
            files[rel] = lines
    edge_list = [
        {"caller_file": c, "caller_line": cl, "callee_file": e, "callee_line": el}
        for (c, cl, e, el) in sorted(edges)
    ]
    # JSON text is dumped with sort_keys=True in main, so insertion order here is cosmetic;
    # keep it alphabetical anyway for byte-identical shapes across runtimes.
    return {
        "command": " ".join(["python"] + list(command_argv)),
        "duration_s": round(duration_s, 3),
        "edges": edge_list,
        "files": files,
        "repo": os.path.basename(os.path.realpath(repo_root)),
        "runtime": "python",
        "schema": SCHEMA,
    }


def main(argv):
    repo_root_arg, extra_paths, out, target_arg, target_args = parse_args(argv)
    repo_root = os.path.abspath(repo_root_arg)
    if not os.path.isdir(repo_root):
        warn("error: --repo-root is not a directory: %s" % repo_root_arg)
        return 2
    target = os.path.abspath(target_arg)
    if not os.path.isfile(target):
        warn("error: TARGET script not found: %s" % target_arg)
        return 2
    filt = RepoFilter(repo_root)
    lines_by_file = {}
    edges = set()
    cache = {}
    old_argv = sys.argv
    # Script dir first (mirrors `python script.py`); --path dirs go before the first
    # site-packages entry (ORG v3 revision: append would lose to installed newer deps).
    sys.path.insert(0, os.path.dirname(target))
    if extra_paths:
        site_idx = len(sys.path)
        for i, entry in enumerate(sys.path):
            if "site-packages" in entry.lower():
                site_idx = i
                break
        for offset, extra in enumerate(extra_paths):
            sys.path.insert(site_idx + offset, os.path.abspath(extra))
    sys.dont_write_bytecode = True  # never write __pycache__ into analyzed repos
    sys.argv = [target] + target_args
    status = 0
    t0 = time.perf_counter()
    sys.settrace(make_tracer(filt, lines_by_file, edges, cache))
    old_stdout = sys.stdout
    sys.stdout = sys.stderr  # target prints must not pollute the JSON-only stdout
    try:
        runpy.run_path(target, run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code not in (None, 0):
            status = 3
            warn("target exited with code %r; partial trace kept" % (code,))
    except BaseException:
        status = 3
        traceback.print_exc(file=sys.stderr)
        warn("target raised; partial trace kept")
    finally:
        sys.settrace(None)
        sys.stdout = old_stdout
        duration_s = time.perf_counter() - t0
        sys.argv = old_argv
    doc = build_doc(filt.root, argv, duration_s, lines_by_file, edges)
    text = json.dumps(doc, sort_keys=True)
    if out:
        out_abs = os.path.abspath(out)
        parent = os.path.dirname(out_abs)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(out_abs, "w", encoding="ascii", newline="\n") as fh:
            fh.write(text + "\n")
    sys.stdout.write(text + "\n")
    warn("files=%d edges=%d duration=%.3fs status=%d" % (
        len(doc["files"]), len(doc["edges"]), duration_s, status))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
