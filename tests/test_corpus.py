#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_corpus.py -- analyze_structure.py 真实语料测试层。

对 tests/corpus/ 下 14 门语言真实仓库逐仓跑 analyze（subprocess，每次 120s 超时），
断言结构事实产物契约（每仓 8 项）+ 同仓双跑 structure-facts.json 逐字节确定性。
语料缺失响亮 skip 并提示一键还原命令；--require-corpus 把 skip 升级为 fail。

运行方式（直跑，风格与 tests/test_analyze_structure.py 一致）：
    python tests/test_corpus.py                      # corpus: N passed / M failed / K skipped
    python tests/test_corpus.py --require-corpus     # 语料缺失从 skip 升级为 fail
    python tests/test_corpus.py --only python,go     # 冒烟：只跑部分语言
    python tests/test_corpus.py --repo <repo-root>   # 缺省自动探测 analyze_structure.py 位置

每仓断言（矩阵列 id）：
    a  analyze exit 0（双跑均 0）
    b  structure-facts.json 存在且可 JSON 解析
    cv facts.schema_version 与 analyze_structure.py:105 SCHEMA_VERSION=3 一致
    ev facts.engine_version 与 analyze_structure.py:115 ENGINE_VERSION=2 一致
    d  symbols 数 >= 5
    e  仓库主语言（目录名）被检出，且该语言符号 >= 1（经 file->language 映射统计；
       符号记录本身不带 lang 字段，见 analyze_structure.py:2523-2536 的 facts 顶层
       与符号排序键——语言归属只能经 files[].language 间接求）
    f  files[] 非空，且每行 language 为 None（未支持扩展名，analyze_structure.py:2284-2291
       如实降级并计 unsupported_files）或属于 16 门语言闭集（:139-141）二者其一；
       另要求主语言文件 >= 1。任何非 None 且不在闭集的取值必红。
    g  确定性：同仓连跑两次，structure-facts.json 逐字节一致
       （无时间戳/无绝对路径契约，analyze_structure.py:69-70）

纪律：本测试不联网、不执行 fetch_corpus.py；临时目录用
os.makedirs(os.path.join(tempfile.gettempdir(), 唯一名)) ——禁用 tempfile.mkdtemp
（Windows 受限令牌下 0700 DACL 目录子进程写入必炸）。输出全 ASCII。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

# ---- 产物契约钉值（漂移即红；来源 analyze_structure.py v1.15.0）----
EXP_SCHEMA_VERSION = 3          # analyze_structure.py:105 SCHEMA_VERSION
EXP_ENGINE_VERSION = 2          # analyze_structure.py:115 ENGINE_VERSION
LANG_CLOSED_SET = frozenset((   # analyze_structure.py:139-141 CLOSED_SETS['language']
    'python', 'javascript', 'typescript', 'java', 'c', 'cpp', 'csharp',
    'go', 'rust', 'php', 'ruby', 'kotlin', 'swift', 'scala', 'dart', 'lua'))

# 语料清单：语言目录名（= 主语言 token，均为闭集成员），每语言恰一个仓库目录。
# 与 tests/corpus/CORPUS.md 清单一致；盘上冲突以盘上为准并在 _discover 里处置。
CORPUS_LANGS = (
    'c', 'cpp', 'csharp', 'go', 'java', 'javascript', 'kotlin', 'lua',
    'php', 'python', 'ruby', 'rust', 'swift', 'typescript')

ANALYZE_TIMEOUT = 120           # 每次 analyze 子进程超时（秒）
MIN_SYMBOLS = 5                 # 断言 d 阈值（保守下限：最小语料 express 冒烟 45）

# xfail 登记：键 (lang, cid) -> '证据编号: 理由'。红灯有产品级证据（file:line）
# 后在此登记；无登记的红灯一律 FAIL，不得静默改断言凑绿。
XFAILS = {}


def _asc(text):
    """任何进 stdout 的字符串先过这里：全 ASCII（GBK 控制台安全）。"""
    return str(text).encode('ascii', 'replace').decode('ascii')


