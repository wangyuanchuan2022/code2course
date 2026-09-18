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


def make_course(tag, transform=None, inject=True):
    """把成品（默认含骨架注入，见文件末「骨架注入」节）复制到临时目录
    （可选单点变异），返回路径。"""
    text = example_text(inject)
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
    """返回变异器：把字段注入第一个**调用图**数据块的 links 首元素。

    锚点必须带 callgraph-data 类名——骨架注入后文档里还有 .arch-data 块，
    它也带 links[]，只认第一个 "links": [ 会把字段注进不跑调用图契约的块。
    """
    def _t(s):
        m = re.search(r'class="callgraph-data">[\s\S]*?"links"\s*:\s*\[\s*\{', s)
        if not m:
            raise AssertionError('no callgraph links array found')
        return s[:m.end()] + field_json + s[m.end():]
    return _t


def example_text(inject=True):
    """读盘上 example；inject=True 时先做骨架注入（默认）。

    盘上 example 是 v1.17.0 前的旧成品，不含 v1.18.0 理解骨架六件——检查 19-23
    会判它红（取证见 test_example_conflict）。本套件的既定断言语义是「合规课程
    在单点变异下变红」，故默认在**副本 + 机械骨架注入**上跑：原有 18 项断言语义
    一字不变，同时顺带证明「既有 18 项在新组件在场时仍绿」。
    """
    with io.open(EXAMPLE, 'r', encoding='utf-8', newline='') as fh:
        text = fh.read()
    return inject_skeleton(text) if inject else text


def parse_example(inject=True):
    """解析成品（默认已注入骨架）→ CourseChecker（各检查函数的数据源）。"""
    chk = VC.CourseChecker()
    raw = example_text(inject)
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


def arch_block(raw):
    """抽取 .arch-data JSON（骨架注入产物内；契约 §一.1 第六类数据块）。"""
    m = re.search(r'<script type="application/json" class="arch-data">'
                  r'([\s\S]*?)</script>', raw)
    if not m:
        raise AssertionError('no .arch-data block')
    return json.loads(m.group(1))


def arch_json_transform(fn):
    """返回变异器：解析 .arch-data → fn(data) → 回写（结构类变异用）。

    比正则切片稳：JSON 内部缩进/换行由 json.dumps 重排，锚点不依赖字面量。
    """
    def _t(text):
        def _repl(m):
            data = json.loads(m.group(1))
            fn(data)
            return ('<script type="application/json" class="arch-data">\n'
                    + json.dumps(data, ensure_ascii=False, indent=2)
                    + '\n</script>')
        out, n = re.subn(r'<script type="application/json" '
                         r'class="arch-data">([\s\S]*?)</script>', _repl, text,
                         count=1)
        if not n:
            raise AssertionError('no .arch-data block to mutate')
        return out
    return _t


# ------------------------------------------- 骨架注入（v1.18.0 契约 §一 组件结构）
# 盘上 example 是 v1.17.0 前的旧成品（无理解骨架六件），v1.18.0 检查 19-23 判它
# 红（取证见 test_example_conflict）。注入是**机械**的：.arch-data 由 example 的
# 封面调用图 JSON 派生（nodes/links 原样 + module_marks），其余五件按契约 §一 的
# 类名与数据属性拼装。注入只新增组件、不改既有元素，故原有 18 项断言语义不变。
# 逐件判定「盘上已有则跳过」——example 日后被课程重做会话重建为 v1.18.0 合规
# 成品时，注入自动退化为补齐缺件（不重复注入），本套件仍可跑。
SKEL_DESIGN_BLOCKS = 3      # 每正式模块注入的设计四问块数（同时满足 L3 下限）
SKEL_UG_ROWS = 6            # 结业段改造指南条目数（L2/L3 下限 6）
SKEL_RC_STEPS = 5           # 封面运行链步数（>4 下限，留出「减到 3 步」变异余量）


def _arch_json_from_cover(text):
    """把封面调用图 JSON 派生成 .arch-data（契约 §一.1：nodes/links + module_marks）。"""
    m = re.search(r'<script type="application/json" class="callgraph-data">'
                  r'([\s\S]*?)</script>', text)
    if not m:
        raise AssertionError('封面调用图块不存在，无法派生 .arch-data')
    data = json.loads(m.group(1))
    marks = [{'id': 'm%d' % (i + 1), 'label': '模块 %d' % (i + 1),
              'covers': [n['id']]}
             for i, n in enumerate(data.get('nodes', [])[:3])]
    return json.dumps({'nodes': data.get('nodes', []),
                       'links': data.get('links', []),
                       'module_marks': marks},
                      ensure_ascii=False, indent=2)


def _arch_scene_html(arch_json):
    return ('<div class="arch-scene scene">\n'
            '<div class="arch-title t-h3">仓库总架构</div>\n'
            '<p class="t-body">这张图回答整个程序由哪些部分组成、谁依赖谁，'
            '以及每个模块在整条链路上的位置。</p>\n'
            '<script type="application/json" class="arch-data">\n'
            + arch_json + '\n</script>\n'
            '<div class="arch-stage" role="group" aria-label="仓库总架构">'
            '</div>\n'
            '<div class="arch-facts t-muted" aria-live="polite">点节点看依赖'
            '</div>\n</div>\n')


def _run_chain_html():
    steps = [('用户', '双击图标启动程序'),
             ('main.py', '创建主窗口并拉起求解器线程'),
             ('solver.py', '按截图、识别、推理、决策四步循环推进'),
             ('vision.py', '截屏切片并把每格识别成数字或空白'),
             ('ui/window.py', '把这一步的决策画回棋盘')][:SKEL_RC_STEPS]
    items = ['<li class="rc-step" data-step="%d"><span class="rc-obj">%s</span>'
             '<span class="rc-what">%s</span></li>' % (i, obj, what)
             for i, (obj, what) in enumerate(steps, 1)]
    return '<ol class="run-chain">\n' + '\n'.join(items) + '\n</ol>\n'


def _module_card_html():
    rows = [('problem', '解决什么问题', '把这一层要处理的核心矛盾说清楚'),
            ('input', '输入是什么', '具体到数据形态，而不是笼统的用户数据'),
            ('output', '输出是什么', '交给下一层的产物是什么形态'),
            ('segment', '在总架构图上的位置', '对应 module_marks 里覆盖本模块的那一段')]
    body = '\n'.join('<div class="mc-row" data-key="%s">'
                     '<span class="mc-key">%s</span>'
                     '<span class="mc-val">%s</span></div>' % r for r in rows)
    return '<div class="module-card">\n' + body + '\n</div>\n'


