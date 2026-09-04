#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_course.py — code2course 成品课程机械校验（零依赖，Python 3.8+ 纯标准库）

用法：
    python validate_course.py <course.html> [--mask] [--quiet]
        [--source <源仓库目录>] [--tier L1|L2|L3]

检查项（对应 quality-gates.md 验收标准与「脱敏机检清单」）：
  1.  无 {{占位符}} 残留（含模板注释块提示词）
  2.  无外部资源引用：src=/href=/url() 不得指向 http(s)://
      （豁免：app.js 内联源码中的 SVG 命名空间字符串不在属性上下文里，
       本脚本只扫属性，天然豁免；xmlns 属性本身也豁免）
  3.  四类 JSON 数据块（.viz-data/.onion-data/.tower-data/.fork-data）
      全部可被 JSON.parse 解析，字符串值不含裸 </script，
      且 note/anchor 等值内无 HTML 实体字面（JSON 是纯文本层）
  4.  每个 .translate-pair 内左右两侧 data-i 集合等长且一致
  5.  每个 .quiz 恰好一个 data-correct="true"；每个 .bet-scene 恰好一个
      data-bet-correct="true"；全部选项 data-why / data-bet-why 非空
  6.  模块锚点一一对应：每个 <section class="module" id="mN"> 都有
      对应 .nav-item[href="#mN"]，反之亦然
  7.  --mask：脱敏机检正则扫描（邮箱 / 盘符路径（含 … 截断豁免）/
      home 目录 / 常见密钥前缀 / 内网网段 / 密码赋值），命中仅告警
  8.  纯 HTML 校验：正文（pre/code/script/style/textarea 之外）与 HTML
      注释不得含 Markdown 语法（八类标记 ERROR + 孤立斜体 WARNING）
  9.  体积读数按磁盘字节计（newline='' 保留 CRLF，护栏阈值不被折叠）
  10. --source <dir>：逐字一致强校验——每个翻译块的转义后文本必须
      原样出现在源文件中；若头部标注 L行号区间，匹配位置必须落在
      区间容差内（抓"源仓库演进后行号漂移"）
  11. --tier L1|L2|L3：档位数量下限机检（每个非封面正式模块的
      翻译块/引擎组件/测验数对照 §0 参数表；阈值内置于脚本）
  12. CSS 变量审计：style 内 var(--x) 引用了未定义变量 → ERROR；
      color/background/fill/stroke 出现裸 #FFFDF8/#FFFFFF → WARNING
  13. 溯源 id 存在性：data-why / data-bet-why 中引用的 pair-* id
      必须在成品中真实存在（防"溯源表写了个不存在的 id"）
  14. 版本自证：成品应有 <meta name="generator" data-version="…">；
      缺失 WARNING（向后兼容旧产物），与内联外壳 @version 不一致 ERROR
  15. 散点内联 style ≤5 处（超出手写样式集中原则，WARNING）

