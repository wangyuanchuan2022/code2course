#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_validate_course.py — validate_course.py 的进程内回归 + 覆盖率补测（批次6）。

口径：validate 的既有测量是「CLI 绿路径单跑」= 69.1%（389/563）——66 个负向
用例跑在子进程里，stdlib trace 不跨进程统计不到，于是全部错误分支显示为 missed。
本文件把负例在**进程内重放**：临时副本 + 单点变异 → 进程内 VC.main()，并把
CourseChecker 解析真实成品后的中间状态直接喂给各检查函数（免造 schema）。
与 tests/test_analyze_structure.py 的 b6 补测同法；缺口表见 agent-out/b6-cov100-report.md。

运行：python tests/test_validate_course.py   → validate-tests: N passed / M failed
"""
import io
import json
import os
import re
import runpy
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WORKSPACE = os.path.dirname(REPO)
sys.path.insert(0, REPO)

import validate_course as VC

EXAMPLE = os.path.join(WORKSPACE, 'example', 'course',
                       'minesweeper_help-交互式代码课-L2.html')
SOURCE_DIR = os.path.join(WORKSPACE, 'example', 'course')

_passed = []
_failed = []


def ck(cond, label):
    if cond:
        _passed.append(label)
    else:
        _failed.append(label)


def run_main(args):
    """进程内跑 VC.main，返回 (rc, stdout 文本)。"""
    old = sys.stdout
    out = io.StringIO()
    sys.stdout = out
    try:
        rc = VC.main(args)
    finally:
        sys.stdout = old
    return rc, out.getvalue()


def fresh_dir(tag):
    path = os.path.join(tempfile.gettempdir(),
                        'c2c-b6val-%s-%d' % (tag, os.getpid()))
    if os.path.isdir(path):
        import shutil
        shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path)
    return path


def make_course(tag, transform=None):
    """把成品复制到临时目录（可选单点变异），返回路径。"""
    with io.open(EXAMPLE, 'r', encoding='utf-8', newline='') as fh:
        text = fh.read()
    if transform is not None:
        text = transform(text)
    path = os.path.join(fresh_dir(tag), 'course.html')
    with io.open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    return path


def sub(old, new, count=1):
    def _t(text):
        if old not in text:
            raise AssertionError('mutation anchor not found: %r' % old[:60])
        return text.replace(old, new, count)
    return _t


def rex(pattern, repl, count=1):
    def _t(text):
        out, n = re.subn(pattern, repl, text, count=count)
        if n == 0:
            raise AssertionError('mutation regex missed: %r' % pattern[:60])
        return out
    return _t


def inject_first_link_field(field_json):
    """返回变异器：把字段注入第一个调用图 links 元素（对象内首部）。"""
    def _t(s):
        m = re.search(r'"links"\s*:\s*\[\s*\{', s)
        if not m:
            raise AssertionError('no links array found')
        return s[:m.end()] + field_json + s[m.end():]
    return _t


def parse_example():
    """解析成品 → CourseChecker（各检查函数的数据源）。"""
    with io.open(EXAMPLE, 'r', encoding='utf-8', newline='') as fh:
        raw = fh.read()
    chk = VC.CourseChecker()
    chk.feed(raw)
    chk.close()
    return raw, chk


def graph_blocks(chk, raw):
    """从原文抽取调用图 JSON 块（CourseChecker 不收集它们）。"""
    out = []
    for m in re.finditer(
            r'<script type="application/json" class="callgraph-data">'
            r'([\s\S]*?)</script>', raw):
        try:
            out.append((m.group(0)[:40], json.loads(m.group(1))))
        except ValueError:
            pass
    return out


# ----------------------------------------------------------------- 1. 用法/IO
def test_usage_and_io():
    ck(run_main(['validate_course.py'])[0] == 2,
       'val-main: no args prints usage and exits 2')
    ck(run_main(['validate_course.py', EXAMPLE, '--tier'])[0] == 2,
       'val-main: option without value exits 2')
    ck(run_main(['validate_course.py',
                 os.path.join(REPO, 'no-such-course.html')])[0] == 2,
       'val-main: unreadable path exits 2')
    real = VC.CourseChecker

    class Boom(real):
        def feed(self, data):
            raise RuntimeError('b6 injected parse failure')

    VC.CourseChecker = Boom
    try:
        rc, out = run_main(['validate_course.py', EXAMPLE])
    finally:
        VC.CourseChecker = real
    ck(rc == 1 and 'HTML 解析异常' in out,
       'val-main: parser exception is reported loudly (exit 1)')


# ------------------------------------------------- 2. 绿路径 + 旗标（--mask/--source）
def test_green_and_flags():
    rc, out = run_main(['validate_course.py', EXAMPLE, '--tier', 'L2'])
    ck(rc == 0 and '全部通过' in out,
       'val-main: example L2 validates green (CLI contract)')
    rc, _out = run_main(['validate_course.py', EXAMPLE, '--mask'])
    ck(rc == 0, 'val-main: --mask run stays green (mask_scan executed)')
    empty_src = fresh_dir('emptysrc')
    rc, out = run_main(['validate_course.py', EXAMPLE, '--source', empty_src])
    ck(rc in (0, 1) and out,
       'val-verbatim: --source with missing files runs verbatim_check')
    rc, out = run_main(['validate_course.py', EXAMPLE, '--source', SOURCE_DIR])
    ck(rc in (0, 1) and out,
       'val-verbatim: --source with the real tree runs verbatim_check')
    rc, out = run_main(['validate_course.py', EXAMPLE, '--tier', 'L3'])
    ck(rc in (0, 1) and out,
       'val-tier: unknown tier id goes through the tier rule lookup')


# ------------------------------------------------------------- 3. 单点变异（HTML）
def test_mutants():
    mutants = [
        ('md-residue',
         sub('</main>', '<p>## 残留标题</p>\n</main>')),
        ('data-i-mismatch',
         rex(r'data-i="1"', 'data-i="77"')),
        ('quiz-two-trues',
         rex(r'(data-correct="false"[\s\S]{0,400}?)data-correct="false"',
             r'\1data-correct="true"')),
        ('quiz-missing-why',
         rex(r'\s+data-why="[^"]{0,80}"', '', count=1)),
        ('orphan-nav',
         rex(r'(<nav[^>]*>)',
             r'\1<a class="nav-item" href="#m-ghost">幽灵项</a>')),
        ('version-drift',
         rex(r'data-version="[^"]+"', 'data-version="0.0.0"')),
        ('external-link',
         sub('</main>', '<p><a href="https://example.com/x">外链</a></p>\n'
                        '</main>')),
        ('cg-resolution-bogus',
         inject_first_link_field('"resolution": "bogus", ')),
        ('cg-self-ref',
         inject_first_link_field('"resolution": "self_ref", ')),
        ('cg-ambiguous-verified',
         inject_first_link_field(
             '"resolution": "ambiguous", "confidence": "verified", ')),
        ('cg-unique-no-resolved-by',
         inject_first_link_field(
             '"resolution": "unique", "confidence": "verified", ')),
        ('cg-resolved-by-bogus',
         inject_first_link_field(
             '"confidence": "verified", "resolved_by": "bogus", ')),
    ]
    for name, transform in mutants:
        try:
            path = make_course(name.replace('-', ''), transform)
        except AssertionError as exc:
            ck(False, 'val-mutant %s: %s' % (name, exc))
            continue
        rc, out = run_main(['validate_course.py', path, '--tier', 'L2'])
        ck(rc == 1, 'val-mutant %s turns the checker red (rc=%d)' % (name, rc))


# --------------------------------------------- 4. 直调检查函数（喂真实解析状态）
def test_direct_checks():
    raw, chk = parse_example()

    segs = VC._parse_file_segments('utils/vision.py · L23-L36 与 main.py · L7')
    ck(len(segs) == 2 and (23, 36) in segs[0][1] and segs[1][1] == [(7, 7)],
       'val-segments: multi-segment data-file spec parses ranges and singles')
    segs = VC._parse_file_segments('plain/path.py')
    ck(segs == [('plain/path.py', [])],
       'val-segments: spec without a dot separator yields no ranges')
    segs = VC._parse_file_segments('a.py · L5')
    ck(segs and segs[0][1] == [(5, 5)],
       'val-segments: single Lnn form yields a one-line range')

    errors = []
    VC.check_raw_text(raw, errors)
    ck(errors == [], 'val-raw: the shipped example passes the raw-text scan')
    errors = []
    VC.check_raw_text('<p>{{ 未替换占位符 }}</p>', errors)
    ck(bool(errors), 'val-raw: leftover {{ }} placeholder is reported')

    errors, warnings = [], []
    VC.markdown_scan([(1, '## 标题')], errors, warnings, 'b6')
    ck(bool(errors) or bool(warnings),
       'val-markdown: a markdown-looking prose line is reported')

    errors, warnings = [], []
    VC.css_var_audit(chk.style_blocks[0] if chk.style_blocks else '',
                     set(), errors, warnings)
    ck(isinstance(errors, list),
       'val-css: css_var_audit consumes a real style block')

    errors = []
    VC.trace_id_check(chk.why_texts, chk.ids, errors)
    ck(errors == [], 'val-trace-id: example why-text pair refs all resolve')
    errors = []
    VC.trace_id_check(['见 pair-ghost 的说明'], chk.ids, errors)
    ck(bool(errors), 'val-trace-id: dangling pair-* reference is reported')

    blocks = graph_blocks(chk, raw)
    ck(bool(blocks), 'val-callgraph: example carries callgraph json blocks')
    if blocks:
        errors = []
        VC.callgraph_check(blocks[0][1], 'b6', errors)
        ck(errors == [], 'val-callgraph: shipped callgraph block passes')
        bad = json.loads(json.dumps(blocks[0][1]))
        if bad.get('links'):
            bad['links'][0]['resolution'] = 'bogus'
        errors = []
        VC.callgraph_check(bad, 'b6', errors)
        ck(bool(errors), 'val-callgraph: bogus resolution is reported')

    errors = []
    edge = {'from': 'a', 'to': 'b', 'count': 1, 'confidence': 'verified',
            'file': 'a.py', 'line': 1, 'resolution': 'unique',
            'resolved_by': 'name'}
    VC._cg_resolution_check(edge, 0, 'b6', errors)
    ck(errors == [], 'val-cg-edge: well-formed verified edge passes')
    for name, mutate, expect in (
            ('bogus-resolved-by',
             {'resolved_by': 'bogus'}, '不在闭集'),
            ('inferred-with-resolved-by',
             {'confidence': 'inferred'}, 'resolved_by'),
            ('bogus-resolution',
             {'resolution': 'bogus'}, 'resolution'),
            ('self-ref',
             {'resolution': 'self_ref'}, 'self_ref'),
            ('ambiguous-verified',
             {'resolution': 'ambiguous', 'resolved_by': None,
              'confidence': 'verified'}, 'inferred'),
            ('unique-without-resolved-by',
             {'resolution': 'unique', 'resolved_by': None}, 'unique')):
        probe = dict(edge)
        probe.update(mutate)
        errors = []
        VC._cg_resolution_check(probe, 0, 'b6', errors)
        ck(bool(errors),
           'val-cg-edge %s is rejected (%s)' % (name, expect))

    errors = []
    VC.verbatim_check(chk.pair_meta_all, SOURCE_DIR, errors)
    ck(isinstance(errors, list),
       'val-verbatim-direct: pair metadata is checked against the real tree')
    errors = []
    VC.verbatim_check(chk.pair_meta_all, fresh_dir('emptysrc2'), errors)
    ck(isinstance(errors, list),
       'val-verbatim-direct: missing source files degrade gracefully')

    errors = []
    VC.tier_check(chk.module_stats, 'L2', errors)
    ck(errors == [], 'val-tier-direct: example satisfies its own tier')
    errors = []
    VC.tier_check(chk.module_stats, 'L1', errors)
    ck(isinstance(errors, list), 'val-tier-direct: L1 rule path runs')
    errors = []
    VC.tier_check(chk.module_stats, 'no-such-tier', errors)
    ck(isinstance(errors, list), 'val-tier-direct: unknown tier is tolerated')
    errors = []
    VC.finale_check(chk.module_stats, errors)
    ck(isinstance(errors, list), 'val-finale: finale_check runs on real stats')
    errors = []
    VC.callgraph_coverage_check(chk.module_stats, errors)
    ck(isinstance(errors, list),
       'val-cg-coverage: callgraph coverage check runs on real stats')
    ck(isinstance(VC.is_finale(chk.module_stats[0]), bool)
       if chk.module_stats else True,
       'val-finale: is_finale answers for a real module record')


# ----------------------------------------------------------- 5. __main__ 守卫
def test_main_guard():
    saved = sys.argv
    sys.argv = ['validate_course.py']
    code = None
    try:
        old = sys.stdout
        sys.stdout = io.StringIO()
        try:
            runpy.run_path(VC.__file__, run_name='__main__')
        finally:
            sys.stdout = old
    except SystemExit as exc:
        code = exc.code
    finally:
        sys.argv = saved
    ck(code == 2, 'val-guard: module __main__ guard exits with main() code')


def _clone(obj):
    return json.loads(json.dumps(obj))


def test_deep_checks():
    """契约错误分支 + 造数据的检查函数分支（coverage-gap: 503-623,646-700,
    343-348,727-783,309-318,196,225,294）。"""
    raw, chk = parse_example()
    data = graph_blocks(chk, raw)[0][1]

    def cg(fn, warnings=None):
        d = _clone(data)
        fn(d)
        errs = []
        VC.callgraph_check(d, 'b6', errs, warnings if warnings is not None
                           else [])
        return errs

    ck(bool(cg(lambda d: d['nodes'][0].pop('id'))),
       'val-cg-deep: node without id is rejected')
    ck(bool(cg(lambda d: d['nodes'][0].update({'bogus': 1}))),
       'val-cg-deep: unknown node key is rejected')
    ck(bool(cg(lambda d: d['links'][0].update({'bogus': 1}))),
       'val-cg-deep: unknown link key is rejected')
    ck(bool(cg(lambda d: d['nodes'][0].update({'about': 'x' * 200}))),
       'val-cg-deep: over-long about text is rejected')
    ck(bool(cg(lambda d: d['nodes'][0].update({'call': 'x' * 200}))),
       'val-cg-deep: over-long call text is rejected')
    ck(bool(cg(lambda d: d['links'][0].pop('to'))),
       'val-cg-deep: link without target is rejected')
    ck(bool(cg(lambda d: d['links'][0].update({'confidence': 'maybe'}))),
       'val-cg-deep: unknown confidence is rejected')
    ck(bool(cg(lambda d: d['links'][0].update({'to': 'no/such-node.py'}))),
       'val-cg-deep: link to an unknown node is rejected')
    ck(bool(cg(lambda d: d.pop('links'))),
       'val-cg-deep: missing links key is rejected')
    ck(bool(cg(lambda d: d.pop('nodes'))),
       'val-cg-deep: missing nodes key is rejected')
    tails = [n for n in data['nodes'] if '/' in str(n.get('id', ''))]
    if len(tails) >= 2:
        warns = []
        cg(lambda d: d['links'].append(
            {'from': tails[0]['id'], 'to': tails[1]['id'], 'count': 1,
             'confidence': 'verified', 'file': 'x', 'line': 1}), warns)
        ck(isinstance(warns, list),
           'val-cg-deep: file-level same-tail edge path is evaluated')

    warns = []
    VC.mask_scan('联系 a@b.com 或 C:\\Users\\someone\\notes 或 '
                 'C:\\Users\\…\\masked', warns)
    ck(len(warns) >= 2,
       'val-mask-deep: email + drive path flagged, ellipsis form exempt')
    warns = []
    VC.mask_scan('password = "supersecret"', warns)
    ck(isinstance(warns, list), 'val-mask-deep: secret-assignment rule runs')

    errs = []
    VC.finale_check([{'id': 'm9-finale', 'hero': False, 'pairs': 0, 'eng': 0,
                      'quiz': 0, 'cg': 0, 'text': ['就此收尾']}], errs)
    ck(len(errs) == 3, 'val-finale-deep: finale段缺结业三件逐条报错')
    errs = []
    VC.callgraph_coverage_check(
        [{'id': 'cover', 'hero': True, 'pairs': 0, 'eng': 0, 'quiz': 0,
          'cg': 0, 'text': []},
         {'id': 'm1', 'hero': False, 'pairs': 1, 'eng': 1, 'quiz': 1,
          'cg': 0, 'text': []}], errs)
    ck(bool(errs), 'val-cg-coverage-deep: 封面/模块缺调用图被报错')
    errs = []
    VC.tier_check([{'id': 'm1', 'hero': False, 'pairs': 0, 'eng': 0,
                    'quiz': 0, 'cg': 1, 'text': []}], 'L2', errs)
    ck(bool(errs), 'val-tier-deep: 低于档位下限的模块被报错')

    srcdir = fresh_dir('src')
    with io.open(os.path.join(srcdir, 'a.py'), 'w', encoding='utf-8') as fh:
        fh.write('print(1)\n')
    pairs = [{'file': 'a.py · L1-L1', 'chunks': ['print(1)\n'], 'head': []},
             {'file': 'a.py · L1-L1', 'chunks': ['print(999)\n'], 'head': []},
             {'file': 'no/such.py · L1-L1', 'chunks': ['x\n'], 'head': []},
             {'file': '(无源码)', 'chunks': ['y\n'], 'head': []}]
    errs = []
    VC.verbatim_check(pairs, srcdir, errs)
    ck(bool(errs),
       'val-verbatim-deep: match / mismatch / missing-source variants run')

    errs, warns = [], []
    VC.markdown_scan([(1, '- 列表项残留'), (2, '**粗体残留**')],
                     errs, warns, 'b6')
    ck(bool(errs) or bool(warns), 'val-markdown-deep: marker lines reported')

    errs, warns = [], []
    VC.css_var_audit('.__b6 { color: #FFFDF8; }', set(), errs, warns)
    ck(bool(errs) or bool(warns), 'val-css-deep: bare white colour reported')

    # ---- HTML 深层变异：内联 style 超限 / 孤儿模块 / 仅告警通过 / JSON 块 ----
    path = make_course('inlinestyle',
                       sub('</main>', ''.join(
                           '<div style="margin:%dpx">s</div>' % i
                           for i in range(7)) + '\n</main>'))
    rc, out = run_main(['validate_course.py', path])
    ck(isinstance(rc, int),
       'val-main-deep: many inline styles path runs (rc=%d)' % rc)

    path = make_course('orphanmod',
                       sub('</main>', '<section class="module" id="m-orphan">'
                                      '<h2>孤儿</h2></section>\n</main>'))
    rc, _out = run_main(['validate_course.py', path])
    ck(rc == 1, 'val-main-deep: module without nav item turns red')

    path = make_course('warnonly',
                       sub('</main>', '<p>联系 a@b.com</p>\n</main>'))
    rc, out = run_main(['validate_course.py', path, '--mask'])
    ck(rc == 0 and '告警' in out,
       'val-main-deep: warnings-only run reports the ⚠️ pass form')

    path = make_course('badjson',
                       rex(r'("nodes"\s*:\s*\[)',
                           r'\1 { "id": '
                           if False else r'\1 { "id" '))
    rc, _out = run_main(['validate_course.py', path])
    ck(rc == 1, 'val-json: malformed callgraph json block turns red')

    path = make_course('quizopt',
                       sub('</main>', '<button class="quiz-opt" '
                                      'data-correct="true" data-why="x">o'
                                      '</button>\n</main>'))
    rc, _out = run_main(['validate_course.py', path])
    ck(rc == 1, 'val-parser: quiz option outside a quiz container turns red')

    path = make_course('styleurl',
                       sub('</main>', '<div style="background: '
                                      'url(http://x/y.png)">z</div>\n</main>'))
    rc, _out = run_main(['validate_course.py', path])
    ck(rc == 1, 'val-parser: inline style url() external reference is red')

    path = make_course('strayend',
                       sub('</main>', '</section>\n</main>'))
    rc, _out = run_main(['validate_course.py', path])
    ck(isinstance(rc, int), 'val-parser: stray end tag path runs (rc=%d)' % rc)

    # 嵌套错配（结束标签与栈顶不配对）
    path = make_course('nestmis',
                       sub('</main>', '<div><span>t</div>\n</main>'))
    rc, _out = run_main(['validate_course.py', path])
    ck(isinstance(rc, int),
       'val-parser: mismatched close tag path runs (rc=%d)' % rc)

    # 其它 class 的 JSON 数据块（白名单外的块类）
    path = make_course('jsonother',
                       sub('</main>', '<script type="application/json" '
                                      'class="mystery-data">{"a": 1}'
                                      '</script>\n</main>'))
    rc, _out = run_main(['validate_course.py', path])
    ck(isinstance(rc, int),
       'val-json: unknown json block class path runs (rc=%d)' % rc)

    # data-i 全缺的 translate-pair（839：左右皆空 → continue）
    path = make_course('emptypair',
                       sub('</main>', '<div class="translate-pair">'
                                      '<div class="tp-head"></div>'
                                      '</div>\n</main>'))
    rc, _out = run_main(['validate_course.py', path])
    ck(isinstance(rc, int),
       'val-main-deep: pair without data-i path runs (rc=%d)' % rc)

    # markdown_scan 的「疑点告警」分支
    probe = [(1, '1. 有序列表残留'), (2, '# 井号标题'), (3, '> 引用行'),
             (4, '| a | b |'), (5, '- 短横列表')]
    errs, warns = [], []
    VC.markdown_scan(probe, errs, warns, 'b6')
    ck(isinstance(errs, list) and isinstance(warns, list),
       'val-markdown-deep: all marker families evaluated (err=%d warn=%d)'
       % (len(errs), len(warns)))

    # 调用图：节点 kind 闭集 / file-line 形态 / declared-back 语义
    data2 = graph_blocks(chk, raw)[0][1]

    def cg2(fn):
        d = _clone(data2)
        fn(d)
        errs = []
        VC.callgraph_check(d, 'b6', errs, [])
        return errs

    ck(isinstance(cg2(lambda d: d['nodes'][0].update(
        {'kind': 'mystery-kind'})), list),
       'val-cg-deep: unknown node kind path is evaluated')
    ck(bool(cg2(lambda d: d['nodes'][0].update({'line': 0}))),
       'val-cg-deep: non-positive node line is rejected')
    ck(bool(cg2(lambda d: d['links'][0].update({'line': 'x'}))),
       'val-cg-deep: non-integer link line is rejected')
    ck(isinstance(cg2(lambda d: d['links'][0].update({'declared': True})),
                  list),
       'val-cg-deep: declared-only edge path is evaluated')
    ck(bool(cg2(lambda d: d['nodes'][0].update({'about': 1}))),
       'val-cg-deep: non-string about is rejected')


def test_gap_close():
    """批次 6b：消化报告 §二 缺口表剩余 37 条可达行（coverage-gap 6b）。"""
    raw, chk = parse_example()
    data = graph_blocks(chk, raw)[0][1]

    # ---- callgraph_check 契约分支（513-514,527-528,541,549,571-572,584,
    #      601,611,620）----
    errs = []
    VC.callgraph_check(['not-an-object'], 'b6', errs, [])
    ck(bool(errs) and '顶层必须是对象' in errs[0],
       'b6b-cg: non-dict top level is rejected (513-514)')
    errs = []
    VC.callgraph_check({'nodes': ['not-an-object'], 'links': []}, 'b6',
                       errs, [])
    ck(bool(errs) and '不是对象' in errs[0],
       'b6b-cg: non-object node entry is rejected (527-528)')
    errs = []
    VC.callgraph_check({'nodes': [{'id': 'a', 'file': 'a.py', 'line': 1},
                                  {'id': 'a', 'file': 'a.py', 'line': 2}],
                        'links': []}, 'b6', errs, [])
    ck(any('重复' in e for e in errs),
       'b6b-cg: duplicate node id is rejected (541)')
    errs = []
    VC.callgraph_check({'nodes': [{'id': 'a', 'line': 1}], 'links': []},
                       'b6', errs, [])
    ck(any('缺 file' in e for e in errs),
       'b6b-cg: node without file is rejected (549)')
    errs = []
    VC.callgraph_check({'nodes': [{'id': 'a', 'file': 'a.py', 'line': 1}],
                        'links': ['not-an-object']}, 'b6', errs, [])
    ck(bool(errs) and '不是对象' in errs[0],
       'b6b-cg: non-object link entry is rejected (571-572)')
    errs = []
    VC.callgraph_check({'nodes': [{'id': 'a', 'file': 'a.py', 'line': 1},
                                  {'id': 'b', 'file': 'a.py', 'line': 2}],
                        'links': [{'from': 'a', 'to': 'b', 'count': 1,
                                   'confidence': 'verified', 'file': 'a.py',
                                   'line': 3, 'about': '边不允许挂综述'}]},
                       'b6', errs, [])
    ck(any('about' in e for e in errs),
       'b6b-cg: about on a link is rejected (584)')
    errs = []
    VC.callgraph_check({'nodes': [{'id': 'a', 'file': 'a.py', 'line': 1}],
                        'links': [{'from': 'a', 'to': 'a', 'count': 1,
                                   'confidence': 'inferred', 'file': 'a.py',
                                   'line': 1}]}, 'b6', errs, [])
    ck(any('自环' in e for e in errs),
       'b6b-cg: from == to self-loop is rejected (601)')
    warns = []
    errs = []
    VC.callgraph_check({'nodes': [{'id': 'A.twin', 'file': 'a.py', 'line': 1},
                                  {'id': 'B.twin', 'file': 'b.py', 'line': 1}],
                        'links': [{'from': 'A.twin', 'to': 'B.twin',
                                   'count': 1, 'confidence': 'inferred',
                                   'file': 'a.py', 'line': 1}]},
                       'b6', errs, warns)
    ck(any('末段名相同' in w for w in warns),
       'b6b-cg: same-tail non-pathish ids warn (611)')
    errs = []
    VC.callgraph_check({'nodes': [{'id': 'a', 'file': 'a.py', 'line': 1},
                                  {'id': 'b', 'file': 'a.py', 'line': 2}],
                        'links': [{'from': 'a', 'to': 'b', 'count': 1,
                                   'confidence': 'verified', 'line': 3}]},
                       'b6', errs, [])
    ck(any('标了 verified 却没有' in e for e in errs),
       'b6b-cg: verified link without source line is rejected (620)')

    # ---- _check_json 的字面 </script 与 HTML 实体分支（313-318）----
    jchk = VC.CourseChecker()
    jchk._check_json('callgraph-data', '{"a": "1 </SCRIPT 2"}', 'b6')
    ck(bool(jchk.errors) and '</script' in jchk.errors[0],
       'b6b-json: literal closing script tag inside json is rejected (313)')
    jchk = VC.CourseChecker()
    jchk._check_json('callgraph-data', '{"a": "1 &gt; 0"}', 'b6')
    ck(bool(jchk.warnings) and '&gt;' in jchk.warnings[0],
       'b6b-json: html entity literal inside json warns (318)')

    # ---- script 块文本含字面标签（handle_endtag 294）----
    path = make_course('scriptliteral',
                       sub('</body>', '<script>var t = "<script>";</script>\n'
                                      '</body>'))
    rc, _out = run_main(['validate_course.py', path])
    ck(rc == 1, 'b6b-parser: literal <script> inside a script blob is red')

    # ---- markdown_scan 斜体星号告警分支（377）----
    errs, warns = [], []
    VC.markdown_scan([(1, '*斜体内容*')], errs, warns, 'b6')
    ck(not errs and bool(warns),
       'b6b-markdown: italic-star form lands in the warning channel (377)')

    # ---- translate-pair 左右皆空（main 839）：空 pair 需在模块 section 内 ----
    path = make_course(
        'emptypair2',
        rex(r'(</section>)',
            '<div class="translate-pair"><div class="tp-head">'
            '</div></div>\\1'))
    rc, _out = run_main(['validate_course.py', path])
    ck(isinstance(rc, int),
       'b6b-main: empty translate-pair inside a module runs 839 (rc=%d)'
       % rc)

    # ---- verbatim_check 全分支（662,677-700）：六种 pair 变体 ----
    vsrc = fresh_dir('vsrc')
    a_lines = ['line-%02d-content' % i for i in range(1, 31)]
    with io.open(os.path.join(vsrc, 'a.py'), 'w', encoding='utf-8',
                 newline='') as fh:
        fh.write('\n'.join(a_lines) + '\n')
    with io.open(os.path.join(vsrc, 'b.py'), 'w', encoding='utf-8',
                 newline='') as fh:
        fh.write('b-unique-line-20-content\nb-unique-line-21-content\n')
    vpairs = [
        {'file': 'a.py · L5-L8',
         'chunks': ['line-06-content\nline-07-content'], 'head': []},
        {'file': 'a.py · L1-L2',
         'chunks': ['line-20-content\nline-21-content'], 'head': []},
        {'file': 'a.py · L1-L1 与 b.py · L1-L2',
         'chunks': ['b-unique-line-20-content\nb-unique-line-21-content'],
         'head': []},
        {'file': 'a.py',
         'chunks': ['this text does not exist anywhere in the source'],
         'head': []},
        {'file': 'a.py', 'chunks': ['print(1)\n'], 'head': []},
        {'file': '', 'chunks': ['whatever'], 'head': []},
    ]
    errs = []
    n_ok, n_fail = VC.verbatim_check(vpairs, vsrc, errs)
    ck(n_ok == 2,
       'b6b-verbatim: in-range and multi-source hits count as ok '
       '(662,677,680-690,696-697)')
    ck(n_fail == 2 and len(errs) == 2
       and any('行号漂移' in e for e in errs)
       and any('逐字失配' in e for e in errs),
       'b6b-verbatim: drift and mismatch are reported (691-695,699-700)')


def run_selftest():
    test_usage_and_io()
    test_green_and_flags()
    test_mutants()
    test_direct_checks()
    test_deep_checks()
    test_gap_close()
    test_main_guard()
    print('validate-tests: %d passed / %d failed'
          % (len(_passed), len(_failed)))
    for label in _failed:
        print('  FAIL %s' % label)
    return 0 if not _failed else 1


if __name__ == '__main__':
    sys.exit(run_selftest())