def _design_qa_html(idx):
    rows = [('what', '它做什么', '这一层在链路上负责的单一职责'),
            ('why', '为什么这么做', '这样切分的收益与代价'),
            ('else', '不这么做会怎样', '换成另一种写法的后果'),
            ('simpler', '为什么不用更简单的方法', '简单解法在什么条件下会失效')]
    body = '\n'.join('<div class="dq-row" data-q="%s"><dt class="dq-key">%s</dt>'
                     '<dd class="dq-val">%s</dd></div>' % r for r in rows)
    return ('<div class="design-qa">\n'
            '<div class="dq-title t-h3">设计四问 %d</div>\n'
            '<dl class="dq-list">\n' % idx + body + '\n</dl>\n</div>\n')


def _vardict_html():
    rows = [('cell_value', '单格像素样本', '识别阶段产生', 'utils/vision.py · L88'),
            ('clicks', '外围候选格', '分区阶段产生',
             'utils/probability.py · L120')]
    trs = []
    for var, plain, stage, loc in rows:
        trs.append('<tr class="vardict-row" data-var="%s" data-stage="%s">'
                   '<td class="vd-var">%s</td><td class="vd-plain">%s</td>'
                   '<td class="vd-stage">%s</td><td class="vd-loc">%s</td></tr>'
                   % (var, stage, var, plain, stage, loc))
    nodes = []
    for i, var in enumerate([r[0] for r in rows]):
        if i:
            nodes.append('<span class="vc-arrow" aria-hidden="true">→</span>')
        nodes.append('<span class="vc-node" data-var="%s">%s</span>' % (var, var))
    return ('<div class="vardict-scene">\n'
            '<div class="vardict-title t-h3">变量词典</div>\n'
            '<table class="vardict-table">\n'
            '<thead><tr><th>代码变量</th><th>人话</th><th>生命周期</th>'
            '<th>代码位置</th></tr></thead>\n<tbody>\n'
            + '\n'.join(trs) + '\n</tbody>\n</table>\n'
            '<div class="var-chain" aria-label="变量生命周期链">\n'
            + '\n'.join(nodes) + '\n</div>\n</div>\n')


def _upgrade_guide_html():
    rows = [('换扫雷皮肤', 'vision.py · cfg.json'),
            ('提高识别准确率', 'utils/vision.py'),
            ('换一套推理策略', 'utils/deduction.py'),
            ('接入新的求解器', 'utils/solver.py'),
            ('加一个统计面板', 'ui/window.py'),
            ('把启发式换成模型', 'utils/probability.py')][:SKEL_UG_ROWS]
    trs = ['<tr class="ug-row" data-task="%s"><td class="ug-task">%s</td>'
           '<td class="ug-where">%s</td></tr>' % (task, task, where)
           for task, where in rows]
    return ('<table class="upgrade-guide">\n'
            '<thead><tr><th>想做的事</th><th>去哪儿改</th></tr></thead>\n'
            '<tbody>\n' + '\n'.join(trs) + '\n</tbody>\n</table>\n')


def inject_skeleton(text):
    """在 example 文本上机械注入理解骨架六件，返回注入后的 HTML 文本。

    逐件判定（v1.19.0 E5 夹具校准）：组件按**作用域内已有量**按需补齐——
    封面两件看全课、词典看全课、改造指南看结业段、模块卡与设计四问看模块段
    （每正式模块缺几张补几张，design-qa 补到 SKEL_DESIGN_BLOCKS 块）。这样
    对 v1.17 形态旧成品（六件全缺）行为与原版一致，对 v1.18.1 重建成品
    （六件在场但每模块 design-qa 仅 2 块）精确补缺口，而不是整体跳过。
    收尾 fail-loud：注入后六件必须都在场，否则报错而不是让断言悄悄失去意义。
    """
    out = text
    hero_extra = ''
    if 'class="arch-scene' not in out:
        hero_extra += _arch_scene_html(_arch_json_from_cover(out))
    if 'class="run-chain"' not in out:
        hero_extra += _run_chain_html()
    if hero_extra:
        out2 = re.sub(r'(<section class="module hero"[^>]*>)',
                      lambda m: m.group(1) + '\n' + hero_extra, out, count=1)
        if out2 == out:
            raise AssertionError('封面段锚点缺失，骨架注入无法进行')
        out = out2

    state = {'vd': 'class="vardict-scene' in out,
             'guide': 'class="upgrade-guide' in out}

    def _count_cls(seg, cls):
        # (?![\w-])：design-qa-off 这类改名产物不得计入已有量
        return len(re.findall(r'class="[^"]*\b%s(?![\w-])' % cls, seg))

    def _inject_module(m):
        open_tag, seg = m.group(1), m.group(0)
        if re.search(r'class="[^"]*\bhero\b', open_tag):
            return seg                      # 封面不参与检查 20/22/23
        body = ''
        mid = re.search(r'id="([^"]*)"', open_tag)
        if mid and 'finale' in mid.group(1):
            if not state['guide'] and not _count_cls(seg, 'upgrade-guide'):
                state['guide'] = True
                body += _upgrade_guide_html()
            if body:
                return seg.replace(open_tag, open_tag + '\n' + body, 1)
            return seg
        if not _count_cls(seg, 'module-card'):
            body += _module_card_html()
        if not state['vd'] and not _count_cls(seg, 'vardict-scene'):
            state['vd'] = True
            body += _vardict_html()
        have_dq = _count_cls(seg, 'design-qa')
        if have_dq < SKEL_DESIGN_BLOCKS:
            body += ''.join(_design_qa_html(have_dq + i)
                            for i in range(1, SKEL_DESIGN_BLOCKS
                                           - have_dq + 1))
        if body:
            return seg.replace(open_tag, open_tag + '\n' + body, 1)
        return seg

    out = re.sub(r'(<section class="module"[^>]*>)[\s\S]*?</section>',
                 _inject_module, out)
    for cls in ('arch-scene', 'run-chain', 'module-card', 'vardict-scene',
                'design-qa', 'upgrade-guide'):
        if ('class="%s' % cls) not in out:
            raise AssertionError('骨架注入后仍缺 .%s（example 形态变了？）' % cls)
    return out


def skeleton_course_path():
    """「example 副本 + 骨架注入」落盘路径（本套件绿路径断言的基准产物）。"""
    return make_course('skel')


def run_mutant(tag, transform, tier='L2', inject=True):
    """在（注入后的）副本上做单点变异并跑 CLI，返回 (rc, 输出文本)。"""
    try:
        path = make_course(tag, transform, inject)
    except AssertionError as exc:
        return None, 'ANCHOR-MISS %s' % exc
    args = ['validate_course.py', path] + (['--tier', tier] if tier else [])
    return run_main(args)


