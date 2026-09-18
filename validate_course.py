#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_course.py — code2course 成品课程机械校验（零依赖，Python 3.8+ 纯标准库）

用法：
    python validate_course.py <course.html> [--mask] [--quiet]
        [--source <源仓库目录>] [--tier L1|L2|L3]
        [--trace-facts <trace-facts-v2.json>]

检查项（对应 quality-gates.md 验收标准与「脱敏机检清单」）：
  1.  无 {{占位符}} 残留（含模板注释块提示词）
  2.  无外部资源引用：src=/href=/url() 不得指向 http(s)://
      （豁免：app.js 内联源码中的 SVG 命名空间字符串不在属性上下文里，
       本脚本只扫属性，天然豁免；xmlns 属性本身也豁免）
  3.  五类 JSON 数据块（.viz-data/.onion-data/.tower-data/.fork-data/
      .callgraph-data）全部可被 JSON.parse 解析，字符串值不含裸 </script，
      且 note/anchor 等值内无 HTML 实体字面（JSON 是纯文本层）；
      v1.18.0 起第六类 .arch-data（总架构图）同此解析口径，并按检查 16 的
      调用图契约校验（见 16 末条）
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
  16. 调用图数据块（.callgraph-data，规格 callgraph-block-v1.13.1 §7 + B3 契约升级）：
      每个 link 有 from/to/confidence 且 confidence ∈ {verified, inferred}、
      from/to 命中 nodes[].id、无自环；verified link 必须有 file 与 line；
      每个 node 必须有 file 与 line（调用图不允许无出处的节点）；
      节点可选键 about/call：只允许出现在 nodes[]（links[] 出现即错）、
      出现即必须是非空字符串且限长（about ≤60 字、call ≤80 字）；
      全键白名单（§14a 逐字段闭集）：nodes/links 出现契约外未知键即错；
      facts v3 派生字段（B2 移交②）：resolved_by ∈ {name,binding,qualified}
      且只属于 verified 边；resolution=self_ref 的边禁入调用图数据；
      resolution ∈ {unresolved, ambiguous} 恒 inferred，resolution=unique
      必须 verified 且带合法 resolved_by；
      v1.18.0 契约 §二/§14a 兼容性扩展（不是新检查）：节点并入可选 desc
      （≤60 字）/role（≤40 字），边并入可选 kind（闭集 owns/call/dependency/
      data/control，缺省 call）/detail（≤80 字）；数据块顶层键集闭集——
      .callgraph-data 只允许 nodes/links；
      .arch-data（仓库总架构图）走同一套契约，唯二差异：顶层另允许
      module_marks（每项 {id,label,covers[]}，covers 必须命中 nodes[].id）、
      节点数 4–20，且节点另允许 view（闭集 own/flow，契约 §一.1）
  17. 调用图前置（v1.14.0 结构契约，workflow 第 5 步「调用图前置」）：
      封面（hero 模块）必须含 ≥1 张 .callgraph-scene（全项目图，模块/文件
      粒度）；每个正式模块（非封面、非结业段）必须含 ≥1 张 .callgraph-scene
      （本模块图，符号级）；结业段豁免（由结业三件专用口径把关）
  18. script 块完整性：任何 <script> 块的原文（含注释与字符串）不得含字面
      "<script" / "</script" 序列——浏览器会在此截断/嵌套解析，整个外壳
      脚本静默失效（v1.14.0 真实事故：app.js 头注释含字面 <script>）
  19. 理解骨架·封面（v1.18.0 结构契约）：封面（hero 段）≥1 张 .arch-scene
      （仓库总架构图）且 ≥1 条 .run-chain（链内 .rc-step ≥4 步）——缺一即 ERROR；
      多个正式模块时 .arch-data 的 module_marks 不得为空（模块归属标注）
  20. 理解骨架·模块卡：每个正式模块（非封面、非结业段）≥1 张 .module-card，
      且卡内 .mc-row ≥4（四行齐全）
  21. 理解骨架·变量词典：全课 ≥1 个 .vardict-scene；每个场景内
      .vardict-row[data-var][data-stage] ≥1，且 .var-chain 内
      .vc-node[data-var] ≥2（变量生命周期链）
  22. 理解骨架·设计四问：每个正式模块 .design-qa ≥1（L1）／≥2（L2）／
      ≥3（L3，--tier 未给按 L1），且每块内 .dq-row ≥4
  23. 理解骨架·改造指南：结业段（id 含 finale）≥1 张 .upgrade-guide，且
      .ug-row[data-task] ≥4（L1）／≥6（L2、L3）
      （19/20/21 常开与档位无关；22/23 除档位下限外常开）
  24. 实测主张锚定（v1.19.0 §2.5）：任何元素带 data-ev="measured" 时，
      本次校验必须提供 --trace-facts <trace-facts-v2.json>（24a），且该元素
      data-ev-files 声明的每个仓库相对路径必须在 trace.files 中且命中行数
      ≥1（24b）；缺 data-ev-files 的 measured 主张不可锚定，同样 ERROR。
      无 data-ev 属性 → 本检查整体跳过（向后兼容，v1.18 课零影响）
  25. 构建卡/复刻线段结构（v1.19.0 §2.6）：.build-run-card 段存在时，
      段内 ≥1 个 .build-cmd 行且每行 data-cmd、data-src 非空；
      .rebuild-path 段存在时，段内带 data-step 的步骤 ≥4 个且编号从 1 起
      连续递增（data-cycle="true" 的环块步骤并列模块、不参与递增校验）；
      段缺位 → 不检查（不强制进入理解骨架六件）

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
        self._json_where = ''          # 当前 JSON 块的定位串（模块 · 行号）
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
        self.cg_scenes = 0             # .callgraph-scene 全文档计数（检查 17 汇总行用）
        self._script_depth = 0         # script 元素深度（检查 18 原文收集用）
        self._script_text = []         # 当前 script 块原文累积
        # translate-pair 元数据（--source 逐字校验用）
        self.pair_meta = []            # 工作栈：运行中的翻译块
        self.pair_meta_all = []        # 持久列表：全部翻译块元数据
        # v1.19.0 检查 24/25 收集（全课级，不归属模块）
        self.measured_claims = []      # data-ev="measured" 的 [{files, line}]
        self.build_cards = 0           # .build-run-card 段数
        self.build_cmds = 0            # 段内 .build-cmd 行数
        self.build_cmd_bad = []        # (行号, 缺的属性名) 明细
        self.rebuild_paths = 0         # .rebuild-path 段数
        self.rb_steps = []             # (是否环块, data-step 原文) 按文档序

    # ---- Markdown 纯度：正文/注释收集（getpos 取当前行号） ----
    def _md_note(self, target, data):
        line = self.getpos()[0]
        for ln in data.split('\n'):
            if ln.strip():
                target.append((line, ln))
            line += 1

    # ---- 理解骨架六件计数（v1.18.0 结构契约 §一；归属最近的 section.module） ----
    def _in_ancestor(self, name):
        """当前元素是否落在某个 cls 含 name 的祖先里。

        self._stack 顶是当前元素自身（handle_starttag 先压栈），故取 [:-1]。
        """
        return any(name in cs for _t, cs in self._stack[:-1])

    def _skeleton_count(self, classes, a, top):
        """六大骨架组件的逐元素计数（契约 §三「计数落点」字段来源）。

        容器内计数：行/节点类只有落在自己的容器里才计——游离的 .mc-row 不能
        替别的卡片充数，否则「卡内 3 行 + 卡外 1 行」会假绿（注入必红实证）。
        带数据属性的行（vardict-row/ug-row）按契约以属性齐全为准：缺
        data-var/data-stage/data-task 的行不计。
        """
        if 'arch-scene' in classes:
            top['arch'] += 1
        if 'run-chain' in classes:
            top['runchain'] += 1
        if 'rc-step' in classes and self._in_ancestor('run-chain'):
            top['rc_steps'] += 1
        if 'module-card' in classes:
            top['card'] += 1
        if 'mc-row' in classes and self._in_ancestor('module-card'):
            top['card_rows'] += 1
        if 'vardict-scene' in classes:
            top['vardict'] += 1
        if 'vardict-row' in classes and self._in_ancestor('vardict-scene') \
                and (a.get('data-var') or '').strip() \
                and (a.get('data-stage') or '').strip():
            top['vd_rows'] += 1
        if 'vc-node' in classes and self._in_ancestor('var-chain') \
                and (a.get('data-var') or '').strip():
            top['vc_nodes'] += 1
        if 'design-qa' in classes:
            top['design'] += 1
        if 'dq-row' in classes and self._in_ancestor('design-qa'):
            top['dq_rows'] += 1
        if 'upgrade-guide' in classes:
            top['guide'] += 1
        if 'ug-row' in classes and self._in_ancestor('upgrade-guide') \
                and (a.get('data-task') or '').strip():
            top['ug_rows'] += 1

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
        # v1.18.0 理解骨架六件计数（arch…ug_rows）与 pairs/eng/quiz 同法：
        # 归属最近的 section.module，模块关闭时随 module_stats 一并结算
        if tag == 'section' and 'module' in classes:
            self.module_stack.append({'id': a.get('id'), 'hero': 'hero' in classes,
                                      'pairs': 0, 'eng': 0, 'quiz': 0, 'cg': 0,
                                      'arch': 0, 'runchain': 0, 'rc_steps': 0,
                                      'arch_marks': 0,
                                      'card': 0, 'card_rows': 0,
                                      'vardict': 0, 'vd_rows': 0, 'vc_nodes': 0,
                                      'design': 0, 'dq_rows': 0,
                                      'guide': 0, 'ug_rows': 0,
                                      'text': []})
        if 'callgraph-scene' in classes:
            self.cg_scenes += 1
        if self.module_stack:
            top = self.module_stack[-1]
            if 'translate-pair' in classes:
                top['pairs'] += 1
            if set(classes) & {'flow-scene', 'onion-scene', 'tower-scene',
                               'fork-scene', 'bet-scene', 'viz-scene',
                               'callgraph-scene'}:
                top['eng'] += 1
            if 'callgraph-scene' in classes:
                top['cg'] += 1
            if tag == 'div' and 'quiz' in classes and 'bet-scene' not in classes:
                top['quiz'] += 1
            self._skeleton_count(classes, a, top)

        # v1.19.0 检查 24/25 收集（v1.19.0 结构契约；全课级，不依赖模块段）
        if (a.get('data-ev') or '').strip() == 'measured':
            self.measured_claims.append({
                'files': a.get('data-ev-files') or '',
                'line': self.getpos()[0],
            })
        if 'build-run-card' in classes:
            self.build_cards += 1
        if 'build-cmd' in classes and self._in_ancestor('build-run-card'):
            self.build_cmds += 1
            cmd = (a.get('data-cmd') or '').strip()
            src = (a.get('data-src') or '').strip()
            if not cmd or not src:
                self.build_cmd_bad.append((self.getpos()[0],
                                           'data-cmd' if not cmd else
                                           'data-src'))
        if 'rebuild-path' in classes:
            self.rebuild_paths += 1
        if self._in_ancestor('rebuild-path') and 'data-step' in a:
            self.rb_steps.append(
                ((a.get('data-cycle') or '').strip() == 'true',
                 (a.get('data-step') or '').strip()))

        # script 块原文收集（检查 18：块文本内的字面标签序列会被浏览器截断）
        if tag == 'script':
            self._script_depth += 1
            self._script_text = []

        # JSON 数据块
        if tag == 'script' and a.get('type') == 'application/json':
            jcls = [c for c in classes
                    if c in ('viz-data', 'onion-data', 'tower-data', 'fork-data',
                             'callgraph-data', 'arch-data')]
            self._json_cls = jcls[0] if jcls else '(json)'
            self._json_buf = []
            mid = self.module_stack[-1]['id'] if self.module_stack else None
            self._json_where = '（模块 %s · L%d）' % (mid or '无归属',
                                                      self.getpos()[0])
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
        if self._script_depth:
            self._script_text.append(data)
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
        if self.module_stack and not self._md_skip:
            # 模块正文（供结业三件检查；代码样例不计——它们在 _md_skip 内）
            self.module_stack[-1]['text'].append(data)

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
        if tag == 'script' and self._script_depth:
            self._script_depth -= 1
            blob = ''.join(self._script_text)
            if ('<script' in blob) or ('</script' in blob):
                self.errors.append(
                    'script 块文本含字面标签序列 "<script"/"</script>"'
                    '（浏览器会在此截断或嵌套解析该块，注释与字符串请改用'
                    '无尖括号写法）——块结束于约 L%d' % self.getpos()[0])
        if tag == 'script' and self._json_cls is not None:
            raw = ''.join(self._json_buf)
            self._check_json(self._json_cls, raw, self._json_where)
            self._json_cls = None
            self._json_buf = []
            self._json_where = ''

    # ---- JSON 检查 ----
    def _check_json(self, cls, raw, where=''):
        try:
            data = json.loads(raw)
        except ValueError as e:
            self.errors.append('.%s JSON 解析失败%s：%s' % (cls, where, e))
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
        if cls == 'callgraph-data':
            callgraph_check(data, '.callgraph-data' + where, self.errors,
                            self.warnings)
        elif cls == 'arch-data':
            # v1.18.0：arch-data 走同一套调用图契约（多 module_marks 与节点数
            # 4–20）；归属标注条数记到当前模块，供检查 19 判「非空」（契约 §一.1）
            n_marks = arch_check(data, '.arch-data' + where, self.errors,
                                 self.warnings)
            if self.module_stack:
                self.module_stack[-1]['arch_marks'] += n_marks


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


