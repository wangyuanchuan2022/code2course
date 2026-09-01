#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_course.py — code2course 成品课程机械校验（零依赖，Python 3.8+ 纯标准库）

用法：
    python validate_course.py <course.html> [--mask] [--quiet]

检查项（对应 quality-gates.md 验收标准与「脱敏机检清单」）：
  1.  无 {{占位符}} 残留（含模板注释块提示词）
  2.  无外部资源引用：src=/href=/url() 不得指向 http(s)://
      （豁免：app.js 内联源码中的 SVG 命名空间字符串不在属性上下文里，
       本脚本只扫属性，天然豁免；xmlns 属性本身也豁免）
  3.  四类 JSON 数据块（.viz-data/.onion-data/.tower-data/.fork-data）
      全部可被 JSON.parse 解析，且字符串值不含裸 </script
  4.  每个 .translate-pair 内左右两侧 data-i 集合等长且一致
  5.  每个 .quiz 恰好一个 data-correct="true"；每个 .bet-scene 恰好一个
      data-bet-correct="true"；全部选项 data-why / data-bet-why 非空
  6.  模块锚点一一对应：每个 <section class="module" id="mN"> 都有
      对应 .nav-item[href="#mN"]，反之亦然
  7.  --mask：脱敏机检正则扫描（邮箱 / 本机路径 / home 目录 / 常见密钥
      前缀 / 内网网段 / 密码赋值），命中仅告警（需人工判定是否教学示例）
  8.  纯 HTML 校验（v1.11.1）：正文（pre/code/script/style/textarea 之外）
      不得含 Markdown 语法——代码围栏、行内反引号对、行首 # 标题、
      行首 -/* 列表、**加粗**、行首 > 引用、[文字](地址) 链接、|---| 表格
      均为 ERROR，HTML 注释内的 Markdown 标记同样报 ERROR（写入的内容
      一律不得含 Markdown）；孤立斜体星号为 WARNING（防误报，人工判定）
      （pre/code/script/style 内的逐字代码样例是被展示的数据，不检查）

退出码：发现 ERROR 非零退出（=1），仅 WARNING 时退出 0。
"""
import json
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
        self._line = 1                 # 当前行号（按已 feed 的原始文本估算）

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

        # JSON 数据块
        if tag == 'script' and a.get('type') == 'application/json':
            jcls = [c for c in classes
                    if c in ('viz-data', 'onion-data', 'tower-data', 'fork-data')]
            self._json_cls = jcls[0] if jcls else '(json)'
            self._json_buf = []
            return

        # 翻译块（栈式：遇到新的 translate-pair 开新记录）
        if 'translate-pair' in classes:
            self._pair_stack.append({'left': set(), 'right': set()})
            self.pairs.append(self._pair_stack[-1])
        elif self._pair_stack and 'data-i' in a:
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
                self._pending_opts.append((owner_type, is_true,
                                           bool((a.get(why_key) or '').strip())))

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
        elif not self._md_skip and data.strip():
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
        # 弹栈到最近的同名开标签（容错：void 元素不入栈）
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                closing = self._stack[i:]
                del self._stack[i:]
                for t, cs in closing:
                    if t == 'div' and 'translate-pair' in cs and self._pair_stack:
                        self._pair_stack.pop()
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


def check_raw_text(raw, errors):
    # 1. {{ 占位符残留
    for m in re.finditer(r'\{\{[^}\n]{0,60}\}\}', raw):
        errors.append('占位符残留：{{%s}}' % m.group(0)[2:-2][:50])


MASK_RULES = [
    ('邮箱', r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
    ('Windows 用户路径', r'[A-Za-z]:[/\\](?:Users|Documents and Settings)[/\\][A-Za-z0-9_.-]+'),
    ('home 目录', r'/(?:home|Users)/[A-Za-z0-9_-]{2,}'),
    ('密钥前缀', r'(?:sk-[A-Za-z0-9]{16,}|AKIA[A-Z0-9]{12,}|ghp_[A-Za-z0-9]{20,}|xox[bap]-[A-Za-z0-9-]{10,})'),
    ('内网网段', r'\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b'),
    ('密码赋值', r'(?i)(?:password|passwd|secret|token)\s*[:=]\s*[\'"][^\'"]{6,}'),
]


def mask_scan(raw, warnings):
    for name, pat in MASK_RULES:
        for m in re.finditer(pat, raw):
            frag = m.group(0)
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


def main(argv):
    # Windows 控制台常见 GBK 编码：强制 UTF-8 输出，emoji 不再炸打印
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    args = [a for a in argv[1:] if not a.startswith('-')]
    flags = [a for a in argv[1:] if a.startswith('-')]
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    try:
        with open(path, 'r', encoding='utf-8') as f:
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