# --------------------------------------- v1.19.0 E5：夹具校准与新检查的变异设施
def design_keep_first():
    """返回变异器：每个正式模块的 .design-qa 减到恰 1 块（段内第 1 块保留，
    其余改名摘除）。

    成品每模块 2 块 / 注入器补齐后每模块 3 块——两种形态下都得到「每模块
    恰 1 块、4 行」，使 22a（L2）/22b（L3）的目标文案精确可断言（「1 块 < 2」
    /「1 块 < 3」），并让 22d 档位门（L1 下限 1）判绿成立。
    """
    def _t(text):
        def _seg(m):
            seg = m.group(0)
            seen = [0]

            def _q(qm):
                seen[0] += 1
                if seen[0] == 1:
                    return qm.group(0)
                return qm.group(0).replace('class="design-qa"',
                                           'class="design-qa-off"', 1)
            return re.sub(r'<div class="design-qa">', _q, seg)
        out, n = re.subn(r'<section class="module[^>]*>[\s\S]*?</section>',
                         _seg, text)
        if not n:
            raise AssertionError('no module section for design_keep_first')
        return out
    return _t


def strip_six(text):
    """机械摘除理解骨架六件（类名改名法）→「无骨架成品」形态。

    ORG 恢复的 example 已是 v1.18.1 重建合规成品（六件在场、自身全绿），
    test_example_conflict 的原断言语义（缺六件被检查 19-23 逐件点名）改由
    本变异承载：改名对解析层等价于摘除（各组件计数归零），不依赖组件
    内部 HTML 形态。
    """
    t = text
    for old, new in (
            ('<div class="arch-scene', '<div class="arch-scene-off'),
            ('<ol class="run-chain"', '<ol class="run-chain-off"'),
            ('<div class="module-card">', '<div class="module-card-off">'),
            ('<div class="vardict-scene">',
             '<div class="vardict-scene-off">'),
            ('<div class="design-qa">', '<div class="design-qa-off">'),
            ('<table class="upgrade-guide">',
             '<table class="upgrade-guide-off">')):
        if old not in t:
            raise AssertionError('strip_six anchor missing: %r' % old)
        t = t.replace(old, new)
    return t


def measured_mut(files='utils/vision.py'):
    """返回变异器：给封面运行链第 1 步注入 data-ev="measured" 主张。

    files=None 时只带主张不带 data-ev-files（空主张变体）；多文件用分号
    分隔（与 SPEC §2.5 的声明语法一致）。锚点不含收尾 `>`——属性必须
    落在开标签内，落在外面就成了正文文本（注入必红会静默失真）。
    """
    def _t(text):
        old = '<li class="rc-step" data-step="1"'
        if old not in text:
            raise AssertionError('rc-step #1 anchor missing')
        extra = '' if files is None else ' data-ev-files="%s"' % files
        return text.replace(old, old + ' data-ev="measured"' + extra + '>', 1)
    return _t


def write_trace(tag, files, schema='trace-facts-v2'):
    """落盘一份最小 trace-facts-v2 采集文件，返回路径（供 --trace-facts）。"""
    d = fresh_dir('trace' + tag)
    path = os.path.join(d, 'trace-facts.json')
    with io.open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(json.dumps({
            'schema': schema, 'repo': '.', 'runtime': 'python',
            'command': 'python -m click --help', 'duration_s': 1.0,
            'files': files, 'edges': []}, ensure_ascii=False))
    return path


def append_body(frag):
    """返回变异器：把片段插到 </main> 之前（构建卡/复刻线段的注入位）。"""
    def _t(text):
        if '</main>' not in text:
            raise AssertionError('</main> anchor missing')
        return text.replace('</main>', frag + '\n</main>', 1)
    return _t


def build_card_html(cmd_rows):
    """构造 .build-run-card 段：cmd_rows 为 (data-cmd, data-src) 元组列表。"""
    rows = '\n'.join('<div class="build-cmd" data-cmd="%s" data-src="%s">'
                     '</div>' % c for c in cmd_rows)
    return '<div class="build-run-card">\n%s\n</div>\n' % rows


def rebuild_path_html(steps):
    """构造 .rebuild-path 段：steps 为 (编号原文, 是否环块) 元组列表。"""
    lis = '\n'.join(
        '<div class="rb-step" data-step="%s"%s>step</div>'
        % (num, ' data-cycle="true"' if cyc else '')
        for num, cyc in steps)
    return '<div class="rebuild-path">\n%s\n</div>\n' % lis


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
    # v1.18.0：绿路径基准产物改为「example 副本 + 骨架注入」（见文件头「骨架注入」
    # 节与 test_example_conflict）——盘上 example 是 v1.17.0 前的旧成品，检查 19-23
    # 判它红。断言语义不变：合规课程在 CLI 绿路径下 exit 0。
    green = skeleton_course_path()
    rc, out = run_main(['validate_course.py', green, '--tier', 'L2'])
    ck(rc == 0 and '全部通过' in out,
       'val-main: example+skeleton clone validates green under L2 (CLI contract)')
    rc, _out = run_main(['validate_course.py', green, '--mask'])
    ck(rc == 0, 'val-main: --mask run stays green (mask_scan executed)')
    empty_src = fresh_dir('emptysrc')
    rc, out = run_main(['validate_course.py', green, '--source', empty_src])
    ck(rc in (0, 1) and out,
       'val-verbatim: --source with missing files runs verbatim_check')
    rc, out = run_main(['validate_course.py', green, '--source', SOURCE_DIR])
    ck(rc in (0, 1) and out,
       'val-verbatim: --source with the real tree runs verbatim_check')
    rc, out = run_main(['validate_course.py', green, '--tier', 'L3'])
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
    rc, out = run_main(['validate_course.py', path])
    # 批次 7r 更正（P2-4，验证者）：本断言是「覆盖见证」而非 :839 的语义
    # 守卫——空 pair 两侧皆空集，禁用 :839 continue 后循环体对空集不产生
    # 任何可观察差异（验证者变异实证仍绿），故它证明的是「空 pair 进入配
    # 对循环区域、被摘要计数且零错误」，不能证明「:839 在跳过它」。其判别
    # 力在于摘要计数（只数非空 pair 的变异会红）与 rc==0。
    _praw, _pchk = parse_example()
    expect_pairs = len(_pchk.pairs) + 1
    ck(rc == 0 and ('翻译块 %d 个' % expect_pairs) in out,
       'b7-main: empty translate-pair is a coverage witness — it reaches '
       'the pair-loop region and is counted in the summary with zero '
       'errors (NOT a semantic guard of the :839 skip: for empty pairs '
       'disabling the skip is unobservable by construction) (summary=%d '
       'pairs, rc=%d)'
       % (expect_pairs, rc))

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