# ---- 16. 调用图数据块契约（规格 callgraph-block-v1.13.1 §7 + B3 契约升级） ----
CG_CONFIDENCE = ('verified', 'inferred')
# about/call：节点级可选键（v1.13.4 前提，规格 §14a）。只许挂在 nodes[] 上，
# 出现即必须是有内容的字符串且有长度上限——事实面板一行放不下超长综述。
CG_ABOUT_MAX = 60   # 字
CG_CALL_MAX = 80    # 字
# v1.18.0 契约 §二 / §14a（C 条，向后兼容）：节点新增可选 desc（它做什么）/
# role（在系统里的角色），边新增可选 kind（闭集）/detail（怎么依赖、传什么）。
CG_DESC_MAX = 60    # 字
CG_ROLE_MAX = 40    # 字
CG_DETAIL_MAX = 80  # 字
CG_KINDS = ('owns', 'call', 'dependency', 'data', 'control')
# 契约 §一.1：arch-data 节点另有可选 view（视图分组闭集），callgraph-data 不收
# （普通调用图没有视图分组概念）。两侧口径分开，互不放宽。
CG_VIEWS = ('own', 'flow')

# B3 全键白名单（兑现 §14a「逐字段闭集」承诺）：nodes/links 键集以下两表为准，
# 出现契约外未知键即报错。links 白名单含 facts v3 派生字段（B2 移交②）
# resolved_by / resolution——它们是 B-P0-2/P0-4 消解诚实性字段的投影。
# v1.18.0 起并入 §14a 语义字段（desc/role → 节点，kind/detail → 边）。
CG_NODE_KEYS = frozenset(('id', 'label', 'kind', 'file', 'line',
                          'about', 'call', 'desc', 'role'))