class Checker(object):
    """计数器：passed / failed / xfail / skipped，与主套件 checker 同风格。"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.xfail = 0
        self.skipped = 0
        self.failures = []

    def check(self, ok, lang, cid, detail=''):
        label = '%s/%s' % (lang, cid)
        if ok:
            self.passed += 1
            return
        registered = XFAILS.get((lang, cid))
        if registered is not None:
            self.xfail += 1
            print('[XFAIL] %-24s %s  (%s)' % (label, _asc(detail), registered))
        else:
            self.failed += 1
            self.failures.append(label)
            print('[FAIL] %-24s %s' % (label, _asc(detail)))


def find_repo_root(explicit):
    """定位 analyze_structure.py 所在仓库根：--repo 优先；否则从脚本目录逐级
    向上探测（含 <ancestor>/code2course 兜底，兼容 staging 目录摆放）。"""
    if explicit:
        cand = os.path.abspath(explicit)
        if os.path.isfile(os.path.join(cand, 'analyze_structure.py')):
            return cand
        raise SystemExit('[FAIL] --repo: no analyze_structure.py under %s' % _asc(cand))
    here = os.path.dirname(os.path.abspath(__file__))
    node = here
    for _ in range(6):
        for cand in (node, os.path.join(node, 'code2course')):
            if os.path.isfile(os.path.join(cand, 'analyze_structure.py')):
                return cand
        parent = os.path.dirname(node)
        if parent == node:
            break
        node = parent
    raise SystemExit('[FAIL] cannot locate analyze_structure.py; use --repo')


def make_tmp(tag):
    """唯一临时目录：os.makedirs 建在 gettempdir() 下（mkdtemp 的 0700 DACL
    在 Windows 受限令牌下不可用，禁用）。"""
    path = os.path.join(tempfile.gettempdir(),
                        'b6corpus-%d-%s' % (os.getpid(), tag))
    os.makedirs(path)
    return path


def run_analyze(repo_root, repo_dir, outdir, log_path):
    """跑一次 analyze，stdout+stderr 落日志文件（不经管道），返回 (rc, elapsed_s)。
    超时返回 rc=-999。"""
    cmd = [sys.executable, os.path.join(repo_root, 'analyze_structure.py'),
           'analyze', repo_dir, '--outdir', outdir, '--quiet']
    start = time.time()
    try:
        with open(log_path, 'w', encoding='utf-8', errors='replace') as log:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=ANALYZE_TIMEOUT)
        return proc.returncode, time.time() - start
    except subprocess.TimeoutExpired:
        return -999, time.time() - start


def _facts_bytes(path):
    with open(path, 'rb') as fh:
        return fh.read()


def _discover(corpus_dir, checker):
    """盘上发现语料：返回 {lang: repo_dir}。与钉死清单比对：
    - 清单内语言目录缺失 -> skip（corpus absent）
    - 目录存在但仓库目录数 != 1 -> 布局红灯（0 个记 skip、多个记 fail）
    - 盘上多出清单外的语言目录 -> 打 WARN（以盘上为准的记录义务，不扩范围）"""
    found = {}
    if not os.path.isdir(corpus_dir):
        print('[SKIP] (all): corpus dir absent - run: python tests/corpus/fetch_corpus.py')
        return found
    on_disk = sorted(
        name for name in os.listdir(corpus_dir)
        if os.path.isdir(os.path.join(corpus_dir, name))
        and name != '_smoke' and not name.startswith('__'))
    for name in on_disk:
        if name not in CORPUS_LANGS:
            print('[WARN] unexpected corpus dir not in manifest: %s (ignored)'
                  % _asc(name))
    for lang in CORPUS_LANGS:
        lang_dir = os.path.join(corpus_dir, lang)
        repos = []
        if os.path.isdir(lang_dir):
            repos = sorted(
                name for name in os.listdir(lang_dir)
                if os.path.isdir(os.path.join(lang_dir, name)))
        if len(repos) == 1:
            found[lang] = os.path.join(lang_dir, repos[0])
        elif len(repos) == 0:
            print('[SKIP] %s: corpus absent - run: python tests/corpus/fetch_corpus.py'
                  % lang)
            checker.skipped += 1
        else:
            checker.check(False, lang, 'layout',
                          'expected exactly 1 repo dir, got %d: %s'
                          % (len(repos), ', '.join(repos)))
    return found


def check_repo(checker, repo_root, lang, repo_dir, only_tag):
    """单仓 8 项断言 + 双跑确定性。"""
    out_a = make_tmp('a-' + only_tag)
    out_b = make_tmp('b-' + only_tag)
    log_a = out_a + '.log'
    log_b = out_b + '.log'
    try:
        rc_a, t_a = run_analyze(repo_root, repo_dir, out_a, log_a)
        rc_b, t_b = run_analyze(repo_root, repo_dir, out_b, log_b)

        checker.check(rc_a == 0 and rc_b == 0, lang, 'a',
                      'analyze exit: run1=%d run2=%d (log %s)' % (rc_a, rc_b, log_a))

        facts_a = None
        path_a = os.path.join(out_a, 'structure-facts.json')
        path_b = os.path.join(out_b, 'structure-facts.json')
        if os.path.isfile(path_a):
            try:
                with open(path_a, encoding='utf-8') as fh:
                    facts_a = json.load(fh)
                checker.check(True, lang, 'b',
                              'parsed %d top-level keys'
                              % len(facts_a if isinstance(facts_a, dict) else {}))
            except (OSError, ValueError) as exc:
                checker.check(False, lang, 'b', 'facts json unreadable: %r' % exc)
        else:
            checker.check(False, lang, 'b',
                          'structure-facts.json missing under %s (rc=%d, log %s)'
                          % (out_a, rc_a, log_a))

        # cv / ev / d / e / f 依赖 facts 解析；b 红时按不可得记失败并说明
        if facts_a is None:
            for cid in ('cv', 'ev', 'd', 'e', 'f'):
                checker.check(False, lang, cid, 'facts unavailable (b failed)')
        else:
            checker.check(facts_a.get('schema_version') == EXP_SCHEMA_VERSION,
                          lang, 'cv', 'schema_version=%r expected %d'
                          % (facts_a.get('schema_version'), EXP_SCHEMA_VERSION))
            checker.check(facts_a.get('engine_version') == EXP_ENGINE_VERSION,
                          lang, 'ev', 'engine_version=%r expected %d'
                          % (facts_a.get('engine_version'), EXP_ENGINE_VERSION))
            symbols = facts_a.get('symbols') or []
            checker.check(len(symbols) >= MIN_SYMBOLS, lang, 'd',
                          'symbols=%d expected >= %d' % (len(symbols), MIN_SYMBOLS))

            files = facts_a.get('files') or []
            flang = dict((rec.get('path'), rec.get('language')) for rec in files)
            prim_syms = sum(1 for sym in symbols
                            if flang.get(sym.get('file')) == lang)
            langs_hit = facts_a.get('languages') or []
            checker.check(lang in langs_hit and prim_syms >= 1, lang, 'e',
                          'primary lang in facts.languages=%s, primary symbols=%d'
                          % (langs_hit, prim_syms))

            bad = sorted(set(
                rec.get('language') for rec in files
                if rec.get('language') is not None
                and rec.get('language') not in LANG_CLOSED_SET))
            n_none = sum(1 for rec in files if rec.get('language') is None)
            prim_files = sum(1 for rec in files
                             if rec.get('language') == lang)
            checker.check(
                bool(files) and not bad and prim_files >= 1, lang, 'f',
                'files=%d none_lang=%d primary_files=%d bad_lang=%s '
                '(None=unsupported ext per analyze_structure.py:2284-2291)'
                % (len(files), n_none, prim_files, bad))

        # g：确定性逐字节比对（不依赖 facts 解析成功）
        if os.path.isfile(path_a) and os.path.isfile(path_b):
            data_a = _facts_bytes(path_a)
            data_b = _facts_bytes(path_b)
            checker.check(data_a == data_b, lang, 'g',
                          'byte mismatch: run1=%d bytes run2=%d bytes'
                          % (len(data_a), len(data_b)))
            size_a = size_b = len(data_a) if data_a == data_b else -1
        else:
            checker.check(False, lang, 'g',
                          'facts file missing: run1=%s run2=%s'
                          % (os.path.isfile(path_a), os.path.isfile(path_b)))
            size_a = size_b = -1

        print('[RUN ] %-10s %-28s t=%.1f+%.1fs bytes=%s sym=%d'
              % (lang, os.path.basename(repo_dir), t_a, t_b,
                 ('%d' % size_a) if size_a >= 0 else 'n/a',
                 len((facts_a or {}).get('symbols') or [])))
    finally:
        for path in (out_a, out_b):
            shutil.rmtree(path, ignore_errors=True)
        for path in (log_a, log_b):
            try:
                os.remove(path)
            except OSError:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description='corpus test layer (staging)')
    parser.add_argument('--require-corpus', action='store_true',
                        help='treat corpus-absent skip as failure')
    parser.add_argument('--only', default='',
                        help='comma-separated language dirs to run (smoke)')
    parser.add_argument('--repo', default='',
                        help='repo root containing analyze_structure.py')
    args = parser.parse_args(argv)

    repo_root = find_repo_root(args.repo)
    corpus_dir = os.path.join(repo_root, 'tests', 'corpus')
    checker = Checker()

    print('repo_root: %s' % _asc(repo_root))
    print('corpus:    %s' % _asc(corpus_dir))
    print('contract:  schema_version=%d engine_version=%d langs=%d timeout=%ds'
          % (EXP_SCHEMA_VERSION, EXP_ENGINE_VERSION, len(LANG_CLOSED_SET),
             ANALYZE_TIMEOUT))
    print('')

    started = time.time()
    found = _discover(corpus_dir, checker)
    only = set(s.strip() for s in args.only.split(',') if s.strip())
    for lang in CORPUS_LANGS:
        if only and lang not in only:
            continue
        repo_dir = found.get(lang)
        if repo_dir is None:
            if lang not in found and not os.path.isdir(
                    os.path.join(corpus_dir, lang)):
                # _discover 已记 skip；--require-corpus 时升级
                if args.require_corpus:
                    checker.skipped -= 1
                    checker.check(False, lang, 'corpus',
                                  'corpus absent (--require-corpus) - run: '
                                  'python tests/corpus/fetch_corpus.py')
            continue
        if only:
            print('[SMOKE] only=%s' % ','.join(sorted(only)))
        check_repo(checker, repo_root, lang, repo_dir,
                   only_tag='-'.join(sorted(only)) or 'full')

    elapsed = time.time() - started
    print('')
    print('xfail: %d' % checker.xfail)
    print('total time: %.1fs' % elapsed)
    print('corpus: %d passed / %d failed / %d skipped'
          % (checker.passed, checker.failed, checker.skipped))
    return 0 if checker.failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