# --------------------------------------- 6. v1.18.0 检查 19-23（理解骨架六件）
def test_skeleton_green():
    """正向可达：注入骨架的副本在 --tier L2 下全绿，汇总行逐件 ✓ 且有计数。"""
    rc, out = run_main(['validate_course.py', skeleton_course_path(),
                        '--tier', 'L2'])
    ck(rc == 0 and '全部通过' in out,
       'v18-green: example+skeleton clone is fully green under L2 (rc=%d)' % rc)
    line = ''
    for ln in out.splitlines():
        if ln.startswith('理解骨架（19-23）'):
            line = ln
    ck(bool(line), 'v18-green: 19-23 汇总行存在（✓/✗ + 计数）')
    ck(line.count('✓') == 6 and '✗' not in line,
       'v18-green: 六件全 ✓（%s）' % line)
    ck(bool(re.search(r'架构图 \d+ 张 ✓', line)) and
       bool(re.search(r'运行链 \d+ 条 [4-9]\d* 步 ✓', line)),
       'v18-green: 封面架构图与运行链步数落在汇总行')
    ck(bool(re.search(r'模块卡 \d+ 张 \d+ 行 ✓', line)) and
       bool(re.search(r'设计四问 \d+ 块 \d+ 行 ✓', line)) and
       bool(re.search(r'改造指南 \d+ 个 \d+ 行 ✓', line)),
       'v18-green: 模块卡/设计四问/改造指南的块与行计数落在汇总行')


def test_skeleton_direct():
    """直调五个新检查：真实解析状态 + 手工最小记录的边界值（含档位门）。"""
    _raw, chk = parse_example()
    stats = chk.module_stats

    for label, fn, extra in (('19 封面架构图与运行链', VC.arch_scene_check, ()),
                             ('20 每模块三句话卡', VC.module_card_check, ()),
                             ('21 变量词典', VC.vardict_check, ()),
                             ('22 设计四问（L3 加严）', VC.design_qa_check, ('L3',)),
                             ('23 改造指南（L3 加严）',
                              VC.upgrade_guide_check, ('L3',))):
        errs = []
        fn(stats, *extra, errs)
        ck(errs == [], 'v18-direct: 注入骨架的真实统计通过 %s' % label)

    ck(sum(m.get('arch', 0) for m in stats) >= 1
       and sum(m.get('runchain', 0) for m in stats) >= 1
       and sum(m.get('rc_steps', 0) for m in stats) >= VC.SKEL_RC_STEPS,
       'v18-stats: arch/runchain/rc_steps 落在 module_stats')
    ck(all(all(k in m for k in ('arch', 'runchain', 'rc_steps', 'card',
                                'card_rows', 'vardict', 'vd_rows', 'vc_nodes',
                                'design', 'dq_rows', 'guide', 'ug_rows'))
           for m in stats),
       'v18-stats: 契约 §三 的 12 个新计数字段全部落在每条 module_stats 上')

    def rec(**kw):
        base = {'id': 'm1', 'hero': False, 'pairs': 0, 'eng': 0, 'quiz': 0,
                'cg': 0, 'text': []}
        base.update(kw)
        return base

    for label, mod, want in (
            ('19 边界 4 步判绿',
             rec(id='m0', hero=True, arch=1, runchain=1, rc_steps=4), 0),
            ('19 缺架构图判红',
             rec(id='m0', hero=True, arch=0, runchain=1, rc_steps=5), 1),
            ('19 缺运行链判红',
             rec(id='m0', hero=True, arch=1, runchain=0, rc_steps=5), 1),
            ('19 运行链 3 步判红',
             rec(id='m0', hero=True, arch=1, runchain=1, rc_steps=3), 1)):
        errs = []
        VC.arch_scene_check([mod], errs)
        ck(len(errs) == want, 'v18-19: %s（errs=%d）' % (label, len(errs)))
    errs = []
    VC.arch_scene_check([rec(id='m1', arch=0, runchain=0)], errs)
    ck(errs == [], 'v18-19: 非封面模块不受检查 19 约束')

    for label, mod, want in (
            ('20 卡内 4 行判绿', rec(id='m1', card=1, card_rows=4), 0),
            ('20 缺卡判红', rec(id='m1', card=0, card_rows=9), 1),
            ('20 卡内 3 行判红', rec(id='m1', card=1, card_rows=3), 1),
            ('20 两卡 7 行判红', rec(id='m1', card=2, card_rows=7), 1),
            ('20 封面豁免', rec(id='m0', hero=True, card=0), 0),
            ('20 结业段豁免', rec(id='m9-finale', card=0), 0),
            ('20 无 id 豁免', rec(id=None, card=0), 0)):
        errs = []
        VC.module_card_check([mod], errs)
        ck(len(errs) == want, 'v18-20: %s（errs=%d）' % (label, len(errs)))

    for label, mods, want in (
            ('21 无词典判红', [rec(id='m1')], 1),
            ('21 一场景两行两节点判绿',
             [rec(id='m1', vardict=1, vd_rows=2, vc_nodes=2)], 0),
            ('21 场景空着判红',
             [rec(id='m1', vardict=1, vd_rows=0, vc_nodes=2)], 1),
            ('21 缺生命周期链判红',
             [rec(id='m1', vardict=1, vd_rows=1, vc_nodes=1)], 1),
            ('21 两场景四行四节点判绿',
             [rec(id='m1', vardict=2, vd_rows=2, vc_nodes=4)], 0)):
        errs = []
        VC.vardict_check(mods, errs)
        ck(len(errs) == want, 'v18-21: %s（errs=%d）' % (label, len(errs)))

    for tier, want in (('L1', 0), ('L2', 1), ('L3', 1), ('no-such-tier', 0),
                       (None, 0)):
        errs = []
        VC.design_qa_check([rec(id='m1', design=1, dq_rows=4)], tier, errs)
        ck(len(errs) == want,
           'v18-22: 1 块在档位 %s 下 errs=%d（L1/未给为下限 1）'
           % (tier, len(errs)))
    errs = []
    VC.design_qa_check([rec(id='m1', design=1, dq_rows=3)], 'L1', errs)
    ck(len(errs) == 1 and '设计四问缺项' in errs[0],
       'v18-22: 块数够但四问缺项判红')
    errs = []
    VC.design_qa_check([rec(id='m0', hero=True, design=0),
                        rec(id='m9-finale', design=0)], 'L3', errs)
    ck(errs == [], 'v18-22: 封面与结业段不参与设计四问下限')

    for tier, want in (('L1', 0), ('L2', 1), ('L3', 1), ('no-such-tier', 0),
                       (None, 0)):
        errs = []
        VC.upgrade_guide_check([rec(id='m9-finale', guide=1, ug_rows=4)],
                               tier, errs)
        ck(len(errs) == want,
           'v18-23: 4 条在档位 %s 下 errs=%d（L2/L3 加严到 6）'
           % (tier, len(errs)))
    errs = []
    VC.upgrade_guide_check([rec(id='m9-finale', guide=0, ug_rows=9)], 'L2', errs)
    ck(len(errs) == 1 and '缺改造指南' in errs[0], 'v18-23: 缺改造指南表判红')
    errs = []
    VC.upgrade_guide_check([rec(id='m1', guide=0, ug_rows=0)], 'L2', errs)
    ck(errs == [], 'v18-23: 非结业段模块不参与检查 23')