CG_LINK_KEYS = frozenset(('from', 'to', 'count', 'confidence', 'file', 'line',
                          'declared', 'back', 'resolved_by', 'resolution',
                          'kind', 'detail'))
# arch-data 节点键集（契约 §一.1）：调用图节点全字段 + view
CG_ARCH_NODE_KEYS = CG_NODE_KEYS | frozenset(('view',))

# B3 契约升级（B2 移交②）：facts v3 消解字段在调用图数据里的语义机检。
# resolution：unique|ambiguous|unresolved|self_ref 四值闭集（facts 侧同源）；
# resolved_by：name|binding|qualified 三值闭集（实锤名/绑定/限定的证据来源）。
CG_RESOLUTIONS = ('unique', 'ambiguous', 'unresolved', 'self_ref')
CG_RESOLVED_BY = ('name', 'binding', 'qualified')


def _cg_str(v):
    return isinstance(v, str) and bool(v.strip())


def _cg_int(v):
    """int 且 ≥1；bool 是 int 的子类，必须排除。"""
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def _cg_resolution_check(e, i, where, errors):
    """B3：facts v3 派生边（携带 resolution/resolved_by 字段）的语义机检。

    四条谓词（各配注入必红变异体，见 agent-out/b3_negative_1134.py）：
      a. resolved_by 出现 → 必须 ∈ {name, binding, qualified}（闭集）；
      b. resolved_by ⟺ verified（证据来源只属于实锤边）；
      c. resolution=self_ref 的边禁入调用图数据（自引用形态必须剔除——
         跨 FFI 同名 / super 调用 / 真递归在这里只能画成契约禁止的自环）；
      d. resolution ∈ {unresolved, ambiguous} 恒 inferred（拒绝即未解析），
         标 verified 即错；resolution=unique 必须 verified 且带合法 resolved_by
         （facts 侧不变式 verified⟺resolved_by+to 的校验器侧接线；
         link 的 to 不可为空由既有「缺 to / to 不在 nodes」检查兜住）。
    """
    rb = e.get('resolved_by')
    if 'resolved_by' in e:
        if rb not in CG_RESOLVED_BY:
            errors.append('%s 调用图 links[%d] 的 resolved_by「%s」不在闭集 '
                          '{name, binding, qualified} 内'
                          % (where, i, rb if isinstance(rb, str) else rb))
        if e.get('confidence') != 'verified':
            errors.append('%s 调用图 links[%d] 不是 verified 边却带 resolved_by'
                          '（证据来源只属于实锤边）' % (where, i))
    if 'resolution' in e:
        res = e.get('resolution')
        if res not in CG_RESOLUTIONS:
            errors.append('%s 调用图 links[%d] 的 resolution「%s」不在闭集 '
                          '{unique, ambiguous, unresolved, self_ref} 内'
                          % (where, i, res if isinstance(res, str) else res))
            return
        if res == 'self_ref':
            errors.append('%s 调用图 links[%d] 的 resolution=self_ref——'
                          '自引用边禁入调用图数据（画出来即契约禁止的自环，'
                          '必须按 §14d SOP 剔除）' % (where, i))
        elif res in ('unresolved', 'ambiguous'):
            if e.get('confidence') != 'inferred':
                errors.append('%s 调用图 links[%d] 的 resolution=%s 恒 inferred'
                              '（拒绝即未解析，多候选收不窄不得标 verified）'
                              % (where, i, res))
        else:                                  # unique：verified + 证据来源
            if e.get('confidence') != 'verified' \
                    or rb not in CG_RESOLVED_BY:
                errors.append('%s 调用图 links[%d] 的 resolution=unique 必须'
                              ' verified 且带 resolved_by∈{name, binding, '
                              'qualified}（实锤边必须说明凭什么实锤）'
                              % (where, i))


# 同尾名告警的形态守卫：文件级/模块级节点的 id 是路径形态，其 split('.')
# 末段是扩展名（如 py）而非符号名——拿它比较会把任意两条同扩展名文件的边
# 误判成「疑似同一符号」。符号级 id（无 '/'、末段非扩展名）行为不变（D6-8②
# 语义保留）。此闭集与 resources/app.js 的 cgIsPathish 两侧口径必须同步演化。
_CG_TAIL_EXT = {
    'py', 'js', 'ts', 'tsx', 'jsx', 'go', 'rs', 'java', 'c', 'cc', 'cpp',
    'h', 'hpp', 'cs', 'rb', 'lua', 'php', 'kt', 'swift', 'm',
    'json', 'md', 'css',
}


def _cg_is_pathish(node_id):
    """id 是否为路径/文件形态（含 '/'，或 split 末段落在已知扩展名闭集）"""
    return '/' in node_id or node_id.rsplit('.', 1)[-1].lower() in _CG_TAIL_EXT


def _cg_top_keys_check(data, where, errors, allow_module_marks=False):
    """数据块顶层键集闭集（v1.18.0 契约 §二）。

    callgraph-data 顶层只允许 nodes/links；arch-data 另允许 module_marks
    （契约 §一.1：module_marks 是「仅 .arch-data 允许的第三个顶层键」）。
    """
    allowed = {'nodes', 'links'}
    if allow_module_marks:
        allowed.add('module_marks')
    unknown = sorted(set(data) - allowed)
    if unknown:
        errors.append('%s 顶层出现契约外键 %s（该数据块顶层只允许 %s）'
                      % (where, '/'.join(unknown), ', '.join(sorted(allowed))))