退出码：发现 ERROR 非零退出（=1），仅 WARNING 时退出 0。
"""
import html
import json
import os
import re
import sys
from html.parser import HTMLParser


class CourseChecker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.errors = []
        self.warnings = []
        # 状态机
        self.json_blocks = []          # (cls, raw_text)
        self._json_cls = None
        self._json_buf = []
        self.pairs = []                # 每个 translate-pair 的 data-i 记录
        self._pair_stack = []          # 嵌套 translate-pair 不存在，但保留栈式收尾
        self.quizzes = []              # 每个测验/赌注容器的汇总记录
        self._pending_opts = []        # 当前容器内累计的选项
        self.modules = set()           # section.module 的 id
        self.nav_items = set()         # nav-item 的 href 锚
        self._stack = []               # (tag, classes) 开标签栈
        self._md_skip = 0              # pre/code/script/style/textarea 嵌套深度
        self.prose_lines = []          # (line_no, text) 正文文本行
        self.comment_lines = []        # (line_no, text) HTML 注释行
        self.ids = set()               # 全文档 id 集合
        self.why_texts = []            # data-why / data-bet-why 属性值
        self.generator_version = None  # <meta name="generator" data-version>
        self.inline_style_count = 0    # style=" 属性出现次数
        self.style_blocks = []         # <style> 内文本（CSS 变量审计用）
        self._style_buf = None
        self._in_tp_head = 0           # translate-pair 头部（行号标注所在）
        self._in_tp_code = 0           # translate-pair 代码列
        self.module_stack = []         # 运行中的 section.module 记录
        self.module_stats = []         # 每个模块的组件计数（--tier 用）
        # translate-pair 元数据（--source 逐字校验用）
        self.pair_meta = []            # 工作栈：运行中的翻译块
        self.pair_meta_all = []        # 持久列表：全部翻译块元数据

    # ---- Markdown 纯度：正文/注释收集（getpos 取当前行号） ----
    def _md_note(self, target, data):
        line = self.getpos()[0]
        for ln in data.split('\n'):
            if ln.strip():
                target.append((line, ln))
            line += 1

    # ---- 标签进入 ----
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get('class', '') or ''
        classes = cls.split()
        self._stack.append((tag, classes))
        if tag in ('pre', 'code', 'script', 'style', 'textarea'):
            self._md_skip += 1
        if 'id' in a:
            self.ids.add(a['id'])
        if tag == 'meta' and (a.get('name') or '').lower() == 'generator':
            self.generator_version = a.get('data-version') or a.get('content')
        if a.get('style', '').strip():
            self.inline_style_count += 1
        if tag == 'style':
            self._style_buf = []
        if tag == 'div' and 'tp-head' in classes:
            self._in_tp_head += 1
        if tag == 'div' and 'tp-code' in classes:
            self._in_tp_code += 1

        # 模块段（--tier 计数作用域）
        if tag == 'section' and 'module' in classes:
            self.module_stack.append({'id': a.get('id'), 'hero': 'hero' in classes,
                                      'pairs': 0, 'eng': 0, 'quiz': 0})
        if self.module_stack:
            top = self.module_stack[-1]
            if 'translate-pair' in classes:
                top['pairs'] += 1
            if set(classes) & {'flow-scene', 'onion-scene', 'tower-scene',
                               'fork-scene', 'bet-scene', 'viz-scene'}:
                top['eng'] += 1
            if tag == 'div' and 'quiz' in classes and 'bet-scene' not in classes:
                top['quiz'] += 1

        # JSON 数据块
        if tag == 'script' and a.get('type') == 'application/json':
            jcls = [c for c in classes
                    if c in ('viz-data', 'onion-data', 'tower-data', 'fork-data')]
            self._json_cls = jcls[0] if jcls else '(json)'
            self._json_buf = []
            return

        # 翻译块（栈式：遇到新的 translate-pair 开新记录）
        if 'translate-pair' in classes:
            meta = {'file': a.get('data-file') or '', 'chunks': [], 'head': []}
            self._pair_stack.append({'left': set(), 'right': set()})
            self.pairs.append(self._pair_stack[-1])
            self.pair_meta.append(meta)
            self.pair_meta_all.append(meta)
        else:
            if self._pair_stack and 'data-i' in a:
                side = 'left' if 'tp-line' in classes else 'right'
                self._pair_stack[-1][side].add(a['data-i'].strip())

        # 测验 / 赌注选项（栈式归属：找最近的 bet-scene / quiz 祖先；
        # 容器关闭时在 handle_endtag 里结算成一条记录）
        if 'quiz-opt' in classes and tag == 'button':
            owner_type = None
            for t, cs in reversed(self._stack[:-1]):
                if 'bet-scene' in cs:
                    owner_type = 'bet'
                    break
                if 'quiz' in cs:
                    owner_type = 'quiz'
                    break
            if owner_type is None:
                self.errors.append('quiz-opt 按钮不在 .quiz / .bet-scene 容器内')
            else:
                is_true = (a.get('data-bet-correct') if owner_type == 'bet'
                           else a.get('data-correct')) == 'true'
                why_key = 'data-bet-why' if owner_type == 'bet' else 'data-why'
                why_val = a.get(why_key) or ''
                if why_val.strip():
                    self.why_texts.append(why_val)
                self._pending_opts.append((owner_type, is_true,
                                           bool(why_val.strip())))

        # 模块 / 导航锚点
        if tag == 'section' and 'module' in classes:
            mid = a.get('id')
            if mid:
                self.modules.add(mid)
        if 'nav-item' in classes and tag == 'a':
            href = a.get('href', '')
            if href.startswith('#'):
                self.nav_items.add(href[1:])

        # 外部资源引用（属性上下文）
        for key in ('src', 'href', 'poster', 'data'):
            v = a.get(key)
            if v and re.match(r'^https?://', v.strip()):
                self.errors.append(
                    '外部资源引用：<%s %s="%s…">（零依赖铁律）' % (tag, key, v[:60]))
        style = a.get('style', '')
        for m in re.finditer(r'url\(\s*[\'"]?https?://', style):
            self.errors.append('style 内外部 url()：%s' % style.strip()[:80])

    # ---- 文本 ----
    def handle_data(self, data):
        if self._json_cls is not None:
            self._json_buf.append(data)
            return
        if self._style_buf is not None:
            self._style_buf.append(data)
        # 翻译块元数据：代码列（pre/code 内）与头部（行号标注所在）
        if self._pair_stack and self._in_tp_code and self._md_skip:
            self.pair_meta[-1]['chunks'].append(data)
        elif self._pair_stack and self._in_tp_head and not self._md_skip:
            self.pair_meta[-1]['head'].append(data)
        if not self._md_skip and data.strip():
            self._md_note(self.prose_lines, data)

    # ---- HTML 注释：说明性文字，同样不得用 Markdown 标记 ----
    def handle_comment(self, data):
        if data.strip() and data.strip() not in ('ng-instance',):
            self._md_note(self.comment_lines, data)

    # ---- 标签退出 ----
    def handle_endtag(self, tag):
        # Markdown 纯度：离开代码/脚本区
        if tag in ('pre', 'code', 'script', 'style', 'textarea') \
                and self._md_skip:
            self._md_skip -= 1
        if tag == 'style' and self._style_buf is not None:
            self.style_blocks.append(''.join(self._style_buf))
            self._style_buf = None
        # 弹栈到最近的同名开标签（容错：void 元素不入栈）
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                closing = self._stack[i:]
                del self._stack[i:]
                for t, cs in closing:
                    if t == 'div' and 'tp-head' in cs and self._in_tp_head:
                        self._in_tp_head -= 1
                    if t == 'div' and 'tp-code' in cs and self._in_tp_code:
                        self._in_tp_code -= 1
                    if t == 'div' and 'translate-pair' in cs and self._pair_stack:
                        self._pair_stack.pop()
                        self.pair_meta.pop()
                    if t == 'section' and 'module' in cs and self.module_stack:
                        self.module_stats.append(self.module_stack.pop())
                    if t == 'div' and ('quiz' in cs or 'bet-scene' in cs) \
                            and self._pending_opts:
                        otype = 'bet' if 'bet-scene' in cs else 'quiz'
                        opts = [o for o in self._pending_opts if o[0] == otype]
                        others = [o for o in self._pending_opts if o[0] != otype]
                        if opts:
                            self.quizzes.append({
                                'type': otype,
                                'n': len(opts),
                                'trues': sum(1 for o in opts if o[1]),
                                'nowhy': sum(1 for o in opts if not o[2]),
                            })
                        self._pending_opts = others
                break
        if tag == 'script' and self._json_cls is not None:
            raw = ''.join(self._json_buf)
            self._check_json(self._json_cls, raw)
            self._json_cls = None
            self._json_buf = []

    # ---- JSON 检查 ----
    def _check_json(self, cls, raw):
        try:
            json.loads(raw)
        except ValueError as e:
            self.errors.append('.%s JSON 解析失败：%s' % (cls, e))
            return
        if re.search(r'</script', raw, re.IGNORECASE):
            self.errors.append(
                '.%s JSON 字符串含裸 </script（会提前终止脚本元素，'
                '合法写法 <\\/script）' % cls)
        # JSON 是纯文本数据层：HTML 实体会被 textContent 字面显示
        for m in re.finditer(r'&(?:gt|lt|amp|quot|#39);', raw):
            self.warnings.append(
                '.%s JSON 值含 HTML 实体字面 %s（textContent 原样显示，'
                '直接写 > < & 字符）' % (cls, m.group(0)))


def check_raw_text(raw, errors):
    # 1. {{ 占位符残留
    for m in re.finditer(r'\{\{[^}\n]{0,60}\}\}', raw):
        errors.append('占位符残留：{{%s}}' % m.group(0)[2:-2][:50])


MASK_RULES = [
    ('邮箱', r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
    ('本机盘符路径', r'(?<![A-Za-z0-9])[A-Za-z]:[/\\][^\s"\'<>]{3,}'),
    ('home 目录', r'/(?:home|Users)/[A-Za-z0-9_-]{2,}'),
    ('密钥前缀', r'(?:sk-[A-Za-z0-9]{16,}|AKIA[A-Z0-9]{12,}|ghp_[A-Za-z0-9]{20,}|xox[bap]-[A-Za-z0-9-]{10,})'),
    ('内网网段', r'\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b'),
    ('密码赋值', r'(?i)(?:password|passwd|secret|token)\s*[:=]\s*[\'"][^\'"]{6,}'),
]


def mask_scan(raw, warnings):
    for name, pat in MASK_RULES:
        for m in re.finditer(pat, raw):
            frag = m.group(0)
            if '…' in frag:
                continue   # 已按规范脱敏的 … 截断形式，豁免
            warnings.append('脱敏疑点[%s]：%s' % (name, frag[:60]))


MD_ERROR_RULES = [
    ('代码围栏', re.compile(r'```|~~~')),
    ('行首井号标题', re.compile(r'^\s{0,3}#{1,6}\s+\S')),
    ('行首星号/横线列表', re.compile(r'^\s{0,3}[-*]\s+\S')),
    ('行首引用', re.compile(r'^\s{0,3}>\s*\S')),
    ('Markdown 链接', re.compile(r'\[[^\]\n]{1,80}\]\([^)\n]{1,200}\)')),
    ('表格分隔线', re.compile(r'\|\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|')),
    ('加粗星号', re.compile(r'\*\*[^*\n]{1,120}?\*\*')),
    ('行内反引号对', re.compile(r'`[^`\n]{1,120}`')),
]
MD_WARN_RULES = [
    ('疑似斜体星号', re.compile(r'(?<![\w*])\*[^*\s][^*\n]{0,80}?\*(?![\w*])')),
]


def markdown_scan(lines, errors, warnings, where):
    """对收集到的正文/注释行做 Markdown 标记扫描。"""
    for line_no, text in lines:
        for name, pat in MD_ERROR_RULES:
            m = pat.search(text)
            if m:
                errors.append('Markdown 混入[%s]（%s L%d）：%s'
                              % (name, where, line_no, m.group(0)[:50]))
        for name, pat in MD_WARN_RULES:
            m = pat.search(text)
            if m:
                warnings.append('Markdown 疑点[%s]（%s L%d）：%s（人工判定）'
                                % (name, where, line_no, m.group(0)[:50]))


# ---- 12. CSS 变量审计 + 对比度黑名单色 ----
def css_var_audit(style_text, js_set_vars, errors, warnings):
    if not style_text:
        return
    defined = set(re.findall(r'(--[A-Za-z0-9_-]+)\s*:', style_text))
    defined |= js_set_vars   # app.js 运行时 setProperty 注入的变量视为已定义
    used = set(re.findall(r'var\(\s*(--[A-Za-z0-9_-]+)', style_text))
    for v in sorted(used - defined):
        errors.append('未定义 CSS 变量：%s（var() 引用无定义，渲染为空）' % v)
    for line in style_text.splitlines():
        if 'color-mix(' in line or '--' in line.split(':')[0]:
            continue   # color-mix 内的 #FFFFFF 是调色成分；自定义属性定义豁免
        if re.search(r'(?:^|[;{]\s*)(color|background(?:-color)?|fill|stroke)\s*:[^;]*#(?:FFFDF8|FFFFFF)\b',
                     line, re.IGNORECASE):
            warnings.append('对比度黑名单色（裸白字）：%s（须用 --on-accent 族 '
                            'token；装饰性用途请注释豁免）' % line.strip()[:80])


# ---- 13. 溯源 id 存在性 ----
def trace_id_check(why_texts, known_ids, errors):
    for why in why_texts:
        for ref in set(re.findall(r'pair-[a-z0-9][a-z0-9-]*', why)):
            if ref not in known_ids:
                errors.append('溯源 id 死链：%s（data-why 引用了不存在的组件 id）'
                              % ref)


# ---- 10. --source 逐字一致强校验 ----
def _parse_file_segments(raw):
    """data-file 值解析：'utils/vision.py · L23-L36' 或
    'a.py · L1-L9 与 b.py · L2-L8'（多源）→ [(path, [(s,e),…]), …]"""
    segs = []
    for seg in re.split(r'\s*与\s*', raw):
        parts = seg.split('·')
        if len(parts) < 2:
            segs.append((seg.strip(), []))
            continue
        path = parts[0].strip()
        ranges = [(int(a), int(b)) for a, b in
                  re.findall(r'L\s*(\d+)\s*[-–—~]\s*L?\s*(\d+)', seg)]
        singles = [int(x) for x in re.findall(r'L\s*(\d+)(?!\s*[-–—~]\s*L?\s*\d)', seg)]
        ranges.extend((x, x) for x in singles)
        segs.append((path, ranges))
    return segs


def verbatim_check(pair_meta, source_dir, errors):
    src_cache = {}
    n_ok = n_fail = 0

    def load_src(rel):
        if rel not in src_cache:
            p = os.path.join(source_dir, *rel.replace('\\', '/').split('/'))
            try:
                with open(p, 'r', encoding='utf-8', errors='replace') as f:
                    src_cache[rel] = f.read().replace('\r\n', '\n')
            except OSError:
                src_cache[rel] = None
        return src_cache[rel]

    for i, pm in enumerate(pair_meta, 1):
        if not pm['file'] or not pm['chunks']:
            continue
        segs = _parse_file_segments(pm['file'])
        srcs = []
        for path, ranges in segs:
            src = load_src(path)
            if src is None:
                errors.append('逐字校验 #%d：源文件打不开 %s' % (i, path))
            else:
                srcs.append((path, src, ranges))
        if not srcs:
            continue
        for chunk in pm['chunks']:
            text = html.unescape(chunk).replace('\r\n', '\n').strip('\n')
            if len(text.strip()) < 20:
                continue   # 过短片段不足以做子串定位
            hit = False
            drift = None
            for path, src, ranges in srcs:
                if text not in src:
                    continue
                hit = True
                idx = src.find(text)
                line = src[:idx].count('\n') + 1
                for s, e in ranges:
                    if s - 3 <= line <= e + 3:
                        drift = None
                        break
                    drift = (path, s, e, line)
                break
            if hit and drift:
                n_fail += 1
                errors.append('行号漂移 #%d（%s）：标注 L%d-L%d，实际命中在 L%d'
                              '（源仓库在生成后演进过？更新标注或刷新快照）'
                              % (i, drift[0], drift[1], drift[2], drift[3]))
            elif hit:
                n_ok += 1
            else:
                n_fail += 1
                errors.append('逐字失配 #%d（%s）：转义后文本在源文件中找不到'
                              % (i, ' / '.join(p for p, _, _ in srcs)))
    return n_ok, n_fail


# ---- 11. --tier 档位数量下限 ----
TIER_RULES = {
    'L2': {'pairs': 2, 'eng': 1, 'quiz': 1},
    'L3': {'pairs': 3, 'eng': 2, 'quiz': 2},
}


def tier_check(module_stats, tier, errors):
    rule = TIER_RULES.get(tier)
    if rule is None:
        return
    for m in module_stats:
        if m['hero'] or not m['id']:
            continue   # 封面不参与内容量下限
        label = '档位下限[%s %s]' % (tier, m['id'])
        if m['pairs'] < rule['pairs']:
            errors.append('%s 翻译块 %d < %d' % (label, m['pairs'], rule['pairs']))
        if m['eng'] < rule['eng']:
            errors.append('%s 引擎组件 %d < %d'
                          % (label, m['eng'], rule['eng']))
        if m['quiz'] < rule['quiz']:
            errors.append('%s 测验 %d < %d' % (label, m['quiz'], rule['quiz']))


def main(argv):
    # Windows 控制台常见 GBK 编码：强制 UTF-8 输出，emoji 不再炸打印
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    args = []
    flags = []
    opts = {'--source': None, '--tier': None}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in opts:
            if i + 1 >= len(argv):
                print('%s 需要一个参数' % a)
                return 2
            opts[a] = argv[i + 1]
            i += 2
        elif a.startswith('-'):
            flags.append(a)
            i += 1
        else:
            args.append(a)
            i += 1
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    try:
        # newline=''：保留原始换行符，体积读数与磁盘字节一致（CRLF 不折叠）
        with open(path, 'r', encoding='utf-8', newline='') as f:
            raw = f.read()
    except OSError as e:
        print('无法读取 %s：%s' % (path, e))
        return 2

    errors, warnings = [], []
    check_raw_text(raw, errors)

    chk = CourseChecker()
    try:
        chk.feed(raw)
        chk.close()
    except Exception as e:
        errors.append('HTML 解析异常：%s' % e)
    errors.extend(chk.errors)

    # 4. data-i 配对
    for i, p in enumerate(chk.pairs, 1):
        if not p['left'] and not p['right']:
            continue
        if p['left'] != p['right']:
            only_l = p['left'] - p['right']
            only_r = p['right'] - p['left']
            errors.append(
                '翻译块 #%d data-i 配对不一致（左多 %s / 右多 %s）'
                % (i, sorted(only_l) or '无', sorted(only_r) or '无'))

    # 5. 正确项唯一 + why 非空（按容器汇总）
    for q in chk.quizzes:
        label = '测验' if q['type'] == 'quiz' else '赌注'
        if q['trues'] != 1:
            errors.append('%s（%d 个选项）正确项数量为 %d（必须恰好 1 个）'
                          % (label, q['n'], q['trues']))
        if q['nowhy']:
            errors.append('%s（%d 个选项）有 %d 个选项缺少解释属性'
                          % (label, q['n'], q['nowhy']))

    # 6. 模块锚点一一对应
    orphan_mods = chk.modules - chk.nav_items
    orphan_navs = chk.nav_items - chk.modules
    if orphan_mods:
        errors.append('模块无对应导航项：%s' % ', '.join(sorted(orphan_mods)))
    if orphan_navs:
        errors.append('导航项指向不存在的模块：%s' % ', '.join(sorted(orphan_navs)))

    # 7. --mask
    if '--mask' in flags:
        mask_scan(raw, warnings)

    # 8. 纯 HTML 校验：正文与注释不得含 Markdown 语法
    markdown_scan(chk.prose_lines, errors, warnings, '正文')
    markdown_scan(chk.comment_lines, errors, warnings, '注释')

    # 12. CSS 变量审计 + 对比度黑名单色
    js_set_vars = set(re.findall(
        r'setProperty\(\s*[\'"](--[A-Za-z0-9_-]+)', raw))
    js_set_vars |= set(re.findall(
        r'style="[^"]*?(--[A-Za-z0-9_-]+)\s*:', raw))
    css_var_audit('\n'.join(chk.style_blocks), js_set_vars, errors, warnings)

    # 13. 溯源 id 存在性
    trace_id_check(chk.why_texts, chk.ids, errors)

    # 14. 版本自证（generator meta）
    shell_ver_m = re.search(r'@version\s+([0-9][\w.]*)', raw)
    shell_ver = shell_ver_m.group(1) if shell_ver_m else None
    if chk.generator_version is None:
        warnings.append('产物无版本自证：<head> 缺 <meta name="generator" '
                        'data-version="技能版本">（旧版产物，建议补齐）')
    elif shell_ver and chk.generator_version != shell_ver:
        errors.append('generator meta 版本（%s）与内联外壳 @version（%s）不一致'
                      % (chk.generator_version, shell_ver))

    # 15. 散点内联 style 软阈值
    if chk.inline_style_count > 5:
        warnings.append('内联 style 属性 %d 处（>5）——布局微调应集中到课程样式块'
                        % chk.inline_style_count)

    # 10. --source 逐字一致强校验
    if opts['--source']:
        n_ok, n_fail = verbatim_check(chk.pair_meta_all, opts['--source'], errors)
        print('逐字校验（--source %s）：%d 块命中 / %d 块异常'
              % (opts['--source'], n_ok, n_fail))

    # 11. --tier 档位数量下限
    if opts['--tier']:
        tier_check(chk.module_stats, opts['--tier'], errors)

    quiet = '--quiet' in flags
    if not quiet:
        print('文件：%s（%.1f KB）' % (path, len(raw.encode("utf-8")) / 1024))
        print('检查：翻译块 %d 个 / 测验+赌注 %d 处 / JSON 块见上 / 模块 %d 个'
              % (len(chk.pairs), len(chk.quizzes), len(chk.modules)))
    for w in warnings:
        print('  ⚠️  %s' % w)
    for e in errors:
        print('  ✖ %s' % e)
    if not quiet:
        if errors:
            print('结果：✖ %d 个错误，%d 条告警' % (len(errors), len(warnings)))
        elif warnings:
            print('结果：⚠️ 通过（%d 条脱敏疑点待人工判定）' % len(warnings))
        else:
            print('结果：✅ 全部通过')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