def test_skeleton_negative():
    """注入必红：每个新检查 ≥2 个变异体，逐条断言目标 ERROR 文案。

    v1.19.0 E5 夹具校准（基线 17 失败处置）：盘上 example 已是 v1.18.1 重建
    合规成品（探针 agent-out/v119/e5-probe.py 实证：arch-scene×1 带 scene
    尾类、run-chain 8 步且开标签带 aria-label、vardict-scene×2（m3 12 行 /
    m5 7 行）、design-qa 每模块 2 块、ug-row 9 行）。因此：
    ① 删除类变异一律改用**类名改名法**（解析层计数即归零，等价于摘除；
      对成品/注入两种形态都命中，不再依赖注入器的内部 HTML 形态）；
    ② 数量类变异按成品真实计数标定（8 步减到 3、9 行减到 3、每模块减到 1 块）；
    ③ 断言语义（rc 期待 + 目标 ERROR 文案）一字未放宽。
    """
    drop_arch = sub('<div class="arch-scene', '<div class="arch-scene-off')
    drop_chain = sub('<ol class="run-chain"', '<ol class="run-chain-off"')
    rc_steps_3 = rex(r'<li class="rc-step" data-step="[45678]">',
                     '<li class="rc-step-off" data-step="0">', count=5)
    card_off = sub('<div class="module-card">', '<div class="module-card-off">')
    mc_row_3 = sub('<div class="mc-row" data-key="segment">',
                   '<div class="mc-row-off" data-key="segment">')
    chain_off = sub('<div class="var-chain"', '<div class="var-chain-off"')
    stage_drop = rex(r'(class="vardict-row" data-var="[^"]*") data-stage="[^"]*"',
                     r'\1', count=99)
    vd_off = sub('<div class="vardict-scene">',
                 '<div class="vardict-scene-off">', count=99)
    design_1 = design_keep_first()
    dq_row_3 = sub('<div class="dq-row" data-q="simpler">',
                   '<div class="dq-row-off" data-q="simpler">')
    ug_3 = rex(r'<tr class="ug-row" data-task="[^"]*">',
               '<tr class="ug-row-off" data-task="x">', count=6)
    ug_4 = rex(r'<tr class="ug-row" data-task="[^"]*">',
               '<tr class="ug-row-off" data-task="x">', count=2)
    ug_off = sub('<table class="upgrade-guide">',
                 '<table class="upgrade-guide-off">')

    def outside_row(text):
        """卡内减到 3 行，再在卡外补一条游离 .mc-row（不能替卡片充数）。"""
        text = mc_row_3(text)
        return sub('<div class="design-qa">',
                   '<div class="mc-row" data-key="ghost"></div>\n'
                   '<div class="design-qa">')(text)

    cases = [
        ('19a', '删封面 .arch-scene', drop_arch, 'L2', '缺仓库总架构图'),
        ('19b', '删封面 .run-chain', drop_chain, 'L2', '缺一次完整运行链路'),
        ('19c', '运行链 8 步减到 3 步', rc_steps_3, 'L2', '.rc-step 仅 3 步'),
        ('19d', '常开：删架构图（无 --tier）', drop_arch, None,
         '缺仓库总架构图'),
        ('20a', '卡片类名被改（卡消失）', card_off, 'L2', '缺三句话卡'),
        ('20b', '卡内 .mc-row 减到 3 行', mc_row_3, 'L2', '三句话卡内容不全'),
        ('20c', '卡外游离 .mc-row 不能充数', outside_row, 'L2',
         '三句话卡内容不全'),
        ('20d', '常开：卡消失（无 --tier）', card_off, None, '缺三句话卡'),
        ('21a', '删 .var-chain（生命周期链）', chain_off, 'L2', '缺生命周期链'),
        ('21b', 'vardict-row 全部去掉 data-stage', stage_drop, 'L2', '有空场景'),
        ('21c', '删全部 .vardict-scene', vd_off, 'L2', '全课缺变量词典'),
        ('21d', '常开：删 var-chain（无 --tier）', chain_off, None,
         '缺生命周期链'),
        ('22a', '四问块每模块减到 1（L2）', design_1, 'L2',
         '设计四问 1 块 < 2'),
        ('22b', '四问块每模块减到 1（L3）', design_1, 'L3',
         '设计四问 1 块 < 3'),
        ('22c', '某块四问减到 3 问', dq_row_3, 'L2', '设计四问缺项'),
        ('23a', '改造指南 9 条减到 3 条（L2）', ug_3, 'L2',
         '改造指南条目 3 < 6'),
        ('23b', '删 .upgrade-guide', ug_off, 'L2', '缺改造指南'),
    ]
    for tag, label, transform, tier, kw in cases:
        rc, out = run_mutant('neg' + tag, transform, tier)
        ck(rc == 1 and kw in out,
           'v18-negative %s %s → rc=%s，目标 ERROR「%s」%s'
           % (tag, label, rc, kw, '出现' if kw in out else '未出现'))

    # 档位门：22/23 的加严下限——同一变异在 L1 缺省下限下应判绿
    for tag, label, transform in (
            ('22d', '四问每模块 1 块（L1 下限 1）', design_1),
            ('23c', '改造指南 7 条（L1 下限 4，L2 下限 6）', ug_4)):
        rc, out = run_mutant('gate' + tag, transform, None)
        ck(rc == 0 and '全部通过' in out,
           'v18-tier-gate %s %s → rc=%s（无 --tier 走 L1 下限，判绿）'
           % (tag, label, rc))