def callgraph_check(data, where, errors, warnings=None,
                    allow_module_marks=False, arch_mode=False):
    """调用图数据契约机检（规格 §7 四条 + v1.13.4 前提的 about/call 三检
    + B3 全键白名单与 facts v3 字段语义 + v1.18.0 §14a 语义字段）。

    每条独立成错、各自定位到具体节点/连线，便于"注入必红"逐条命中：
    坏 JSON 在 json.loads 处即返回（不落到这里）；缺 confidence、verified
    缺 line、node 缺 file、about 空串、about 超长、about 挂到 links 上、
    未知键、resolved_by 闭集外、self_ref 边、降级边标 verified、kind 出闭集、
    detail 超长、顶层多余键等各只命中对应那一条。
    v1.18.0：nodes 增可选 desc(≤60)/role(≤40)，links 增可选 kind(闭集)/detail(≤80)；
    顶层键集闭集（callgraph-data 只允许 nodes/links）。
    """
    if not isinstance(data, dict):
        errors.append('%s 顶层必须是对象（含 nodes/links）' % where)
        return
    # v1.18.0 契约 §二：顶层键集闭集（callgraph-data 只允许 nodes/links；
    # arch-data 由 arch_check 以 allow_module_marks=True 放开第三个键）
    _cg_top_keys_check(data, where, errors, allow_module_marks)
    nodes = data.get('nodes')
    links = data.get('links')
    if not isinstance(nodes, list) or not nodes:
        errors.append('%s 缺 nodes[]（或为空）——调用图至少一个节点' % where)
        return
    if not isinstance(links, list):
        errors.append('%s 缺 links[]（引用清单；没有边时写 []）' % where)
        links = []

    ids = set()
    for i, n in enumerate(nodes, 1):
        if not isinstance(n, dict):
            errors.append('%s nodes[%d] 不是对象' % (where, i))
            continue
        # B3 全键白名单：逐字段闭集（§14a「键集以下两表为准」的校验器兑现）
        # arch_mode（arch-data）下节点另允许 view（契约 §一.1）
        node_keys = CG_ARCH_NODE_KEYS if arch_mode else CG_NODE_KEYS
        unknown = sorted(set(n) - node_keys)
        if unknown:
            who0 = n.get('id') if isinstance(n.get('id'), str) else '#%d' % i
            errors.append('%s 调用图节点「%s」出现契约外键 %s'
                          '（§14a 逐字段闭集：节点只允许 %s）'
                          % (where, who0, '/'.join(unknown),
                             ', '.join(sorted(node_keys))))
        nid = n.get('id')
        if _cg_str(nid):
            who = nid
            if nid in ids:
                errors.append('%s nodes[%d] 的 id「%s」重复（id 必须唯一）'
                              % (where, i, nid))
            ids.add(nid)
        else:
            who = nid if isinstance(nid, str) else '#%d' % i
            errors.append('%s nodes[%d] 缺 id' % (where, i))
        # 4. 每个 node 必须有 file 与 line（调用图不允许无出处的节点）
        if not _cg_str(n.get('file')):
            errors.append('%s 调用图节点「%s」缺 file'
                          '（调用图不允许无出处的节点）' % (where, who))
        if not _cg_int(n.get('line')):
            errors.append('%s 调用图节点「%s」缺 line（或不是 ≥1 的整数）'
                          % (where, who))
        # 5. about / call（v1.13.4 前提）+ desc / role（v1.18.0 §14a）：可选键，
        #    出现即必须是非空字符串且限长（about ≤60 / call ≤80 / desc ≤60 /
        #    role ≤40）；逐节点定位，缺谁报谁
        for key, cap in (('about', CG_ABOUT_MAX), ('call', CG_CALL_MAX),
                         ('desc', CG_DESC_MAX), ('role', CG_ROLE_MAX)):
            if key not in n:
                continue
            v = n[key]
            if not isinstance(v, str) or not v.strip():
                errors.append('%s 调用图节点「%s」的 %s 不是非空字符串'
                              '（可选键：要么不写，写就写有内容的）'
                              % (where, who, key))
            elif len(v) > cap:
                errors.append('%s 调用图节点「%s」的 %s 超长（%d 字 > 上限 %d 字'
                              '——事实面板一行放不下，综述请精简）'
                              % (where, who, key, len(v), cap))
        # arch-data 专属：view 视图分组（契约 §一.1 闭集 own/flow）
        if arch_mode and 'view' in n:
            view = n.get('view')
            if view not in CG_VIEWS:
                errors.append('%s 调用图节点「%s」的 view「%s」不在闭集 '
                              '{own, flow} 内（架构图节点的视图分组：own=自身'
                              '拥有的，flow=数据流经过的）'
                              % (where, who, view))

    for i, e in enumerate(links, 1):
        if not isinstance(e, dict):
            errors.append('%s links[%d] 不是对象' % (where, i))
            continue
        # B3 全键白名单：links 键集闭集（含 facts v3 派生字段 resolved_by/resolution）
        unknown = sorted(set(e) - CG_LINK_KEYS)
        if unknown:
            errors.append('%s 调用图 links[%d] 出现契约外键 %s'
                          '（§14a 逐字段闭集：边只允许 %s）'
                          % (where, i, '/'.join(unknown),
                             ', '.join(sorted(CG_LINK_KEYS))))
        # 6. about / call 是节点级字段：不允许挂在 links[] 上（防载荷膨胀——
        #    边可能成倍于节点，且边的「作用」本就是节点 about 的内容）
        for key in ('about', 'call'):
            if key in e:
                errors.append('%s 调用图 links[%d] 出现了 %s'
                              '（about/call 只允许出现在 nodes[] 的节点上）'
                              % (where, i, key))
        # 7. kind / detail（v1.18.0 契约 §二 / §14a 的边级语义字段）：
        #    kind 闭集（缺省视为 call，写出来就必须合法）；detail 出现即
        #    非空字符串且 ≤80 字（事实面板一行的长度）。
        if 'kind' in e:
            kind = e.get('kind')
            if not _cg_str(kind) or kind not in CG_KINDS:
                errors.append('%s 调用图 links[%d] 的 kind「%s」不在闭集 '
                              '{owns, call, dependency, data, control} 内'
                              '（缺省按 call 处理，写出来就必须在闭集内）'
                              % (where, i, kind))
        if 'detail' in e:
            detail = e.get('detail')
            if not _cg_str(detail):
                errors.append('%s 调用图 links[%d] 的 detail 不是非空字符串'
                              '（可选键：要么不写，写就写有内容的）' % (where, i))
            elif len(detail) > CG_DETAIL_MAX:
                errors.append('%s 调用图 links[%d] 的 detail 超长（%d 字 > 上限 '
                              '%d 字——事实面板一行放不下，依赖说明请精简）'
                              % (where, i, len(detail), CG_DETAIL_MAX))
        # 2. from / to / confidence 三者齐全且合法
        for k in ('from', 'to', 'confidence'):
            if not _cg_str(e.get(k)):
                errors.append('%s 调用图 links[%d] 缺 %s' % (where, i, k))
        conf = e.get('confidence')
        if _cg_str(conf) and conf not in CG_CONFIDENCE:
            errors.append('%s 调用图 links[%d] 的 confidence「%s」不在闭集 '
                          '{verified, inferred} 内' % (where, i, conf))
        frm, to = e.get('from'), e.get('to')
        for k, v in (('from', frm), ('to', to)):
            if _cg_str(v) and v not in ids:
                errors.append('%s 调用图 links[%d].%s「%s」在 nodes[].id 中不存在'
                              % (where, i, k, v))
        if _cg_str(frm) and frm == to:
            errors.append('%s 调用图 links[%d] 是自环（from == to，规格禁止）'
                          % (where, i))
        elif _cg_str(frm) and _cg_str(to) and warnings is not None \
                and not _cg_is_pathish(frm) and not _cg_is_pathish(to) \
                and frm.split('.')[-1] == to.split('.')[-1]:
            # D6-8②：两端 id 不同但末段名相同——facts 里带 self_ref 的边
            # （如同一符号被写成「限定名 → 末段名」）就是这种形态，必须剔除。
            # 形态守卫：文件级/模块级 id（含 '/' 或末段为扩展名）不参与本
            # 告警——它们的 split 末段是 py/js 这类扩展名而非符号名，否则
            # 任意两条同扩展名文件的边都会被误报（口径见 _cg_is_pathish）。
            warnings.append('%s 调用图 links[%d]（%s → %s）两端末段名相同，'
                            '很可能是同一符号的自环（analyze 产物里 self_ref: true '
                            '的边必须剔除），请人工核对' % (where, i, frm, to))
        # B3：facts v3 派生字段的语义机检（B2 移交②）
        _cg_resolution_check(e, i, where, errors)
        # 3. verified link 必须有 file 与 line
        if conf == 'verified':
            pair = '%s → %s' % (frm, to)
            if not _cg_str(e.get('file')):
                errors.append('%s 调用图 links[%d]（%s）标了 verified 却没有 '
                              'file——实锤边必须给出发起行' % (where, i, pair))
            if not _cg_int(e.get('line')):
                errors.append('%s 调用图 links[%d]（%s）标了 verified 却没有 '
                              'line——实锤边必须给出发起行' % (where, i, pair))


# ---- v1.18.0：arch-data（仓库总架构图）数据契约（契约 §一.1） ----
CG_NODE_MIN = 4      # 架构图节点 4–20（少于 4 看不清全貌）
CG_NODE_MAX = 20     # 多于 20 该按模块聚合收口
ARCH_MARK_KEYS = frozenset(('id', 'label', 'covers'))


def arch_check(data, where, errors, warnings=None):
    """.arch-data（v1.18.0 契约 §一.1 仓库总架构图）的数据校验。

    复用调用图同一套契约（键集白名单含 desc/role/kind/detail、出处、confidence
    闭集、禁自环、self_ref 剔除、facts v3 字段语义），差异只有三处：
      ① 顶层额外允许 module_marks（数组，每项 {id, label, covers[]}）；
      ② 节点数 4–20（架构图粒度口径）；
      ③ 节点另允许 view（闭集 own/flow，契约 §一.1；callgraph-data 不收）。
    covers[] 每一项必须命中 nodes[].id——「模块归属标注」必须指向真实节点。

    返回 module_marks 条数（缺失或为空返回 0），供检查 19 判「归属标注非空」。
    """
    if not isinstance(data, dict):
        errors.append('%s 顶层必须是对象（含 nodes/links/module_marks）' % where)
        return 0
    nodes = data.get('nodes')
    if isinstance(nodes, list) and not (CG_NODE_MIN <= len(nodes) <= CG_NODE_MAX):
        errors.append('%s 节点 %d 个不在 %d–%d 区间（架构图粒度：少于 %d 看不清'
                      '全貌，多于 %d 该按模块聚合收口）'
                      % (where, len(nodes), CG_NODE_MIN, CG_NODE_MAX,
                         CG_NODE_MIN, CG_NODE_MAX))
    callgraph_check(data, where, errors, warnings, allow_module_marks=True,
                    arch_mode=True)
    marks = data.get('module_marks')
    if marks is None:
        return 0
    if not isinstance(marks, list) or not marks:
        errors.append('%s module_marks 必须是非空数组（每项 {id, label, '
                      'covers[]}；不画模块归属时整个键省略）' % where)
        return 0
    ids = set()
    if isinstance(nodes, list):
        ids = set(n.get('id') for n in nodes
                  if isinstance(n, dict) and _cg_str(n.get('id')))
    for i, mk in enumerate(marks, 1):
        if not isinstance(mk, dict):
            errors.append('%s module_marks[%d] 不是对象' % (where, i))
            continue
        unknown = sorted(set(mk) - ARCH_MARK_KEYS)
        if unknown:
            errors.append('%s module_marks[%d] 出现契约外键 %s'
                          '（只允许 id/label/covers）'
                          % (where, i, '/'.join(unknown)))
        if not _cg_str(mk.get('id')):
            errors.append('%s module_marks[%d] 缺 id（模块锚点，非空字符串）'
                          % (where, i))
        if not _cg_str(mk.get('label')):
            errors.append('%s module_marks[%d] 缺 label（模块名，非空字符串）'
                          % (where, i))
        covers = mk.get('covers')
        if not isinstance(covers, list) or not covers:
            errors.append('%s module_marks[%d] 的 covers 必须是非空数组'
                          '（该模块覆盖架构图上的哪些节点）' % (where, i))
            continue
        for c in covers:
            if not _cg_str(c) or c not in ids:
                errors.append('%s module_marks[%d] 的 covers 元素「%s」不是 '
                              'nodes[].id（模块归属标注必须指向真实节点）'
                              % (where, i, c))
    return len(marks)


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

# 结业收束段（P1-f）：id 含 finale 即认定；豁免档位数量下限，改走「结业三件」。
# 标记集是**已文档化的机检契约**（workflow §8 同列），刻意收全自然措辞——R6 实测稿
# 用的是「串回一条线 / 主线回放 / 一句话总结」，短表会误报
FINALE_ID_MARK = 'finale'
FINALE_RECAP_KEYS = ('回顾', '回放', '回望', '回主线', '主线', '串联', '串起',
                     '串回', '一条线', '小结', '总结', '复盘', '收束', '贯穿')