def test_example_conflict():
    """example 集成断言（v1.18.0 建立；v1.19.0 E5 夹具校准，语义未放宽）。

    原断言语义：无骨架成品在 L2 下必红，19-23 逐件点名（断到具体文案）。
    承载方式更新：ORG 恢复的 example 已是 v1.18.1 重建合规成品（六件在场、
    自身 rc=0——旧断言因此整体失效），故「无骨架形态」由 strip_six 机械
    构造（类名改名 = 解析层计数归零）。另补一条正向锚：盘上成品自身在 L2
    下全绿——夹具合规回归锚，防夹具再度漂移时静默通过。
    """
    rc, out = run_mutant('pristine', None, 'L2', inject=False)
    ck(rc == 0 and '全部通过' in out,
       'v18-conflict: 盘上成品（v1.18.1 重建成品夹具）自身在 L2 下全绿'
       '（rc=%s）' % rc)
    rc, out = run_mutant('strip6', strip_six, 'L2', inject=False)
    ck(rc == 1, 'v18-conflict: 摘除六件的无骨架成品在 L2 下判红（rc=%s）' % rc)
    for kw, label in (('缺仓库总架构图', '19 封面架构图'),
                      ('缺一次完整运行链路', '19 封面运行链'),
                      ('缺三句话卡', '20 模块卡'),
                      ('全课缺变量词典', '21 变量词典'),
                      ('设计四问', '22 设计四问'),
                      ('缺改造指南', '23 改造指南')):
        ck(kw in out,
           'v18-conflict: 无骨架成品缺 %s 被点名（关键词「%s」）' % (label, kw))


# ------------------------------------------- v1.19.0 检查 24（实测主张锚定）
def test_v119_measured():
    """24a/24b 注入必红 + 全命中绿 + 无属性向后兼容（SPEC §2.5 三类别）。"""
    # 向后兼容：无属性成品、不给 --trace-facts → 检查整体跳过，rc 不变
    rc, out = run_main(['validate_course.py', skeleton_course_path()])
    ck(rc == 0 and '全部通过' in out and '实测主张 0 处' in out,
       'v119-24-compat: 无属性成品跳过检查 24（汇总行「实测主张 0 处」，rc=%d）'
       % rc)

    # 24a：有主张、未提供 --trace-facts → ERROR
    rc, out = run_mutant('ev24a', measured_mut(), 'L2')
    ck(rc == 1 and '实测主张缺证据' in out,
       'v119-24a: measured 无 --trace-facts 必红（rc=%s）' % rc)

    # 绿：主张 + 全命中轨迹 → rc=0；反斜杠路径声明归一后同样命中
    tf_ok = write_trace('ok', {'utils/vision.py': [88, 120, 211]})
    rc, out = run_main(['validate_course.py',
                        make_course('evok', measured_mut()), '--tier', 'L2',
                        '--trace-facts', tf_ok])
    ck(rc == 0 and '全部通过' in out and '实测主张 1 处 ✓' in out,
       'v119-24: 全命中轨迹判绿（rc=%s）' % rc)
    rc, out = run_main(['validate_course.py',
                        make_course('evbsl', measured_mut('utils\\vision.py')),
                        '--tier', 'L2', '--trace-facts', tf_ok])
    ck(rc == 0, 'v119-24: 反斜杠路径声明归一后命中（rc=%s）' % rc)

    # 24b-1：声明文件不在 trace.files → ERROR
    tf_miss = write_trace('miss', {'other/thing.py': [1]})
    rc, out = run_main(['validate_course.py',
                        make_course('evmiss', measured_mut()), '--tier', 'L2',
                        '--trace-facts', tf_miss])
    ck(rc == 1 and '不在轨迹中' in out,
       'v119-24b: 声明文件不在轨迹必红（rc=%s）' % rc)

    # 24b-2：键在但命中行数 0 → ERROR
    tf_zero = write_trace('zero', {'utils/vision.py': []})
    rc, out = run_main(['validate_course.py',
                        make_course('evzero', measured_mut()), '--tier', 'L2',
                        '--trace-facts', tf_zero])
    ck(rc == 1 and '零命中' in out,
       'v119-24b: 声明文件命中行数 0 必红（rc=%s）' % rc)

    # 24b-3：多文件声明部分缺失 → 逐文件点名
    tf_half = write_trace('half', {'utils/vision.py': [88]})
    rc, out = run_main(['validate_course.py',
                        make_course('evhalf', measured_mut(
                            'utils/vision.py;utils/probability.py')),
                        '--tier', 'L2', '--trace-facts', tf_half])
    ck(rc == 1 and '不在轨迹中' in out and 'utils/probability.py' in out,
       'v119-24b: 多文件声明缺失项被点名（rc=%s）' % rc)

    # 24b-4：主张无 data-ev-files 配套 → 空主张不可锚定，ERROR
    rc, out = run_main(['validate_course.py',
                        make_course('evnof', measured_mut(files=None)),
                        '--tier', 'L2', '--trace-facts', tf_ok])
    ck(rc == 1 and '缺文件声明' in out,
       'v119-24b: 无 data-ev-files 的主张必红（rc=%s）' % rc)

    # 24 卫生：schema 不对 / 文件打不开 → ERROR
    tf_bad = write_trace('bad', {'utils/vision.py': [1]}, schema='trace-v1')
    rc, out = run_main(['validate_course.py',
                        make_course('evbad', measured_mut()), '--tier', 'L2',
                        '--trace-facts', tf_bad])
    ck(rc == 1 and 'trace-facts-v2' in out,
       'v119-24: schema 非 trace-facts-v2 必红（rc=%s）' % rc)
    rc, out = run_main(['validate_course.py',
                        make_course('evio', measured_mut()), '--tier', 'L2',
                        '--trace-facts',
                        os.path.join(fresh_dir('evio-tf'), 'no-such.json')])
    # 注：trace 路径用独立 tag——fresh_dir 同 tag 二次调用会 rmtree 掉
    # make_course 刚写好的课程副本（main 将 rc=2「无法读取」而非检查 24 红）
    ck(rc == 1 and '无法解析' in out,
       'v119-24: --trace-facts 打不开必红（rc=%s）' % rc)


# ------------------------------------- v1.19.0 检查 25（构建卡/复刻线段结构）
def test_v119_buildcard():
    """25 结构 ×3 类别注入必红 + 段缺位跳过 + 环块并列绿（SPEC §2.6）。"""
    # 段缺位：成品无两段 → 不检查（汇总行 0/0 且 rc 不变）
    rc, out = run_main(['validate_course.py', skeleton_course_path(),
                        '--tier', 'L2'])
    ck(rc == 0 and '构建卡 0 张' in out and '复刻线 0 条' in out,
       'v119-25-skip: 段缺位不检查（rc=%d）' % rc)

    # 绿：完整构建卡 + 4 步复刻线 → rc=0
    ok = append_body(
        build_card_html([('python -m pip install -e .', 'README.md · L30')])
        + rebuild_path_html([('1', False), ('2', False), ('3', False),
                             ('4', False)]))
    rc, out = run_main(['validate_course.py', make_course('bc25ok', ok),
                        '--tier', 'L2'])
    ck(rc == 0 and '全部通过' in out and '构建卡 1 张 1 条命令 ✓' in out
       and '复刻线 1 条 4 步 ✓' in out,
       'v119-25: 完整两段判绿且汇总行计数正确（rc=%s）' % rc)

    # 绿：环块并列——3 个普通步 + 2 个 data-cycle 步 → 总数 5 ≥4、递增校验只看普通步
    cyc = append_body(rebuild_path_html([('1', False), ('2', False),
                                         ('3', False), ('2', True),
                                         ('3', True)]))
    rc, out = run_main(['validate_course.py', make_course('bc25cyc', cyc),
                        '--tier', 'L2'])
    ck(rc == 0 and '复刻线 1 条 5 步 ✓' in out,
       'v119-25: data-cycle 环块并列模块判绿（rc=%s）' % rc)

    # 25a-1：.build-run-card 段内 0 条命令 → ERROR
    rc, out = run_main(['validate_course.py',
                        make_course('bc25a', append_body(
                            '<div class="build-run-card">\n</div>\n')),
                        '--tier', 'L2'])
    ck(rc == 1 and '缺 .build-cmd' in out,
       'v119-25a: 空构建卡必红（rc=%s）' % rc)

    # 25a-2：.build-cmd 缺 data-src → ERROR
    rc, out = run_main(['validate_course.py',
                        make_course('bc25a2', append_body(
                            '<div class="build-run-card">\n'
                            '<div class="build-cmd" data-cmd="pip install">'
                            '</div>\n</div>\n')),
                        '--tier', 'L2'])
    ck(rc == 1 and '缺 data-src' in out,
       'v119-25a: 命令缺 data-src 必红（rc=%s）' % rc)

    # 25b：复刻线步骤 2 个 < 4 → ERROR
    rc, out = run_main(['validate_course.py',
                        make_course('bc25b', append_body(
                            rebuild_path_html([('1', False), ('2', False)]))),
                        '--tier', 'L2'])
    ck(rc == 1 and '步骤仅 2 个 < 4' in out,
       'v119-25b: 复刻线步数不足必红（rc=%s）' % rc)

    # 25c：步骤编号错乱（非环块 1,1,1,1）→ ERROR
    rc, out = run_main(['validate_course.py',
                        make_course('bc25c', append_body(
                            rebuild_path_html([('1', False), ('1', False),
                                               ('1', False), ('1', False)]))),
                        '--tier', 'L2'])
    ck(rc == 1 and '编号错乱' in out,
       'v119-25c: 步骤编号错乱必红（rc=%s）' % rc)

    # 25c-2：data-step 非整数 → ERROR
    rc, out = run_main(['validate_course.py',
                        make_course('bc25c2', append_body(
                            rebuild_path_html([('1', False), ('2', False),
                                               ('x', False), ('4', False)]))),
                        '--tier', 'L2'])
    ck(rc == 1 and '不是整数' in out,
       'v119-25c: data-step 非整数必红（rc=%s）' % rc)

    # 25 卫生：段外游离 .build-cmd 不计（无 .build-run-card 容器 → 检查跳过）
    rc, out = run_main(['validate_course.py',
                        make_course('bc25out', append_body(
                            '<div class="build-cmd" data-cmd="x" '
                            'data-src="y"></div>\n')),
                        '--tier', 'L2'])
    ck(rc == 0 and '构建卡 0 张' in out,
       'v119-25: 段外游离 build-cmd 不计、检查仍跳过（rc=%s）' % rc)


def test_cg_semantic_fields():
    """v1.18.0 §14a/§二：节点 desc/role、边 kind/detail 并入检查 16 键集。

    既有键与既有语义不动（about/call、confidence/resolved_by/resolution 照旧，
    非闭集值照旧报错）；新增字段出现即受「非空 + 上限 + 闭集」三条约束。
    """
    raw, chk = parse_example()
    data = graph_blocks(chk, raw)[0][1]

    errs = []
    d = _clone(data)
    d['nodes'][0].update({'desc': '程序入口：拉起界面与求解器',
                          'role': '启动与装配'})
    d['links'][0].update({'kind': 'owns', 'detail': '持有实例并驱动一次求解'})
    VC.callgraph_check(d, 'b6', errs, [])
    ck(errs == [], 'v18-cg14a: desc/role/kind/detail 合规值判绿（键集已扩容）')

    probes = [
        ('desc 超长', {'nodes': [0, {'desc': 'x' * (VC.CG_DESC_MAX + 1)}]},
         '超长'),
        ('desc 空串', {'nodes': [0, {'desc': '   '}]}, '不是非空字符串'),
        ('role 超长', {'nodes': [0, {'role': 'x' * (VC.CG_ROLE_MAX + 1)}]},
         '超长'),
        ('node view 仍是契约外键（arch 专用）',
         {'nodes': [0, {'view': 'own'}]}, '契约外键'),
        ('link desc 仍是契约外键', {'links': [0, {'desc': 'x'}]}, '契约外键'),
        ('link role 仍是契约外键', {'links': [0, {'role': 'x'}]}, '契约外键'),
        ('kind 出闭集', {'links': [0, {'kind': 'calls'}]}, '不在闭集'),
        ('kind 空串', {'links': [0, {'kind': ''}]}, '不在闭集'),
        ('detail 超长', {'links': [0, {'detail': 'x' * (VC.CG_DETAIL_MAX + 1)}]},
         '超长'),
        ('detail 非字符串', {'links': [0, {'detail': 1}]}, '不是非空字符串'),
    ]
    for label, spec, kw in probes:
        d = _clone(data)
        for coll, (idx, patch) in spec.items():
            d[coll][idx].update(patch)
        errs = []
        VC.callgraph_check(d, 'b6', errs, [])
        ck(any(kw in e for e in errs),
           'v18-cg14a: %s 判红（关键词「%s」）' % (label, kw))

    d = _clone(data)
    d['module_marks'] = []
    errs = []
    VC.callgraph_check(d, 'b6', errs, [])
    ck(any('顶层出现契约外键' in e for e in errs),
       'v18-cg14a: callgraph-data 顶层仍只允许 nodes/links（module_marks 判红）')