FINALE_NEXT_KEYS = ('下一步', '接下来', '继续', '延伸', '后续')


def is_finale(module):
    """是否结业收束段（workflow §8：结业段允许轻量）。"""
    mid = module.get('id') or ''
    return FINALE_ID_MARK in mid.lower()


def finale_check(module_stats, errors):
    """结业收束段的「结业三件」专用检查（P1-f，与 workflow §8 文本契约同源）。

    结业段豁免档位数量下限后，改用三件套核对：主线回顾 / 跨模块综合题 /
    下一步指引——三件缺一即红（README 与 workflow §8 已写明机检口径）。
    """
    for m in module_stats:
        if not is_finale(m):
            continue
        label = '结业段[%s]' % m['id']
        text = ''.join(m.get('text') or ())
        if not any(k in text for k in FINALE_RECAP_KEYS):
            errors.append('%s 缺「主线回顾」（§8 结业三件之一：正文需出现 %s 之一）'
                          % (label, '/'.join(FINALE_RECAP_KEYS)))
        if m['quiz'] < 1:
            errors.append('%s 缺「跨模块综合题」（§8 结业三件之一）' % label)
        if not any(k in text for k in FINALE_NEXT_KEYS):
            errors.append('%s 缺「下一步指引」（§8 结业三件之一：正文需出现 %s 之一）'
                          % (label, '/'.join(FINALE_NEXT_KEYS)))


def callgraph_coverage_check(module_stats, errors):
    """调用图前置结构契约（workflow 第 5 步「调用图前置」，v1.14.0 起）。

    封面（hero）必须含 ≥1 张全项目调用图；每个正式模块（非封面、非结业段）
    开头必须含 ≥1 张本模块调用图。结业段豁免——由 finale_check 三件套
    专用口径把关（豁免口径与 tier_check 一致）。
    """
    for m in module_stats:
        if m['hero']:
            if m['cg'] < 1:
                errors.append('封面[%s] 缺全项目调用图（workflow 第 5 步'
                              '「调用图前置」：封面必须放模块/文件粒度的'
                              '全项目调用图）' % (m['id'] or '?'))
        elif m['id'] and not is_finale(m):
            if m['cg'] < 1:
                errors.append('模块[%s] 缺前置调用图（workflow 第 5 步'
                              '「调用图前置」：每个正式模块开头必须放'
                              '本模块调用图）' % m['id'])


# ---- 19-23. 理解骨架六件（v1.18.0 结构契约，见 agent-out/b118-contract.md §一/§三） ----
# 阈值集中在此，与契约表逐行对照。--tier 未给时 22/23 走 L1 下限；19/20/21
# 常开，与档位无关（契约 §三「触发范围」列）。
SKEL_RC_STEPS = 4       # 一次完整运行链路至少 4 步
SKEL_CARD_ROWS = 4      # 三句话卡四行齐全（问题/输入/输出/在总架构图上的位置）
SKEL_VC_NODES = 2       # 变量生命周期链至少 2 个节点
SKEL_DQ_ROWS = 4        # 设计四问四问齐全（做什么/为什么/不这么做/为什么不用更简单）
SKEL_DESIGN_TIER = {'L1': 1, 'L2': 2, 'L3': 3}   # 每正式模块 .design-qa 块数
SKEL_UG_TIER = {'L1': 4, 'L2': 6, 'L3': 6}       # 结业段 .ug-row[data-task] 条数
SKEL_RB_STEPS = 4                                # .rebuild-path 步骤下限（v1.19.0 §2.6）


def _skel_floor(table, tier):
    """档位下限查询：tier 在闭集内取值，--tier 未给或非法回落 L1 下限。"""
    return table.get(tier if tier in table else 'L1')


def arch_scene_check(module_stats, errors):
    """19. 封面「仓库总架构图 + 一次完整运行链路」（S1 开场双件，常开）。

    封面（hero 段）必须 ≥1 张 .arch-scene（复用调用图引擎的全项目架构图）
    且 ≥1 条 .run-chain（对象级时序），链内 .rc-step ≥4 步——缺一即红。
    另：课程存在多个正式模块时，封面总架构图的 module_marks 不得为空
    （S1 三视图之一的「模块归属标注」；条数由 arch_check 记到模块上）。
    """
    formal = [m for m in module_stats
              if m['id'] and not m['hero'] and not is_finale(m)]
    for m in module_stats:
        if not m['hero']:
            continue
        label = '封面[%s]' % (m['id'] or '?')
        if m.get('arch', 0) < 1:
            errors.append('%s 缺仓库总架构图（v1.18.0 结构契约：封面必须放 ≥1 张 '
                          '.arch-scene 全项目架构图，先回答「这个仓库由哪些部分'
                          '组成、谁依赖谁」）' % label)
        elif m.get('arch_marks', 0) < 1 and len(formal) >= 2:
            errors.append('%s 总架构图缺模块归属标注（.arch-data 的 module_marks '
                          '为空——S1 三视图之一：每个课程模块覆盖架构图上的哪些'
                          '节点）' % label)
        if m.get('runchain', 0) < 1:
            errors.append('%s 缺一次完整运行链路（.run-chain：开场要用对象级时序'
                          '走完一次完整运行，不是模块清单）' % label)
        elif m.get('rc_steps', 0) < SKEL_RC_STEPS:
            errors.append('%s 运行链路 .rc-step 仅 %d 步 < %d（少于 %d 步走不完'
                          '一次完整运行：每个 rc-step 是一个对象级动作）'
                          % (label, m.get('rc_steps', 0), SKEL_RC_STEPS,
                             SKEL_RC_STEPS))


def module_card_check(module_stats, errors):
    """20. 每个正式模块的「三句话卡」（.module-card，常开）。

    每正式模块（非封面、非结业段）≥1 张卡，且卡内 .mc-row ≥4（四行齐全：
    解决什么问题 / 输入是什么 / 输出是什么 / 在总架构图上的位置）。
    行数按卡内统计——卡外游离的 .mc-row 不计（不能替卡片充数）。
    """
    for m in module_stats:
        if m['hero'] or not m['id'] or is_finale(m):
            continue
        label = '模块[%s]' % m['id']
        card = m.get('card', 0)
        rows = m.get('card_rows', 0)
        if card < 1:
            errors.append('%s 缺三句话卡（.module-card：每个正式模块至少 1 张，'
                          '回答「解决什么问题 / 输入是什么 / 输出是什么 / 在'
                          '总架构图上的位置」）' % label)
        elif rows < SKEL_CARD_ROWS * card:
            errors.append('%s 三句话卡内容不全：.mc-row %d 行 < %d（%d 张卡 × '
                          '%d 行，四行齐全才算）'
                          % (label, rows, SKEL_CARD_ROWS * card, card,
                             SKEL_CARD_ROWS))