def test_arch_data_contract():
    """v1.18.0 §一.1：.arch-data 走调用图同一套契约，差异=module_marks + 节点 4–20。"""
    raw, chk = parse_example()
    arch = arch_block(raw)

    errs = []
    n = VC.arch_check(arch, 'b6', errs, [])
    ck(errs == [] and n >= 1,
       'v18-arch: 派生 arch-data 通过契约，返回 %d 条 module_marks' % n)
    errs = []
    bare = _clone(arch)
    bare.pop('module_marks', None)
    ck(VC.arch_check(bare, 'b6', errs, []) == 0 and errs == [],
       'v18-arch: module_marks 缺失时返回 0 且不报错（完整性由检查 19 把关）')

    def probe(label, mutate, kw):
        d = _clone(arch)
        mutate(d)
        errs = []
        VC.arch_check(d, 'b6', errs, [])
        ck(any(kw in e for e in errs), 'v18-arch: %s 判红（「%s」）' % (label, kw))

    probe('module_marks 空数组',
          lambda d: d.update({'module_marks': []}), '必须是非空数组')
    probe('module_marks 非数组',
          lambda d: d.update({'module_marks': 'm1'}), '必须是非空数组')
    probe('module_marks 项非对象',
          lambda d: d.update({'module_marks': ['m1']}), '不是对象')
    probe('module_marks 缺 id',
          lambda d: d['module_marks'][0].pop('id'), '缺 id')
    probe('module_marks 缺 label',
          lambda d: d['module_marks'][0].pop('label'), '缺 label')
    probe('module_marks 项出现契约外键',
          lambda d: d['module_marks'][0].update({'covers_x': []}), '契约外键')
    probe('covers 为空数组',
          lambda d: d['module_marks'][0].update({'covers': []}),
          'covers 必须是非空数组')
    probe('covers 指向不存在的节点',
          lambda d: d['module_marks'][0].update({'covers': ['no-such-node']}),
          '不是 nodes[].id')
    probe('covers 元素非字符串',
          lambda d: d['module_marks'][0].update({'covers': [1]}),
          '不是 nodes[].id')
    probe('节点少于 4 个',
          lambda d: d.update({'nodes': d['nodes'][:3]}), '不在 4–20 区间')
    probe('节点多于 20 个',
          lambda d: d.update({'nodes': d['nodes'] * 3}), '不在 4–20 区间')
    probe('view 出闭集',
          lambda d: d['nodes'][0].update({'view': 'bogus'}), '不在闭集')
    probe('节点未知键',
          lambda d: d['nodes'][0].update({'bogus': 1}), '契约外键')
    probe('顶层多余键',
          lambda d: d.update({'extra': 1}), '顶层出现契约外键')
    probe('arch-data 内的自环边',
          lambda d: d['links'].append(
              {'from': d['nodes'][0]['id'], 'to': d['nodes'][0]['id'],
               'count': 1, 'confidence': 'inferred'}), '自环')
    errs = []
    ck(VC.arch_check(['not-an-object'], 'b6', errs, []) == 0 and bool(errs),
       'v18-arch: 顶层非对象判红且返回 0')
    errs = []
    viewed = _clone(arch)
    viewed['nodes'][0]['view'] = 'own'
    ck(VC.arch_check(viewed, 'b6', errs, []) >= 1 and errs == [],
       'v18-arch: 节点 view=own 判绿（arch-data 专属可选键，闭集 own/flow）')


def test_module_marks_completeness():
    """v1.18.0 §一.1：多个正式模块时，封面总架构图的 module_marks 不得为空。"""
    def rec(**kw):
        base = {'id': 'm1', 'hero': False, 'pairs': 0, 'eng': 0, 'quiz': 0,
                'cg': 0, 'text': []}
        base.update(kw)
        return base

    hero_ok = rec(id='m0', hero=True, arch=1, arch_marks=2, runchain=1,
                  rc_steps=4)
    hero_bare = rec(id='m0', hero=True, arch=1, arch_marks=0, runchain=1,
                    rc_steps=4)
    errs = []
    VC.arch_scene_check([_clone(hero_bare), rec(id='m1'), rec(id='m2')], errs)
    ck(any('缺模块归属标注' in e for e in errs),
       'v18-19: 多正式模块而 module_marks 为空 → 判红')
    errs = []
    VC.arch_scene_check([_clone(hero_ok), rec(id='m1'), rec(id='m2')], errs)
    ck(errs == [], 'v18-19: module_marks 非空判绿')
    errs = []
    VC.arch_scene_check([_clone(hero_bare), rec(id='m1')], errs)
    ck(errs == [], 'v18-19: 只有一个正式模块时不要求归属标注')
    errs = []
    VC.arch_scene_check([_clone(hero_bare), rec(id='m1'),
                         rec(id='m9-finale')], errs)
    ck(errs == [], 'v18-19: 结业段不计入正式模块数（单正式模块仍免）')


def test_arch_data_negative():
    """注入必红（CLI 端到端）：arch-data 已注册且受契约约束。"""
    drop_marks = arch_json_transform(lambda d: d.pop('module_marks', None))
    ghost_cover = arch_json_transform(
        lambda d: d['module_marks'][0].update({'covers': ['no-such-node']}))
    three_nodes = arch_json_transform(
        lambda d: d.update({'nodes': d['nodes'][:3]}))
    top_extra = arch_json_transform(lambda d: d.update({'extra': 1}))
    link_kind = arch_json_transform(
        lambda d: d['links'][0].update({'kind': 'calls'}))
    view_bogus = arch_json_transform(
        lambda d: d['nodes'][0].update({'view': 'bogus'}))

    cases = [
        ('arch-marks', '删 module_marks', drop_marks, '缺模块归属标注'),
        ('arch-cover', 'covers 指向幽灵节点', ghost_cover, '不是 nodes[].id'),
        ('arch-nodes', '节点减到 3 个', three_nodes, '不在 4–20 区间'),
        ('arch-top', 'arch-data 顶层多余键', top_extra, '顶层出现契约外键'),
        ('arch-kind', '边 kind 出闭集', link_kind, '不在闭集'),
        ('arch-view', '节点 view 出闭集', view_bogus, '不在闭集'),
    ]
    for tag, label, transform, kw in cases:
        rc, out = run_mutant(tag.replace('-', ''), transform, 'L2')
        ck(rc == 1 and kw in out,
           'v18-arch-negative %s %s → rc=%s，目标 ERROR「%s」%s'
           % (tag, label, rc, kw, '出现' if kw in out else '未出现'))


def run_selftest():
    test_usage_and_io()
    test_green_and_flags()
    test_mutants()
    test_direct_checks()
    test_deep_checks()
    test_gap_close()
    test_skeleton_green()
    test_skeleton_direct()
    test_skeleton_negative()
    test_cg_semantic_fields()
    test_arch_data_contract()
    test_module_marks_completeness()
    test_arch_data_negative()
    test_example_conflict()
    test_v119_measured()
    test_v119_buildcard()
    test_main_guard()
    print('validate-tests: %d passed / %d failed'
          % (len(_passed), len(_failed)))
    for label in _failed:
        print('  FAIL %s' % label)
    return 0 if not _failed else 1


if __name__ == '__main__':
    sys.exit(run_selftest())