def vardict_check(module_stats, errors):
    """21. 变量词典与变量生命周期链（.vardict-scene，常开）。

    全课 ≥1 个 .vardict-scene；每个场景内 .vardict-row[data-var][data-stage]
    ≥1（缺 data-var/data-stage 的行不计）且 .var-chain 内 .vc-node[data-var]
    ≥2（变量之间的传递关系要画成链）。

    场景内行数由模块级聚合口径把关：每个场景至少要贡献 1 行 / 2 节点，故
    模块内 vd_rows < 场景数、或 vc_nodes < 2×场景数，即存在空场景/缺链条。
    """
    if sum(m.get('vardict', 0) for m in module_stats) < 1:
        errors.append('全课缺变量词典（.vardict-scene ≥1：变量词典是 v1.18.0 '
                      '理解骨架六件之一，A3 变量表与 A4 生命周期链的合并载体）')
    for m in module_stats:
        scenes = m.get('vardict', 0)
        if not scenes:
            continue
        label = '模块[%s]' % (m['id'] or '?')
        rows = m.get('vd_rows', 0)
        nodes = m.get('vc_nodes', 0)
        if rows < scenes:
            errors.append('%s 变量词典有空场景：.vardict-row[data-var]'
                          '[data-stage] %d 行 < %d 个场景（每个场景至少 1 行；'
                          '属性不全的行不计）' % (label, rows, scenes))
        if nodes < SKEL_VC_NODES * scenes:
            errors.append('%s 变量词典缺生命周期链：.var-chain 内 .vc-node'
                          '[data-var] %d 个 < %d（%d 个场景 × %d 节点）'
                          % (label, nodes, SKEL_VC_NODES * scenes, scenes,
                             SKEL_VC_NODES))


def design_qa_check(module_stats, tier, errors):
    """22. 每个正式模块的「设计四问」块（.design-qa）。

    块数下限随档位加严：L1 ≥1 / L2 ≥2 / L3 ≥3（--tier 未给按 L1）；每块内
    .dq-row ≥4（做什么 / 为什么这么做 / 不这么做会怎样 / 为什么不用更简单的
    方法，缺项不算——行数按块内统计）。结业段不参与（由检查 23 把关）。
    """
    floor = _skel_floor(SKEL_DESIGN_TIER, tier)
    for m in module_stats:
        if m['hero'] or not m['id'] or is_finale(m):
            continue
        label = '模块[%s]' % m['id']
        blocks = m.get('design', 0)
        rows = m.get('dq_rows', 0)
        if blocks < floor:
            errors.append('%s 设计四问 %d 块 < %d（档位 %s：每个正式模块至少 '
                          '%d 个 .design-qa——只讲「是什么」不算理解，要能回答'
                          '设计取舍）'
                          % (label, blocks, floor, tier or 'L1（缺省）', floor))
        elif rows < SKEL_DQ_ROWS * blocks:
            errors.append('%s 设计四问缺项：.dq-row %d 行 < %d（%d 块 × %d 问：'
                          '做什么/为什么这么做/不这么做会怎样/为什么不用更简单'
                          '的方法，四问齐全才算）'
                          % (label, rows, SKEL_DQ_ROWS * blocks, blocks,
                             SKEL_DQ_ROWS))


def upgrade_guide_check(module_stats, tier, errors):
    """23. 结业段的「改造指南」（.upgrade-guide，结业段内）。

    结业段（id 含 finale）内 ≥1 张 .upgrade-guide，且 .ug-row[data-task]
    ≥4（L1）／≥6（L2、L3，--tier 未给按 L1）——读完要能上手改：想做的事
    对应去哪儿改。行数按表内统计，缺 data-task 的行不计。
    """
    floor = _skel_floor(SKEL_UG_TIER, tier)
    for m in module_stats:
        if not is_finale(m):
            continue
        label = '结业段[%s]' % m['id']
        guides = m.get('guide', 0)
        rows = m.get('ug_rows', 0)
        if guides < 1:
            errors.append('%s 缺改造指南（.upgrade-guide：结业段要给「想做的事 '
                          '→ 去哪儿改」的操作表，与主线回顾/综合题并列）'
                          % label)
        elif rows < floor:
            errors.append('%s 改造指南条目 %d < %d（档位 %s：.ug-row[data-task] '
                          '至少 %d 条；缺 data-task 的行不计）'
                          % (label, rows, floor, tier or 'L1（缺省）', floor))


def _norm_rel(p):
    """仓库相对路径归一：剥空白、统一正斜杠、剥 ./ 前缀（检查 24 键匹配用）。"""
    p = (p or '').strip().replace('\\', '/')
    while p.startswith('./'):
        p = p[2:]
    return p


def measured_check(claims, trace_path, errors):
    """24. 实测主张锚定（v1.19.0 §2.5）。

    data-ev="measured" 的元素主张「这一步被真实运行轨迹覆盖」，其证据链：
      24a  本次校验必须提供 --trace-facts（trace-facts-v2 采集文件）；
      24b  每处主张的 data-ev-files（分号分隔的仓库相对路径）都必须出现在
           trace.files 且命中行数 ≥1；
      无 data-ev-files 配套的主张没有可核验的文件支撑，同样 ERROR（空主张）。
    无 data-ev 属性 → 整体跳过（向后兼容，v1.18 课零影响）。
    """
    if not claims:
        return
    if not trace_path:
        errors.append(
            '实测主张缺证据：data-ev="measured" 共 %d 处，但本次校验未提供 '
            '--trace-facts（动态取证文件）——要么带轨迹复跑，要么降级为'
            '推断徽标（移除该属性）' % len(claims))
        return
    try:
        with open(trace_path, 'r', encoding='utf-8') as f:
            trace = json.load(f)
    except (OSError, ValueError) as e:
        errors.append('--trace-facts 文件无法解析（%s）：%s' % (trace_path, e))
        return
    if not isinstance(trace, dict) or trace.get('schema') != 'trace-facts-v2':
        errors.append('--trace-facts 的 schema 不是 trace-facts-v2：%r'
                      % (trace.get('schema') if isinstance(trace, dict)
                         else type(trace).__name__))
        return
    files = trace.get('files') or {}
    if not isinstance(files, dict):
        errors.append('--trace-facts 的 files 不是对象（trace-facts-v2 契约）')
        return
    for c in claims:
        label = '约 L%d' % c.get('line', 0)
        declared = [x for x in (c.get('files') or '').split(';') if x.strip()]
        if not declared:
            errors.append('实测主张缺文件声明：%s 的 data-ev="measured" 未带 '
                          'data-ev-files（无文件支撑的实测主张不可锚定）' % label)
            continue
        for f in declared:
            key = _norm_rel(f)
            lines = files.get(key)
            if lines is None:
                errors.append(
                    '实测主张文件不在轨迹中：%s 声明 %s，--trace-facts 的 '
                    'files 里没有这个键（采集命令是否覆盖了它？）' % (label, f))
            elif not any(isinstance(n, int) and n > 0
                         for n in (lines if isinstance(lines, list) else [])):
                errors.append('实测主张零命中：%s 声明 %s 在轨迹中命中行数 0'
                              % (label, f))


def buildcard_check(chk, errors):
    """25. 构建卡/复刻线段结构（v1.19.0 §2.6，段缺位即跳过）。

    .build-run-card 段在场时：段内 ≥1 个 .build-cmd 行，且每行 data-cmd、
    data-src 非空（构建命令必须带证据文件出处）。
    .rebuild-path 段在场时：段内带 data-step 的步骤 ≥4 个，编号从 1 起连续
    递增（data-cycle="true" 的环块步骤并列模块，计入总数、不参与递增校验）。
    两段都缺位 → 不检查（不强制进入理解骨架六件）。
    """
    n = 0
    if getattr(chk, 'build_cards', 0):
        if not chk.build_cmds:
            errors.append('.build-run-card 缺 .build-cmd 行（至少 1 条构建'
                          '命令：data-cmd 命令本体 + data-src 证据文件）')
            n += 1
        for line, which in chk.build_cmd_bad:
            errors.append('.build-cmd（约 L%d）缺 %s（命令与证据文件都要有）'
                          % (line, which))
            n += 1
    if getattr(chk, 'rebuild_paths', 0):
        steps = chk.rb_steps
        if len(steps) < SKEL_RB_STEPS:
            errors.append('.rebuild-path 步骤仅 %d 个 < %d（复刻线至少要走完'
                          ' %d 步：拉仓库、装依赖、构建、跑起来）'
                          % (len(steps), SKEL_RB_STEPS, SKEL_RB_STEPS))
            n += 1
        seq = []
        bad_num = False
        for cyc, raw_v in steps:
            if cyc:
                continue
            try:
                seq.append(int(raw_v))
            except ValueError:
                errors.append('.rebuild-path 步骤 data-step 不是整数：%r'
                              % raw_v)
                n += 1
                bad_num = True
                break
        if not bad_num and seq and seq != list(range(1, len(seq) + 1)):
            errors.append('.rebuild-path 步骤编号错乱（data-step 应从 1 起连续'
                          '递增，实测 %s）' % seq[:8])
            n += 1
    return n


def tier_check(module_stats, tier, errors):
    rule = TIER_RULES.get(tier)
    if rule is None:
        return
    for m in module_stats:
        if m['hero'] or not m['id']:
            continue   # 封面不参与内容量下限
        if is_finale(m):
            continue   # P1-f：结业段豁免档位下限，由 finale_check 专用口径把关
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
    opts = {'--source': None, '--tier': None, '--trace-facts': None}
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
    # 既有缺陷修复：解析器侧告警（JSON 实体字面 / 调用图同尾名自环）原先被静默丢弃——
    # 只 extend 了 errors，没接 warnings；D6-8② 的新门线依赖这条接线
    warnings.extend(chk.warnings)

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

    # 11b. 结业收束段「结业三件」（P1-f：与 --tier 无关的内容契约）
    finale_check(chk.module_stats, errors)

    # 17. 调用图前置（封面全项目图 + 每正式模块模块图；v1.14.0 结构契约）
    callgraph_coverage_check(chk.module_stats, errors)

    # 19-23. 理解骨架六件（v1.18.0 结构契约 §三）。每件独立结算错误数，
    # 汇总行与检查 17 同处，逐件打印 ✓/✗ 与计数。
    skel_err = []
    for skel_fn, extra in ((arch_scene_check, ()), (module_card_check, ()),
                           (vardict_check, ()),
                           (design_qa_check, (opts['--tier'],)),
                           (upgrade_guide_check, (opts['--tier'],))):
        n0 = len(errors)
        skel_fn(chk.module_stats, *extra, errors)
        skel_err.append(len(errors) - n0)

    # 24. 实测主张锚定（v1.19.0 §2.5；无 data-ev 属性即跳过）
    n24 = len(errors)
    measured_check(getattr(chk, 'measured_claims', []), opts['--trace-facts'],
                   errors)
    err24 = len(errors) - n24

    # 25. 构建卡/复刻线段结构（v1.19.0 §2.6；段缺位即跳过）
    n25 = len(errors)
    err25 = buildcard_check(chk, errors)
    err25 = len(errors) - n25

    def _skel_tot(key):
        return sum(m.get(key, 0) for m in chk.module_stats)

    def _skel_mark(i):
        return '✓' if not skel_err[i] else '✗'

    skel_line = (
        '理解骨架（19-23）：架构图 %d 张 %s / 运行链 %d 条 %d 步 %s / '
        '模块卡 %d 张 %d 行 %s / 变量词典 %d 个 %d 行 %d 节点 %s / '
        '设计四问 %d 块 %d 行 %s / 改造指南 %d 个 %d 行 %s'
        % (_skel_tot('arch'), _skel_mark(0),
           _skel_tot('runchain'), _skel_tot('rc_steps'), _skel_mark(0),
           _skel_tot('card'), _skel_tot('card_rows'), _skel_mark(1),
           _skel_tot('vardict'), _skel_tot('vd_rows'), _skel_tot('vc_nodes'),
           _skel_mark(2),
           _skel_tot('design'), _skel_tot('dq_rows'), _skel_mark(3),
           _skel_tot('guide'), _skel_tot('ug_rows'), _skel_mark(4)))

    dyn_line = (
        '动态取证（24-25）：实测主张 %d 处 %s / 构建卡 %d 张 %d 条命令 %s / '
        '复刻线 %d 条 %d 步 %s'
        % (len(getattr(chk, 'measured_claims', [])),
           '✓' if not err24 else '✗',
           getattr(chk, 'build_cards', 0), getattr(chk, 'build_cmds', 0),
           '✓' if not err25 else '✗',
           getattr(chk, 'rebuild_paths', 0), len(getattr(chk, 'rb_steps', [])),
           '✓' if not err25 else '✗'))

    quiet = '--quiet' in flags
    if not quiet:
        print('文件：%s（%.1f KB）' % (path, len(raw.encode("utf-8")) / 1024))
        print('检查：翻译块 %d 个 / 测验+赌注 %d 处 / JSON 块见上 / 模块 %d 个 / 调用图 %d 张'
              % (len(chk.pairs), len(chk.quizzes), len(chk.modules), chk.cg_scenes))
        print(skel_line)
        print(dyn_line)
    for w in warnings:
        print('  ⚠️  %s' % w)
    for e in errors:
        print('  ✖ %s' % e)
    if not quiet:
        if errors:
            print('结果：✖ %d 个错误，%d 条告警' % (len(errors), len(warnings)))
        elif warnings:
            print('结果：⚠️ 通过（%d 条告警待人工判定）' % len(warnings))
        else:
            print('结果：✅ 全部通过')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
