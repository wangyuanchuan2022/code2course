#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_structure.py — code2course 结构事实底稿生成器（零依赖，Python 3.8+ 纯标准库）

用法：
    python analyze_structure.py <repo> [--lang auto|<id>[,<id>...]]
                                [--exclude A,B,...] [--outdir DIR] [--quiet]
    python analyze_structure.py analyze <repo> [同上]        # 显式子命令形式（等价 v1）
    python analyze_structure.py --selftest                   # 兼容转发入口：自测实现
                                                             # 位于 tests/test_analyze_structure.py
                                                             # （缺测试文件时退出 2）

查询层（F8/F9，纯只读，不写任何文件；facts 缺省取 <cwd>/structure-facts/structure-facts.json）：
    python analyze_structure.py map      [--facts F] [--dir P] [--depth N] [--files]
                                        [--include-inferred] [--format md|json]
    python analyze_structure.py callers  <symbol> [--facts F] [--exact] [--limit N]
                                        [--include-inferred] [--format md|json]
    python analyze_structure.py callees  <symbol> [--facts F] [--exact] [--limit N]
                                        [--include-inferred] [--format md|json]
    python analyze_structure.py impact   <symbol> [--facts F] [--depth N] [--exact]
                                        [--include-inferred] [--format md|json]
    python analyze_structure.py path     <a> <b> [--facts F] [--exact]
                                        [--include-inferred] [--format md|json]
    python analyze_structure.py entry    [--facts F] [--kind K] [--format md|json]
    python analyze_structure.py search   <keyword> [--facts F] [--in symbol|file|call|all]
                                        [--limit N] [--format md|json]

查询退出码：0 查询完成（含无结果）/ 1 facts 读不到、JSON 非法或 schema_version
不匹配（响亮失败）/ 2 用法错误（缺 <symbol>、--depth 非整数、--in 值非法等）。

产物（写入 <outdir>，缺省 <cwd>/structure-facts）：
    structure-facts.json — 机器可读五件套（schema_version=3，顶层键恰好 12 个）
    structure-facts.md   — 人读底稿（固定小节：文件清单 / 符号表 / 依赖边（import）/
                           调用边 / 断点清单（Where the graph stops）/ 入口点 /
                           解析失败与警告 / 诚实性声明）

说明：
  * 五件套 = 文件清单 / 符号表 / import 边 / 调用边 / 入口点。facts 顶层另有
    engine_version（整数，提取引擎内容版本，与 schema_version 的形状契约相互独立；
    bump 规则见常量定义处注释）。
  * 语言面：16 门 Tier-1 全部接入（F5）。python 走 ast 模块确定性提取（extractor: ast）；
    其余 15 门走表驱动启发式引擎（brace = 大括号系 / end = end 块系，extractor 如实标注），
    每门语言一张模式表（LANG_TABLES），token 正则借鉴 Pygments 2.21.0 lexer（见文末出处注记）。
    已知盲区见产物 MD 末尾的诚实性声明与 F5 各语言盲区列。
  * 边诚实性（v3 消解口径）：verified（实锤）只发给「目标可唯一指认」的调用边，且必带
    resolved_by 证据来源——实锤(名)=末段名唯一命中（或多候选经同文件唯一收窄）；
    实锤(绑定)=经 import 绑定收窄，或含点属性链的链根在本文件有绑定且末段名唯一命中；
    实锤(限定)=receiver+callee 限定名精确命中。以下一律 inferred（推断）：末段名多候选
    且收不窄（拒绝即未解析；边带 to_candidates 候选列表 ≤5 + candidates_total）；
    符号表未命中（边带 unresolved_reason：external / not_extracted_here /
    builtin_filtered）；自引用形态（caller 末段名 == callee——无条件降级并标 self_ref，
    真递归、super 基类调用与跨 FFI 同名自环静态不可分）；receiver 为含点属性链的边
    一律不凭名字判 verified。resolution 字段为四值闭集
    unique / ambiguous / unresolved / self_ref。内建/全局名只计入 filtered_calls，
    不逐条列出；(file, line, callee) 去重。calls[].caller 可为 null：模块级调用——
    调用点位于模块顶层、不属于任何函数/方法时的形态（正常形态而非缺失数据；
    真实仓库实测量级可达数千条）。
  * 同名候选上限 500（CANDIDATE_CAP）：尾名同名符号超过上限的调用边整条放弃
    （计 filtered_calls 并告警 name-cap-exceeded），防同名集合二次方扫描回潮。
  * 生成文件标注：files[].generated 按路径约定 + 文件头 banner 双信号标注
    （只标注不排除——解释噪声来源，不删数据；banner 只认注释行，窗口 60 行 / 8192 字符；
     banner 口径 v2：『@』词首的生成标记为强信号、单凭自身判定；其余生成/勿改词为弱信号、
     须同行另有自身指代词（this file / 本文件 一类）才判——防手写头注释引用他人生成物
     被误标；弱信号与指代词表均中英双语，词表见 GENERATED_ 常量）。
  * 默认排除清单按目录 basename 匹配（任意层级、大小写不敏感）；--exclude 为追加而非
    替换；排除在目录遍历阶段生效（被排除目录的探针在 files/symbols/imports/calls
    四处零出现）。
  * 被分析仓库零写入；产物确定性：同一仓库同一输入连跑两次字节一致（无时间戳、
    无绝对路径、所有列表按稳定键排序）。
  * 查询层子命令（F8/F9，1c）：map / callers / callees / impact / path / entry / search。
    进程内加载 facts → dict 索引，纯只读；符号参数先 qualname 精确、再末段名（--exact 只认
    精确）；impact / path 缺省只走 verified 边（D-41：推断边不进推理链），--include-inferred
    才纳且逐跳 / 逐层标注 confidence；map / callers / callees 属「列出事实」，两类都返回并
    分列计数；无结果 = found:false + exit 0；path 多解按邻居排序键 (file, line, callee)
    字典序取首个（确定性最短路径）。
  * 查询层输出契约 v2.1（C-P0-2/P1-1/P1-2/P1-6/P1-7，机检门先行批次）：① 表头数字 =
    最终保留条目数（callers/callees 新增 listed: 表头、impact 新增 radius: 表头）；
    --limit 截断时在触发列表旁就地写「已截断：显示 X / 共 Y（--limit 可放宽）」，
    同一条文本进 notes（截断/降级唯一结构化通道，自带下一步动作）；--format json 外壳
    加 truncated/total/limit 三字段（total=截断前真实总数）。② 「无结果不是错误」
    收敛在 classify_query_outcome 单点（md/json 两出口共调）。③ 列表全序单点
    _list_sort_key（语义主键→file→line→符号名字典序）、去重键单点 _call_site_key
    （tuple，禁字符串拼接键）。④ emit_human/emit_json 双通道：--format json 时
    stdout 只写一个 JSON 文档（json.loads 全量一次成功），人类文本（含 [FAIL]）走 stderr。

退出码：0 成功产出（可含 warning）/ 1 产出不完整或内部错误 / 2 用法错误或路径不可读。

重估触发线（留档，供后续修订判断）：自测断言 > 150 条，或需要跨文件共享 fixture 时，
拆分独立测试目录（DEV-01；已触发：自测区平移至 tests/test_analyze_structure.py，
此处 --selftest 为子进程转发入口）；facts JSON > 50MB，或进程内单次查询冷启动 > 3s，或跨文件
边数 > 10^6 时，重新评估索引形态（F11）。

Language token patterns adapted from Pygments 2.21.0 (BSD-2-Clause) lexers — https://pygments.org/docs/lexers/
"""
import ast
import builtins
import json
import os
import re
import subprocess
import sys
import tempfile

SCHEMA_VERSION = 3
TOOL_NAME = 'analyze_structure.py'
# A-P1-6（J3 裁决）：引擎内容版本，对齐 CodeGraph EXTRACTION_VERSION 的纪律——
# 与 SCHEMA_VERSION（facts 形状契约，迁移可补）相互独立：本值跟踪「提取产出的内容」，
# 只能重建底稿才能对齐的变化 bump。bump 规则：新增事实字段 / 新增语言或引擎分支 /
# 改变既有字段的语义或取值分布 → +1；纯 bugfix、CLI/UX 改动、仅形状的 schema 迁移
# → 不 bump（over-bumping 会让「建议重跑」提示变成噪声）。查询层不因本值不等而失败
# （向后兼容：旧 facts 缺该字段视为未知），只在 MD 头输出供人/下游判断底稿新鲜度。
# v2：banner 口径改双信号（弱信号须与自身指代同行共现 + 模式补中文），generated
# 标注的取值分布变化 → +1。
ENGINE_VERSION = 2
SIGNATURE_MAX = 200
PARSE_MAX_BYTES = 5 * 1024 * 1024        # 超过则不解析（记 too-large 告警）
READ_MAX_BYTES = 64 * 1024 * 1024        # 超过则不读入

# ---------------------------------------------------------------- 闭集契约（F10）
# 单一常量表：后续加语言/加类型只加数据、不改分支；取值只做追加，不重排、不改名。
CLOSED_SETS = {
    'symbols.kind': (
        'function', 'method', 'class', 'interface', 'struct', 'enum',
        'trait', 'type_alias', 'constant', 'variable', 'module'),
    'extractor': ('ast', 'brace', 'end'),
    'imports.kind': ('import', 'include', 'require', 'use', 'using'),
    'entry_points.kind': (
        'main-guard', 'main-function', 'console-script', 'manifest-main',
        'pkg-bin', 'pkg-script', 'filename-heuristic', 'listen-call'),
    'warnings.kind': (
        'parse-error', 'decode-error', 'too-large', 'read-error',
        'unbalanced-block', 'manifest-error', 'unsupported-language',
        'symlink-skipped', 'name-cap-exceeded'),
    'calls.resolution': ('unique', 'ambiguous', 'unresolved', 'self_ref'),
    'calls.unresolved_reason': ('external', 'not_extracted_here',
                                'builtin_filtered'),
    'calls.resolved_by': ('name', 'binding', 'qualified'),
    'language': (
        'python', 'javascript', 'typescript', 'java', 'c', 'cpp', 'csharp',
        'go', 'rust', 'php', 'ruby', 'kotlin', 'swift', 'scala', 'dart', 'lua'),
    'counts.keys': (
        'files', 'symbols', 'imports', 'calls', 'calls_verified',
        'calls_inferred', 'entry_points', 'parse_errors', 'filtered_calls',
        'languages', 'unsupported_files'),
}

# 闭集尺寸（表完备性自检用；改动闭集必须同步此表与 schema_version）
CLOSED_SIZES = {
    'symbols.kind': 11, 'extractor': 3, 'imports.kind': 5,
    'entry_points.kind': 8, 'warnings.kind': 9, 'language': 16,
    'counts.keys': 11, 'calls.resolution': 4,
    'calls.unresolved_reason': 3, 'calls.resolved_by': 3,
}

SYM_KINDS = CLOSED_SETS['symbols.kind']
K_FUNCTION, K_METHOD, K_CLASS, K_INTERFACE, K_STRUCT, K_ENUM, K_TRAIT, \
    K_TYPE_ALIAS, K_CONSTANT, K_VARIABLE, K_MODULE = SYM_KINDS

EXTRACTORS = CLOSED_SETS['extractor']
EXT_AST, EXT_BRACE, EXT_END = EXTRACTORS

IMPORT_KINDS = CLOSED_SETS['imports.kind']
IMP_IMPORT, IMP_INCLUDE, IMP_REQUIRE, IMP_USE, IMP_USING = IMPORT_KINDS

ENTRY_KINDS = CLOSED_SETS['entry_points.kind']
EP_MAIN_GUARD, EP_MAIN_FUNCTION, EP_CONSOLE_SCRIPT, EP_MANIFEST_MAIN, \
    EP_PKG_BIN, EP_PKG_SCRIPT, EP_FILENAME, EP_LISTEN = ENTRY_KINDS

WARNING_KINDS = CLOSED_SETS['warnings.kind']
W_PARSE, W_DECODE, W_TOO_LARGE, W_READ, W_UNBALANCED, W_MANIFEST, \
    W_UNSUPPORTED, W_SYMLINK, W_NAME_CAP = WARNING_KINDS

LANG_IDS = CLOSED_SETS['language']
COUNT_KEYS = CLOSED_SETS['counts.keys']

CONF_VERIFIED = 'verified'
CONF_INFERRED = 'inferred'
CONFIDENCES = (CONF_VERIFIED, CONF_INFERRED)      # J3：二值枚举

# A-P0-2：调用边消解状态四值闭集（resolution 字段）
RESOLUTIONS = CLOSED_SETS['calls.resolution']
R_UNIQUE, R_AMBIGUOUS, R_UNRESOLVED, R_SELF_REF = RESOLUTIONS
# to=null 时的未解析理由闭集（unresolved_reason 字段；builtin_filtered 当前引擎
# 不会落到边上——内建名在建边前已按 filtered_calls 计数，取值保留给 hand-built
# facts 与后续批次收口用）
UNRESOLVED_REASONS = CLOSED_SETS['calls.unresolved_reason']
U_EXTERNAL, U_NOT_EXTRACTED, U_BUILTIN = UNRESOLVED_REASONS
# B-P0-2：verified 边的证据来源正交标签（resolved_by 字段；闭集不扩，J5）
RESOLVED_BY = CLOSED_SETS['calls.resolved_by']
RB_NAME, RB_BINDING, RB_QUALIFIED = RESOLVED_BY

# B-P2-3：同名候选上限（CodeGraph CODEGRAPH_AMBIGUOUS_NAME_CEILING 同源纪律：
# 宁可放弃该边也不做 ref×cand 两两打分）。超过上限的尾名，其调用边整条放弃
# （计 filtered_calls 并按名告警一次 name-cap-exceeded）。
CANDIDATE_CAP = 500
# A-P0-2：多候选时边内保留的候选列表长度上限（全量以 candidates_total 表达）。
TO_CANDIDATE_LIMIT = 5

# ---------------------------------------------------------------- 语言矩阵（F5）
LANG_EXTS = {
    'python': ('.py',),
    'javascript': ('.js', '.jsx', '.mjs', '.cjs'),
    'typescript': ('.ts', '.tsx', '.mts', '.cts'),
    'java': ('.java',),
    'c': ('.c', '.h'),
    'cpp': ('.cpp', '.cc', '.cxx', '.hpp', '.hh', '.hxx'),
    'csharp': ('.cs',),
    'go': ('.go',),
    'rust': ('.rs',),
    'php': ('.php',),
    'ruby': ('.rb',),
    'kotlin': ('.kt', '.kts'),
    'swift': ('.swift',),
    'scala': ('.scala', '.sc'),
    'dart': ('.dart',),
    'lua': ('.lua',),
}

LANG_ALIASES = {
    'py': 'python', 'js': 'javascript', 'ts': 'typescript',
    'c++': 'cpp', 'c#': 'csharp', 'golang': 'go',
}

EXT_TO_LANG = {}
for _lang, _exts in LANG_EXTS.items():
    for _ext in _exts:
        EXT_TO_LANG[_ext] = _lang
del _lang, _exts, _ext


def lang_extractor(lang):
    """语言 → 引擎/extractor 取值（F5 三引擎；表驱动，无实现分支）。"""
    if lang == 'python':
        return EXT_AST
    if lang in ('ruby', 'lua'):
        return EXT_END
    return EXT_BRACE


# 命名启发式入口点规则（F6.6）：(basename, 要求的父目录名或 None)
# v1 口径：Python + JS 族；v2 新增：Go main.go / Rust src/main.rs / Java Main.java
FILENAME_ENTRY_RULES = (
    ('main.py', None), ('app.py', None), ('__main__.py', None),
    ('manage.py', None), ('cli.py', None),
    ('index.js', None), ('index.ts', None), ('app.js', None), ('app.ts', None),
    ('main.js', None), ('main.ts', None), ('server.js', None), ('server.ts', None),
    ('main.go', None), ('main.rs', 'src'), ('Main.java', None),
)

# ---------------------------------------------------------------- 语言模式表（F6.3）
# 表是数据，不是代码分支：加一门语言 = 加一张表 + 加断言。
# 字段契约：
#   line_comment   行注释前缀（剥后再匹配）
#   block_comment  块注释 (open, close) 对
#   strings        字符串 (open, close, flags) 对；flags 含 escape/multiline/dquote2；
#                  ('RE',) 表示 JS 族正则字面量启发式
#   open_kw / open_kw_line_start / close_kw   end 引擎的块关键字（brace 语言为空）
#   decl           (正则, kind, role) 列表；role ∈ type/impl/func/value/bodyless；
#                  正则具名组 (?P<n>...) = 名，(?P<recv>...) = 接收者/所属类型
#   imports        (正则, kind, resolver) 列表；捕获组 1 = 模块/路径说明符
#   decl_stops     声明名停用表（控制关键字，命中即弃）
#   member_sep     成员调用分隔符（默认 '.'；lua 为 '[.:]'）
#   call_stops     裸调用名停用表
#   global_stops   全局名停用表（被滤条目只计 filtered_calls，F6.5）
#   new_call       是否把 new Foo( 记为调用边（F6.5：JS 族）
#   listen         是否探测 .listen( 入口点（F6.6：JS 族）
#   main_re        main 函数声明形态（F6.6 main-function；None=无）
#   qualname_rule  限定名构造规则说明（F6.3 表字段）
LANG_TABLES = {
    'javascript': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'strings': (('"', '"', 'escape'), ("'", "'", ''), ('`', '`', 'multiline'),
                    ('RE',)),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bfunction\s*\*?\s*(?P<n>[\w$]+)\s*\(', K_FUNCTION, 'func'),
            (r'\bclass\s+(?P<n>[\w$]+)', K_CLASS, 'type'),
            (r'\bconst\s+(?P<n>[\w$]+)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)[^=;{}]*?=>|[\w$]+\s*=>)', K_FUNCTION, 'func'),
            (r'\blet\s+(?P<n>[\w$]+)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)[^=;{}]*?=>)', K_FUNCTION, 'func'),
            (r'\b(?:async\s+)?(?P<n>[\w$]+)\s*\([^;{}]*\)\s*\{', K_METHOD, 'func'),
        ),
        'imports': (
            (r'^[ \t]*import\s+(?:[\w{},\s\*$]+\s+from\s+)?[\'"]([^\'"]+)[\'"]', IMP_IMPORT, 'js'),
            (r'^[ \t]*export\s+[^\'"\n]*?\bfrom\s+[\'"]([^\'"]+)[\'"]', IMP_IMPORT, 'js'),
            (r'\brequire\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', IMP_REQUIRE, 'js'),
            (r'\bimport\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', IMP_IMPORT, 'js_dynamic'),
        ),
        'decl_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'typeof',
                       'function', 'new', 'await', 'do', 'else', 'try', 'finally',
                       'class', 'extends', 'import', 'export', 'delete', 'void',
                       'in', 'of', 'instanceof', 'super', 'this', 'case', 'default',
                       'throw', 'yield', 'listen', 'require'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'typeof',
                       'function', 'new', 'await', 'do', 'else', 'try', 'finally',
                       'class', 'extends', 'import', 'export', 'delete', 'void',
                       'in', 'of', 'instanceof', 'super', 'this', 'case', 'default',
                       'throw', 'yield', 'listen', 'require'),
        'global_stops': ('log', 'parseInt'),
        'new_call': True,
        'listen': True,
        'main_re': None,
        'qualname_rule': 'Type.method（作用域栈点号连接；顶层 const/let 箭头与函数表达式 → function）',
    },

    'typescript': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'strings': (('"', '"', 'escape'), ("'", "'", ''), ('`', '`', 'multiline'),
                    ('RE',)),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\binterface\s+(?P<n>[\w$]+)', K_INTERFACE, 'type'),
            (r'\btype\s+(?P<n>[\w$]+)\s*=', K_TYPE_ALIAS, 'bodyless'),
            (r'\benum\s+(?P<n>[\w$]+)', K_ENUM, 'type'),
            (r'\bfunction\s*\*?\s*(?P<n>[\w$]+)\s*\(', K_FUNCTION, 'func'),
            (r'\bclass\s+(?P<n>[\w$]+)', K_CLASS, 'type'),
            (r'\bconst\s+(?P<n>[\w$]+)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)[^=;{}]*?=>|[\w$]+\s*=>)', K_FUNCTION, 'func'),
            (r'\b(?:async\s+)?(?P<n>[\w$]+)\s*\([^;{}]*\)\s*\{', K_METHOD, 'func'),
        ),
        'imports': (
            (r'^[ \t]*import\s+(?:[\w{},\s\*$]+\s+from\s+)?[\'"]([^\'"]+)[\'"]', IMP_IMPORT, 'js'),
            (r'^[ \t]*export\s+[^\'"\n]*?\bfrom\s+[\'"]([^\'"]+)[\'"]', IMP_IMPORT, 'js'),
            (r'\brequire\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', IMP_REQUIRE, 'js'),
            (r'\bimport\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', IMP_IMPORT, 'js_dynamic'),
        ),
        'decl_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'typeof',
                       'function', 'new', 'await', 'do', 'else', 'try', 'finally',
                       'class', 'extends', 'import', 'export', 'delete', 'void',
                       'in', 'of', 'instanceof', 'super', 'this', 'case', 'default',
                       'throw', 'yield', 'interface', 'type', 'enum', 'declare',
                       'namespace', 'abstract', 'readonly', 'implements', 'public',
                       'private', 'protected', 'listen'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'typeof',
                       'function', 'new', 'await', 'do', 'else', 'try', 'finally',
                       'class', 'extends', 'import', 'export', 'delete', 'void',
                       'in', 'of', 'instanceof', 'super', 'this', 'case', 'default',
                       'throw', 'yield', 'keyof', 'readonly', 'listen',
                       'require'),
        'global_stops': ('log', 'parseInt'),
        'new_call': True,
        'listen': True,
        'main_re': None,
        'qualname_rule': '同 javascript，另加 interface/type_alias/enum 声明形态',
    },

    'java': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'strings': (('"', '"', 'escape'), ("'", "'", '')),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bclass\s+(?P<n>\w+)', K_CLASS, 'type'),
            (r'\binterface\s+(?P<n>\w+)', K_INTERFACE, 'type'),
            (r'\benum\s+(?P<n>\w+)', K_ENUM, 'type'),
            (r'\brecord\s+(?P<n>\w+)', K_CLASS, 'type'),
            (r'\bstatic\s+final\b[^=;{}]*?\b(?P<n>[A-Za-z_]\w*)\s*=[^=]', K_CONSTANT, 'value'),
            (r'\bfinal\s+static\b[^=;{}]*?\b(?P<n>[A-Za-z_]\w*)\s*=[^=]', K_CONSTANT, 'value'),
            (r'(?<!new\s)\b(?P<n>\w+)\s*\([^;{}]*\)\s*\{', K_METHOD, 'func'),
        ),
        'imports': (
            (r'^[ \t]*import\s+(?:static\s+)?([\w\.]+)\s*;', IMP_IMPORT, 'dotfile'),
        ),
        'decl_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'new',
                       'do', 'else', 'try', 'finally', 'synchronized', 'throw',
                       'case', 'super', 'this', 'assert', 'class', 'interface',
                       'enum', 'record'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'new',
                       'do', 'else', 'try', 'finally', 'synchronized', 'throw',
                       'case', 'super', 'this', 'assert'),
        'global_stops': ('println', 'printf', 'print'),
        'new_call': False,
        'listen': False,
        'main_re': r'\bpublic\s+static\s+void\s+main\s*\(',
        'qualname_rule': 'Outer.Inner.method（作用域栈点号连接；static final 常量带所属类前缀）',
    },

    'c': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'strings': (('"', '"', 'escape'), ("'", "'", '')),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bstruct\s+(?P<n>\w+)\s*\{', K_STRUCT, 'type'),
            (r'\benum\s+(?P<n>\w+)\s*\{', K_ENUM, 'type'),
            (r'\btypedef\b[^;]*?\b(?P<n>\w+)\s*;', K_TYPE_ALIAS, 'bodyless'),
            (r'^[ \t]*#\s*define\s+(?P<n>\w+)(?!\s*\()', K_CONSTANT, 'value'),
            (r'\b(?:[\w\*]+\s+)+\**(?P<n>\w+)\s*\([^;{}]*\)\s*\{', K_FUNCTION, 'func'),
        ),
        'imports': (
            (r'^[ \t]*#\s*include\s*"([^"]+)"', IMP_INCLUDE, 'c_quote'),
            (r'^[ \t]*#\s*include\s*<([^>]+)>', IMP_INCLUDE, 'c_angle'),
        ),
        'decl_stops': ('if', 'for', 'while', 'switch', 'return', 'sizeof', 'do',
                       'else', 'case', 'goto', 'struct', 'enum', 'union'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'switch', 'return', 'sizeof', 'do',
                       'else', 'case', 'goto'),
        'global_stops': ('printf', 'scanf', 'malloc', 'free', 'memcpy', 'strlen'),
        'new_call': False,
        'listen': False,
        'main_re': r'\b(?:int|void)\s+main\s*\(',
        'qualname_rule': '函数名（C 无类作用域；struct/enum/typedef/#define 按形态）',
    },

    'cpp': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'strings': (('"', '"', 'escape'), ("'", "'", '')),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bclass\s+(?P<n>\w+)', K_CLASS, 'type'),
            (r'\bnamespace\s+(?P<n>\w+)', K_MODULE, 'type'),
            (r'\bstruct\s+(?P<n>\w+)\s*\{', K_STRUCT, 'type'),
            (r'\benum(?:\s+class)?\s+(?P<n>\w+)\s*\{', K_ENUM, 'type'),
            (r'\btypedef\b[^;]*?\b(?P<n>\w+)\s*;', K_TYPE_ALIAS, 'bodyless'),
            (r'^[ \t]*#\s*define\s+(?P<n>\w+)(?!\s*\()', K_CONSTANT, 'value'),
            # P1-b：模块唯一出口（pybind11 / Boost.Python 的宏式模块初始化函数）
            (r'^[ \t]*(?P<n>PYBIND11_MODULE|PYBIND11_PLUGIN|BOOST_PYTHON_MODULE)\s*\(',
             K_FUNCTION, 'func'),
            (r'\b(?P<recv>\w+)::(?P<n>\w+)\s*\([^;{}]*\)\s*\{', K_METHOD, 'func'),
            # P1-b：`const` / `noexcept` / `override` 限定的成员函数
            # （`bool check_leaf(const std::vector<Coord>& cslist) const {`）。
            # 类型词里的冒号必须成对（`::`），否则 `public:` / `private:` 标号会被
            # 当成类型吃掉（实测伪符号 MD5.MD5 / MD5.rol）
            (r'\b(?:[\w\*&]+(?:::+[\w\*&]+)*(?:<[^;{}()]*>)?[\s\*&]+)+\**(?P<n>\w+)'
             r'\s*\([^;{}]*\)\s*(?:const|noexcept|override|final)\b[^;{}]*\{',
             K_FUNCTION, 'func'),
            # P1-b：带限定名/模板参数的返回类型（`std::vector<Coord> f(...) {`）
            (r'\b(?:[\w\*&]+(?:::+[\w\*&]+)*(?:<[^;{}()]*>)?[\s\*&]+)+\**(?P<n>\w+)'
             r'\s*\([^;{}]*\)\s*\{', K_FUNCTION, 'func'),
        ),
        'imports': (
            (r'^[ \t]*#\s*include\s*"([^"]+)"', IMP_INCLUDE, 'c_quote'),
            (r'^[ \t]*#\s*include\s*<([^>]+)>', IMP_INCLUDE, 'c_angle'),
        ),
        'decl_stops': ('if', 'for', 'while', 'switch', 'return', 'sizeof', 'do',
                       'else', 'case', 'goto', 'new', 'delete', 'throw', 'catch',
                       'struct', 'enum', 'union', 'template', 'using', 'namespace',
                       'operator', 'class'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'switch', 'return', 'sizeof', 'do',
                       'else', 'case', 'goto', 'new', 'delete', 'throw', 'catch'),
        'global_stops': ('printf', 'scanf', 'malloc', 'free', 'memcpy', 'strlen'),
        'new_call': False,
        'listen': False,
        'main_re': r'\b(?:int|void)\s+main\s*\(',
        'qualname_rule': 'Namespace.Class.method（作用域栈点号连接；Class::method 域外定义 → method）',
    },

    'csharp': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'strings': (('"', '"', 'escape'), ('@"', '"', 'multiline dquote2'),
                    ("'", "'", '')),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bclass\s+(?P<n>\w+)', K_CLASS, 'type'),
            (r'\binterface\s+(?P<n>\w+)', K_INTERFACE, 'type'),
            (r'\bstruct\s+(?P<n>\w+)', K_STRUCT, 'type'),
            (r'\benum\s+(?P<n>\w+)', K_ENUM, 'type'),
            (r'\bnamespace\s+(?P<n>\w+)', K_MODULE, 'type'),
            (r'\b(?:const|static\s+readonly)\s+[\w<>\[\],\s\?]{0,120}?\b(?P<n>\w+)\s*=[^=]', K_CONSTANT, 'value'),
            (r'(?<!new\s)(?<!new\()\b(?P<n>\w+)\s*\([^;{}]*\)\s*\{', K_METHOD, 'func'),
        ),
        'imports': (
            (r'^[ \t]*using\s+([\w\.]+)\s*;', IMP_USING, 'dotfile_cs'),
        ),
        'decl_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'new',
                       'do', 'else', 'try', 'finally', 'lock', 'case', 'foreach',
                       'base', 'this', 'throw', 'switch', 'sizeof', 'class',
                       'interface', 'struct', 'enum', 'namespace'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'new',
                       'do', 'else', 'try', 'finally', 'lock', 'case', 'foreach',
                       'base', 'this', 'throw', 'sizeof'),
        'global_stops': ('WriteLine', 'Write', 'ReadLine', 'ReadKey'),
        'new_call': False,
        'listen': False,
        'main_re': r'\bstatic\s+(?:void|int)\s+Main\s*\(',
        'qualname_rule': 'Namespace.Class.method（作用域栈点号连接；const/static readonly 带所属类前缀）',
    },

    'go': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'strings': (('"', '"', 'escape'), ('`', '`', 'multiline'), ("'", "'", '')),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\btype\s+(?P<n>\w+)\s+struct\b', K_STRUCT, 'type'),
            (r'\btype\s+(?P<n>\w+)\s+interface\b', K_INTERFACE, 'type'),
            (r'\btype\s+(?P<n>\w+)\s*=', K_TYPE_ALIAS, 'bodyless'),
            (r'\bfunc\s*(?:\(\s*\w+\s+\*?(?P<recv>\w+)\s*\)\s*)?(?P<n>\w+)\s*\(', K_FUNCTION, 'func'),
            (r'\bconst\s+(?P<n>\w+)\s*=[^=]', K_CONSTANT, 'value'),
            (r'\bvar\s+(?P<n>\w+)\s*(?:[\w\*\.\[\]]+\s*)?=[^=]', K_VARIABLE, 'value'),
        ),
        'imports': (
            (r'^[ \t]*import\s+"([^"]+)"', IMP_IMPORT, 'go'),
            (r'^[ \t]*import\s*\($', IMP_IMPORT, 'go_block'),
        ),
        'decl_stops': ('if', 'for', 'switch', 'return', 'func', 'go', 'defer',
                       'range', 'case', 'select', 'break', 'continue', 'goto',
                       'var', 'const', 'type', 'map', 'chan', 'struct',
                       'interface'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'switch', 'return', 'func', 'go', 'defer',
                       'range', 'case', 'select', 'break', 'continue', 'goto',
                       'var', 'const', 'type'),
        'global_stops': ('make', 'len', 'cap', 'append', 'panic', 'recover',
                         'print', 'println', 'Println', 'Printf'),
        'new_call': False,
        'listen': False,
        'main_re': r'\bfunc\s+main\s*\(\s*\)',
        'qualname_rule': 'Type.Method（func (r T) Name → T.Name；包级 func Name → function）',
    },

    'rust': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'nested_block': True,
        # char 字面量按 Pygments rust.py:115 形态预剥离（与生命周期 'a 区分）
        'pre_strip': (r"'(\\u\{[0-9a-fA-F]{1,6}\}|\\x[0-9a-fA-F]{2}|\\0|\\['\"\\nrt]|[^\\'\n])'",),
        # raw 串 b?r(#*)"..."\1（rust.py:138）；单引号对不剥（生命周期，同 Pygments）
        'strings': (('"', '"', 'escape'), ('r##"', '##"', 'multiline'),
                    ('br#"', '"#', 'multiline'), ('r#"', '"#', 'multiline'),
                    ('br"', '"', 'multiline'), ('r"', '"', 'multiline'),
                    ('b"', '"', 'escape')),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bfn\s+(?P<n>\w+)', K_FUNCTION, 'func'),
            (r'\bstruct\s+(?P<n>\w+)', K_STRUCT, 'type'),
            (r'\benum\s+(?P<n>\w+)', K_ENUM, 'type'),
            (r'\btrait\s+(?P<n>\w+)', K_TRAIT, 'type'),
            (r'\btype\s+(?P<n>\w+)\s*=', K_TYPE_ALIAS, 'bodyless'),
            (r'\bmod\s+(?P<n>\w+)\s*;', K_MODULE, 'bodyless'),
            (r'\bmod\s+(?P<n>\w+)', K_MODULE, 'type'),
            (r'\bimpl\s*(?:<[^>]*>\s*)?(?:[\w:]+\s+for\s+)?(?P<n>\w+)', None, 'impl'),
            (r'\bconst\s+(?P<n>\w+)', K_CONSTANT, 'value'),
            (r'\bstatic\s+(?P<n>\w+)', K_CONSTANT, 'value'),
        ),
        'imports': (
            (r'^[ \t]*use\s+([\w:]+)', IMP_USE, 'rust'),
        ),
        'decl_stops': ('if', 'for', 'while', 'loop', 'match', 'return', 'let',
                       'else', 'in', 'as', 'dyn', 'move', 'ref', 'where'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'loop', 'match', 'return', 'let',
                       'else', 'in', 'as', 'dyn', 'move', 'ref', 'where', 'fn',
                       'impl', 'mod', 'use', 'crate', 'self', 'super'),
        'macro_stops': ('println', 'format', 'vec', 'panic', 'assert'),
        'global_stops': (),
        'new_call': False,
        'listen': False,
        'main_re': r'\bfn\s+main\s*\(\s*\)',
        'qualname_rule': 'impl Type 内 fn → Type.method；trait 内 fn 签名（; 结尾）不产出',
    },

    'php': {
        'line_comment': ('//', '#'),
        'block_comment': (('/*', '*/'),),
        'strings': (('"', '"', 'escape'), ("'", "'", '')),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bfunction\s+(?P<n>\w+)\s*\(', K_FUNCTION, 'func'),
            (r'\bclass\s+(?P<n>\w+)', K_CLASS, 'type'),
            (r'\binterface\s+(?P<n>\w+)', K_INTERFACE, 'type'),
            (r'\btrait\s+(?P<n>\w+)', K_TRAIT, 'type'),
            (r'\bconst\s+(?P<n>\w+)\s*=[^=]', K_CONSTANT, 'value'),
            (r'\bdefine\s*\(\s*[\'"](?P<n>\w+)[\'"]', K_CONSTANT, 'value'),
        ),
        'imports': (
            (r'^[ \t]*use\s+([\w\\]+)\s*;', IMP_USE, 'php_use'),
            (r'^[ \t]*(?:require|include)(?:_once)?\s*\(?\s*[\'"]([^\'"]+)[\'"]', IMP_REQUIRE, 'path'),
        ),
        'decl_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'new',
                       'do', 'else', 'try', 'foreach', 'function', 'elseif',
                       'print', 'echo', 'case'),
        'member_sep': '->',
        'call_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'new',
                       'do', 'else', 'try', 'foreach', 'function', 'elseif',
                       'print', 'echo', 'case'),
        'global_stops': ('strlen', 'strtoupper', 'strtolower', 'substr',
                         'implode', 'explode', 'var_dump', 'count', 'define'),
        'new_call': False,
        'listen': False,
        'main_re': None,
        'heredoc': True,
        'decl_on_comments': True,      # define('NAME', ...) 的名字在串里：声明扫描用仅剥注释文本
        'qualname_rule': 'Class.method（作用域栈点号连接；顶层 function → function）',
    },

    'ruby': {
        'line_comment': ('#',),
        'block_comment': (('=begin', '=end'),),
        'strings': (('"', '"', 'escape'), ("'", "'", '')),
        'open_kw': ('def', 'class', 'module', 'begin', 'do', 'case'),
        'open_kw_line_start': ('if', 'unless', 'while', 'until', 'for', 'case'),
        'close_kw': ('end',),
        'decl': (
            (r'\bdef\s+(?:self\.)?(?P<n>\w+)', K_FUNCTION, 'func'),
            (r'\bclass\s+(?P<n>[A-Z]\w*)', K_CLASS, 'type'),
            (r'\bmodule\s+(?P<n>[A-Z]\w*)', K_MODULE, 'type'),
            (r'\b(?P<n>[A-Z][A-Z0-9_]{2,})\s*=[^=]', K_CONSTANT, 'value'),
        ),
        'imports': (
            (r'^[ \t]*require_relative\s*[\'"]([^\'"]+)[\'"]', IMP_REQUIRE, 'ruby_rel'),
            (r'^[ \t]*require\s*[\'"]([^\'"]+)[\'"]', IMP_REQUIRE, 'ruby'),
        ),
        'decl_stops': ('if', 'unless', 'while', 'until', 'def', 'class', 'module',
                       'begin', 'case', 'return', 'yield', 'then', 'elsif', 'raise',
                       'end', 'do'),
        'member_sep': '.',
        'call_stops': ('if', 'unless', 'while', 'until', 'def', 'class', 'module',
                       'begin', 'case', 'return', 'yield', 'then', 'elsif', 'raise',
                       'end', 'do', 'and', 'or', 'not'),
        'global_stops': ('puts', 'print', 'p', 'raise'),
        'new_call': False,
        'listen': False,
        'main_re': None,
        'qualname_rule': 'Module.Class.method（作用域栈点号连接；CONST 全大写 → constant）',
    },

    'kotlin': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'nested_block': True,                  # Pygments jvm.py KotlinLexer comment #push/#pop
        'strings': (('"', '"', 'escape'), ('"""', '"""', 'multiline'),
                    ("'", "'", '')),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bclass\s+(?P<n>\w+)', K_CLASS, 'type'),
            (r'\binterface\s+(?P<n>\w+)', K_INTERFACE, 'type'),
            (r'\bobject\s+(?P<n>\w+)', K_CLASS, 'type'),
            (r'\bfun\s+(?:<[^>]*>\s+)?(?:[\w<>\[\]\.]+\s+)?(?P<n>\w+)\s*\(', K_FUNCTION, 'func'),
            (r'\bval\s+(?P<n>\w+)\s*[:=<][^=]', K_CONSTANT, 'value'),
            (r'\bvar\s+(?P<n>\w+)\s*[:=][^=]', K_VARIABLE, 'value'),
        ),
        'imports': (
            (r'^[ \t]*import\s+([\w\.]+)', IMP_IMPORT, 'dotfile_kt'),
        ),
        'decl_stops': ('if', 'for', 'while', 'when', 'return', 'do', 'else', 'try',
                       'catch', 'is', 'in', 'as', 'throw', 'this', 'super', 'new',
                       'object', 'class', 'interface', 'fun', 'val', 'var'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'when', 'return', 'do', 'else', 'try',
                       'catch', 'is', 'in', 'as', 'throw', 'this', 'super', 'new'),
        'global_stops': ('println', 'print'),
        'new_call': False,
        'listen': False,
        'main_re': r'\bfun\s+main\s*\(',
        'qualname_rule': 'Class.method（作用域栈点号连接；val → constant / var → variable）',
    },

    'swift': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'nested_block': True,                  # Pygments objective.py comment-multi #push/#pop
        'strings': (('"', '"', 'escape'),),    # 尾逗号：单元素元组
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bfunc\s+(?P<n>\w+)\s*[(<]', K_FUNCTION, 'func'),
            (r'\bclass\s+(?P<n>\w+)', K_CLASS, 'type'),
            (r'\bstruct\s+(?P<n>\w+)', K_STRUCT, 'type'),
            (r'\benum\s+(?P<n>\w+)\s*[:\{]', K_ENUM, 'type'),
            (r'\bprotocol\s+(?P<n>\w+)', K_INTERFACE, 'type'),
            (r'\blet\s+(?P<n>\w+)\s*[:=][^=]', K_CONSTANT, 'value'),
            (r'\bvar\s+(?P<n>\w+)\s*[:=][^=]', K_VARIABLE, 'value'),
        ),
        'imports': (
            (r'^[ \t]*import\s+([\w\.]+)', IMP_IMPORT, 'dotfile_swift'),
        ),
        'decl_stops': ('if', 'for', 'while', 'switch', 'guard', 'return', 'do',
                       'else', 'try', 'catch', 'in', 'as', 'is', 'throw', 'defer'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'switch', 'guard', 'return', 'do',
                       'else', 'try', 'catch', 'in', 'as', 'is', 'throw', 'defer'),
        'global_stops': ('print',),
        'new_call': False,
        'listen': False,
        'main_re': r'\bfunc\s+main\s*\(',
        'qualname_rule': 'Type.method（作用域栈点号连接；let → constant / var → variable）',
    },

    'scala': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'nested_block': True,                  # Pygments jvm.py ScalaLexer comment #push/#pop
        'strings': (('"', '"', 'escape'), ('"""', '"""', 'multiline'),
                    ("'", "'", '')),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bclass\s+(?P<n>\w+)', K_CLASS, 'type'),
            (r'\bobject\s+(?P<n>\w+)', K_MODULE, 'type'),
            (r'\btrait\s+(?P<n>\w+)', K_TRAIT, 'type'),
            (r'\bdef\s+(?P<n>\w+)\s*[\(<]', K_FUNCTION, 'func'),
            (r'\bval\s+(?P<n>\w+)\s*[:=][^=]', K_CONSTANT, 'value'),
            (r'\bvar\s+(?P<n>\w+)\s*[:=][^=]', K_VARIABLE, 'value'),
        ),
        'imports': (
            (r'^[ \t]*import\s+([\w\.]+)', IMP_IMPORT, 'dotfile_scala'),
        ),
        'decl_stops': ('if', 'for', 'while', 'return', 'case', 'new', 'do', 'else',
                       'try', 'match', 'yield', 'object', 'class', 'trait'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'return', 'case', 'new', 'do', 'else',
                       'try', 'match', 'yield'),
        'global_stops': ('println', 'print'),
        'new_call': False,
        'listen': False,
        'main_re': r'\bdef\s+main\s*\(',
        'qualname_rule': 'Object.Class.method（object → module；val → constant / var → variable）',
    },

    'dart': {
        'line_comment': ('//',),
        'block_comment': (('/*', '*/'),),
        'strings': (('"', '"', 'escape'), ("'", "'", ''),
                    ('r"""', '"""', 'multiline'), ("r'''", "'''", 'multiline'),
                    ('r"', '"', ''), ("r'", "'", ''),
                    ("'''", "'''", 'multiline'), ('"""', '"""', 'multiline')),
        'open_kw': (), 'open_kw_line_start': (), 'close_kw': (),
        'decl': (
            (r'\bclass\s+(?P<n>\w+)', K_CLASS, 'type'),
            (r'\benum\s+(?P<n>\w+)\s*\{', K_ENUM, 'type'),
            (r'\b(?:final|const)\s+[\w<>\[\],\s\?]{0,120}?\b(?P<n>\w+)\s*=[^=]', K_CONSTANT, 'value'),
            (r'\bvar\s+(?P<n>\w+)\s*=[^=]', K_VARIABLE, 'value'),
            (r'[\w<>\[\],\?]+[ \t]+\b(?P<n>\w+)\s*\([^;{}]*\)\s*\{', K_FUNCTION, 'func'),
        ),
        'imports': (
            (r'^[ \t]*import\s+[\'"]([^\'"]+)[\'"]', IMP_IMPORT, 'path'),
            (r'^[ \t]*(?:export|part)\s+[\'"]([^\'"]+)[\'"]', IMP_IMPORT, 'path'),
        ),
        'decl_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'new',
                       'do', 'else', 'try', 'finally', 'case', 'in', 'as', 'is',
                       'rethrow', 'assert', 'class', 'enum', 'extends', 'final',
                       'const', 'var'),
        'member_sep': '.',
        'call_stops': ('if', 'for', 'while', 'switch', 'catch', 'return', 'new',
                       'do', 'else', 'try', 'finally', 'case', 'in', 'as', 'is',
                       'rethrow', 'assert'),
        'global_stops': ('print',),
        'new_call': False,
        'listen': False,
        'main_re': r'\b(?:void\s+)?main\s*\(\s*\)',
        'qualname_rule': 'Class.method（作用域栈点号连接；顶层 final/const → constant）',
    },

    'lua': {
        'line_comment': ('--',),
        'block_comment': (('--[[', ']]'),),
        'strings': (('"', '"', 'escape'), ("'", "'", ''), ('[[', ']]', 'multiline')),
        # P1-7：for/while 语法必需的 `do` 恰好开一个块（同线/换行/standalone do
        # 三形态都正确）；for/while 自身不再计入开块，否则 do 双重计数 → 含循环
        # 函数系统性 end_line=null。
        'open_kw': ('function', 'if', 'do', 'repeat'),
        'open_kw_line_start': (),
        'close_kw': ('end', 'until'),
        'decl': (
            (r'\bfunction\s+(?P<n>[\w\.:]+)\s*\(', K_FUNCTION, 'func'),
            (r'\blocal\s+function\s+(?P<n>\w+)\s*\(', K_FUNCTION, 'func'),
            (r'\blocal\s+(?P<n>\w+)\s*=[^=]', K_VARIABLE, 'value'),
        ),
        'imports': (
            (r'^[ \t]*require\s*\(?\s*[\'"]([^\'"]+)[\'"]', IMP_REQUIRE, 'lua'),
        ),
        'decl_stops': ('if', 'for', 'while', 'do', 'then', 'end', 'function',
                       'local', 'return', 'repeat', 'until', 'elseif', 'else',
                       'break', 'goto'),
        'member_sep': '[.:]',
        'call_stops': ('if', 'for', 'while', 'do', 'then', 'end', 'function',
                       'local', 'return', 'repeat', 'until', 'elseif', 'else',
                       'break', 'goto', 'and', 'or', 'not'),
        'global_stops': ('print', 'pairs', 'ipairs', 'tostring', 'tonumber',
                         'type', 'error', 'pcall'),
        'new_call': False,
        'listen': False,
        'main_re': None,
        'qualname_rule': 'function t.f / t:f → method（qualname 取点号形态）；local function → function',
    },
}

# 模式表完备性自检用的字段清单（缺字段=机检红，不是引擎分支漏写——R3 关键缓解）
TABLE_REQUIRED_KEYS = ('line_comment', 'block_comment', 'strings', 'open_kw',
                       'open_kw_line_start', 'close_kw', 'decl', 'imports',
                       'decl_stops', 'member_sep', 'call_stops', 'global_stops',
                       'new_call', 'listen', 'main_re', 'qualname_rule')

# ---------------------------------------------------------------- 排除清单（F4）
DEFAULT_EXCLUDES = frozenset((
    '.git', '.hg', '.svn', '.idea', '.vscode', '.cache',
    'node_modules', '__pycache__', '.venv', 'venv', 'env', '.tox',
    '.mypy_cache', '.pytest_cache', '.ruff_cache',
    'dist', 'build', '.next', '.nuxt', 'coverage', 'htmlcov',
    'vendor', 'target', '.gradle', '.terraform',
))

# 元数据文件：不作为源文件登记（v1 F5 元数据行），仅供入口点/依赖解析读取
# P2-6：集合全小写——入口一律 base.lower() 比较（Windows 文件系统不敏感，且与
# 目录排除口径一致），manifest_entries 内部的分派字面量同用小写。
METADATA_BASENAMES = frozenset((
    'package.json', 'pyproject.toml', 'setup.py', 'setup.cfg',
    'cargo.toml', 'pom.xml', 'composer.json', 'go.mod',
))

# 命名启发式入口点（v1 口径：Python + JS 族；Go/Rust/Java 由 1b 扩列）
# 1b 起：规则表 FILENAME_ENTRY_RULES（见 LANG_TABLES 之前的定义）为准，此处旧字面量已删除。

PYPROJECT_SCRIPT_SECTIONS = (
    'project.scripts', 'tool.poetry.scripts',
    'project.entry-points.console_scripts',
)

BUILTIN_NAMES = frozenset(dir(builtins))

PROBE_DIR_NAMES = (
    'node_modules', 'dist', 'build', '__pycache__', '.venv', 'vendor', 'target',
)

# ---------------------------------------------------------------- 生成文件检测（A-P0-1）
# 双信号（路径约定 + 文件头 banner），信号只做**标注**（files[].generated），
# 绝不自动排除（J4 裁决：收益是解释噪声来源，不是删数据）。
# 机制与纪律借鉴 CodeGraph src/extraction/generated-detection.ts（MIT）：
# 排序提示非硬过滤、precision-first（假阳会静默把手写源码打上「疑生成」）、
# banner 必须落注释行（排除字符串字面量与标识符撞词）。
# 路径约定表：(basename 小写正则, 出处注记)。
GENERATED_PATH_PATTERNS = (
    (re.compile(r'\.pb\.go$'), 'protobuf Go'),
    (re.compile(r'_grpc\.pb\.go$'), 'gRPC Go'),
    (re.compile(r'\.pb\.(cc|hh?|hpp)$'), 'protobuf C++'),
    (re.compile(r'_pb2\.py$'), 'protobuf Python'),
    (re.compile(r'\.pb\.dart$'), 'protobuf Dart'),
    (re.compile(r'\.g\.dart$'), 'build_runner Dart'),
    (re.compile(r'\.freezed\.dart$'), 'freezed Dart'),
    (re.compile(r'\.generated\.(ts|js|rs)$'), '通用 .generated 后缀'),
    (re.compile(r'\.min\.m?js$'), '压缩产物 JS'),
    (re.compile(r'^mock_[\w.]+\.go$'), 'gomock mock_<src>.go 命名'),
    (re.compile(r'[\w.]+_mock\.go$'), 'gomock <src>_mock.go 命名'),
    (re.compile(r'\.g\.cs$'), 'C# 生成源'),
    (re.compile(r'^outerclass\.java$'), 'protoc java 内嵌类文件'),
)
# banner 形状表（precision-first：每条都要求「手写文本罕见」的组合；v2 双信号口径——
# 强信号单凭自身即可判定，弱信号必须同行另有本文件指代词才判定（见 GENERATED_SELF_REF），
# 防手写头注释引用他人生成物（do not edit those files directly 一类）被误标；
# 中文模式补齐：真生成物的中文 banner（本文件由 X 自动生成，请勿手动修改）此前零命中）
GENERATED_STRONG_PATTERNS = (
    # @generated 需词边界守卫：foo@generated 这类标识符文本不算
    re.compile(r'(?:^|[^\w@])@generated\b', re.IGNORECASE),
)
GENERATED_WEAK_PATTERNS = (
    # 裸「自动生成」散文太常见，要求 by 指名生成者（弱信号：还须同行指代本文件）
    re.compile(r'\bgenerated\s+by\s+\S', re.IGNORECASE),
    re.compile(r'\bauto-?generated\b', re.IGNORECASE),
    re.compile(r'\bdo\s+not\s+edit\b', re.IGNORECASE),
    re.compile(r'\bdo\s+not\s+modify\b', re.IGNORECASE),
    re.compile(r'自动生成'),
    re.compile(r'请勿手动修改'),
    re.compile(r'请勿编辑'),
    re.compile(r'请勿修改'),
)
# 「本文件指代」词表（v2，中英双语）：与弱信号同行共现才判 generated
GENERATED_SELF_REF = re.compile(
    r'\bthis\s+(?:file|code|module)\b|本文件|此文件|该文件', re.IGNORECASE)
GENERATED_STEM = re.compile(r'generat|自动生成|请勿',
                            re.IGNORECASE)   # 快速拒绝（须放行中文 banner，否则下表全白搭）
GENERATED_HEADER_CHARS = 8192   # 头部窗口：够放 license 前言 + build tag，
GENERATED_HEADER_LINES = 60     # 又紧到「生成器自己的源码里的字符串」冒充不了 banner
_GENERATED_COMMENT_LEADERS = (
    '//', '/*', '*', '#', '--', '%', ';', "'", '!', '(*', '{-', '<#',
    '=begin', '@rem', 'rem',
)
_GENERATED_BLOCK_PAIRS = (
    ('/*', '*/'), ('(*', '*)'), ('{-', '-}'), ('"""', '"""'),
    ("'''", "'''"), ('=begin', '=end'), ('<#', '#>'),
)


def has_generated_header(text):
    """文件头 banner 检测（A-P0-1，v2 双信号）：先快速拒绝，再逐行只测注释行/块内行。

    判定口径：@generated 词首标记为强信号，单凭自身即可判 True；其余生成/勿改词
    为弱信号，须同一行另有本文件指代词（GENERATED_SELF_REF）共现才判 True——
    手写头注释引用他人生成物（第三人称 generated by / 无指代的 do not edit）不满足
    共现，不再误标。块注释状态推进刻意朴素（naive，同行闭合即出块）；代价上限只是
    「疑生成」标注（非硬过滤），不产生错误答案。
    """
    if not text:
        return False
    head = text[:GENERATED_HEADER_CHARS]
    if not GENERATED_STEM.search(head):
        # 快速拒绝：绝大多数手写源码在此即返回（不切行、零逐行开销）
        return False
    in_block = None
    for line in head.splitlines()[:GENERATED_HEADER_LINES]:
        stripped = line.strip()
        if in_block is not None:
            if in_block in stripped:
                in_block = None          # 同行闭合（含 =end 一类闭合标记）
            continue                     # 块内行按注释行对待
        if not any(stripped.startswith(ld) for ld in _GENERATED_COMMENT_LEADERS):
            matched_block = False
            for opener, closer in _GENERATED_BLOCK_PAIRS:
                if stripped.startswith(opener):
                    if closer not in stripped[len(opener):]:
                        in_block = closer
                    matched_block = True
                    break
            if not matched_block:
                continue                 # 代码行：banner 不在代码行上找
        if any(rx.search(stripped) for rx in GENERATED_STRONG_PATTERNS):
            return True
        if (GENERATED_SELF_REF.search(stripped)
                and any(rx.search(stripped) for rx in GENERATED_WEAK_PATTERNS)):
            return True
    return False


def detect_generated(path, text=None):
    """双信号并集入口（A-P0-1）：路径约定命中或头部 banner 命中 → True。

    text=None（未读入/超限/解码失败）时退化为仅路径信号（如实降级，不猜内容）。
    """
    base = path.rsplit('/', 1)[-1].lower()
    for rx, _src in GENERATED_PATH_PATTERNS:
        if rx.search(base):
            return True
    return has_generated_header(text) if text is not None else False

HONESTY_BLOCK = '''> 本底稿由 analyze_structure.py 自动生成。Python 部分来自 ast 模块的确定性提取（extractor: ast）；
> 其余语言来自表驱动启发式引擎（extractor: brace = 大括号系 / end = end 块系），均为启发式而非事实。
> 已知盲区举例：C/C++ 宏定义函数与函数指针调用、Java/C# 注解处理器与 Lambda 体、Go 接口隐式实现、
> Rust 宏与 trait 默认方法、Ruby define_method 与单行修饰形式、Lua 表方法的两种调用形态、
> JS/TS 对象字面量方法与装饰器、`)` 或 `]` 之后的链式方法调用（`fetch(x).then(h)`、
> `arr[0].push(v)` 形态）。以上均不保证被识别。
> `.h` 一律按 C 的模式表处理（`.hpp` / `.hh` / `.hxx` 才是 C++）：header-only 或大量用 `.h`
> 写 C++ 的工程，模板/命名空间/类语义会走 C 的口径，语言统计也随之为 c——需人工复核。
> 每条调用边标注「实锤(名)/实锤(绑定)/实锤(限定)」或「推断」：verified 必须目标可唯一指认
> （边带 to 身份三元组与 resolved_by 证据来源），末段名多候选收不窄时一律推断（拒绝即未解析；
> 边带 to_candidates 候选列表 ≤5 + candidates_total，绝不「先实锤再让下游剔」）。
> 自引用形态（caller 末段名 == callee）无条件降级为「推断」并标 `self_ref`：真递归、
> super 基类调用与跨 FFI 边界（pybind11 / ctypes / Cython / JNI）的同名自环在静态上不可分，
> 下游调用图不得把 self_ref 边当实锤边画。receiver 为含点属性链的边一律不凭名字判 verified
> （链根在本文件有绑定且末段名唯一命中才可判实锤(绑定)）。
> 调用边的 caller 列为 '-'（MD 表）/ null（JSON facts）表示模块级调用：调用点在
> 模块顶层、不属于任何函数/方法——是正常形态而非缺失数据；查询层 callers 会把它
> 列为 (module)，callees / impact / path 不产生符号级边（模块级调用点无符号身份）。
> files[].generated 按路径约定 + 文件头 banner 双信号标注疑似生成文件（只标注不排除；
> banner 只认注释行，扫描窗口 60 行 / 8192 字符，未读入的文件仅按路径信号判定；
> banner 口径 v2：@generated 词首为强信号单凭自身判定，其余生成/勿改词为弱信号、
> 须同行另有本文件指代词（this file / 本文件 一类）才判定，模式中英双语——引用
> 他人生成物的手写头注释不再仅凭第三人称 do not edit 误标）。
> 同名候选超过上限（500）的尾名，其调用边整条放弃：按 filtered_calls 计数并告警
> name-cap-exceeded（每名一次），不逐条列出。
> 断点清单的「符号表未命中」既可能是真外部调用，也可能是本文件内的抽漏（启发式引擎不保证抽全；
> 边上的 unresolved_reason=not_extracted_here 表示「声明形位置出现过该名字但符号表没有」——
> 抽漏的机检信号）。
> 入口点中的命名启发式、manifest 声明与 listen( 调用均属启发式而非事实。
> 底稿与源码冲突时，以源码为准。'''


# ---------------------------------------------------------------- 通用小工具
def _rel_posix(root, path):
    """绝对/相对路径 → 相对 root 的 POSIX 路径（J2：无盘符、无反斜杠、无前导 ./）。"""
    return os.path.relpath(path, root).replace(os.sep, '/')


_CONTROL_RE = re.compile(r'[\x00-\x1f\x7f-\x9f]')


def _clean_text(text):
    """控制字符（C0/C1：ESC / 换行 / 制表 …）→ 空格。

    P2-5：源码行与路径会进 MD 与 stdout，未净化的控制字符可注入终端 ANSI 序列
    或伪造整行；此处单点收口（JSON 侧另有 json.dumps 转义，无需重复）。
    """
    return _CONTROL_RE.sub(' ', text)


def _md_cell(text):
    """MD 单元格净化（P2-5）：'|' 转义 + 控制字符清空（防表格结构被打碎）。"""
    return _clean_text(str(text)).replace('|', '\\|')


def _line_at(src_lines, lineno):
    """声明行原文（trim、控制字符→空格、≤200 字符；行号越界返回空串）。"""
    if 1 <= lineno <= len(src_lines):
        return _clean_text(src_lines[lineno - 1].strip())[:SIGNATURE_MAX]
    return ''


def _warn(rel, kind, message):
    return {'file': rel, 'kind': kind, 'message': message}


# 疑似 vendored（第三方内嵌）目录的常见名（P1-a/P2-c：**只提示不自动排除**——
# D-10 的默认排除清单是冻结契约，加名单需 spec 修订；提示走 stdout / map notes）
VENDOR_HINTS = frozenset((
    'third_party', 'thirdparty', '3rdparty', 'extern', 'external', 'deps',
    'depends', 'vendor', 'vendored', 'subprojects', 'inc', 'include',
))


def vendored_hints(facts):
    """疑似 vendored 目录探测（P1-a/P2-c）。

    `--exclude` 的匹配语义是「任意层级同名目录」，故按**目录 basename** 归并
    （一条符号路径里的同名单目录只计一次）。两类信号：
      ('exclude', 名, 数, 占比) —— 目录名命中第三方常见名（inc/third_party/…）：
                                   可直接 `--exclude <名>`；
      ('review', 顶层名, 数, 占比) —— 某顶层目录符号占比 > 50% 但名字不像第三方：
                                   只提示复核，**不建议排除**（可能是项目主代码）。
    只作建议，绝不自动排除（D-10 默认排除清单是冻结契约）。
    """
    total = len(facts['symbols'])
    if not total:
        return []
    by_name = {}
    top = {}
    for sym in facts['symbols']:
        parts = sym['file'].split('/')[:-1]
        if parts:
            top[parts[0]] = top.get(parts[0], 0) + 1
        for name in set(p.lower() for p in parts if p):
            by_name[name] = by_name.get(name, 0) + 1
    out = []
    for name in sorted(by_name, key=lambda k: (-by_name[k], k)):
        share = 100.0 * by_name[name] / total
        if name in VENDOR_HINTS:
            out.append(('exclude', name, by_name[name], share))
    for name in sorted(top, key=lambda k: (-top[k], k)):
        share = 100.0 * top[name] / total
        if share > 50.0 and name.lower() not in VENDOR_HINTS:
            out.append(('review', name, top[name], share))
    out.sort(key=lambda item: (item[0] != 'exclude', -item[2]))
    return out


def _rmtree(path):
    """递归删除自测临时目录（只用标准库文件 API，不调任何外部程序）。"""
    if not os.path.isdir(path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        return
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        for fn in filenames:
            try:
                os.remove(os.path.join(dirpath, fn))
            except OSError:
                pass
        for dn in dirnames:
            try:
                os.rmdir(os.path.join(dirpath, dn))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


# ---------------------------------------------------------------- 遍历（R4：排除在遍历阶段生效）
def scan_tree(root, exclude_names, warnings):
    """返回相对 POSIX 路径列表（已排序）。

    排除在**目录剪枝**阶段完成——被排除目录不会被读入、不会产生任何条目，
    因此 files / symbols / imports / calls 四处不可能泄漏探针。
    """
    excludes_lower = set(name.lower() for name in exclude_names)
    out = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        keep = []
        for name in sorted(dirnames):
            full = os.path.join(dirpath, name)
            if name.lower() in excludes_lower:
                continue
            if os.path.islink(full):
                warnings.append(_warn(_rel_posix(root, dirpath), W_SYMLINK,
                                      'symlinked directory skipped: %s' % name))
                continue
            keep.append(name)
        dirnames[:] = keep
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            if os.path.islink(full):
                # secP2-2：文件符号链接同样跳过（目录分支早已跳过）——git 会还原
                # 仓库内 120000 链接，跟随会把仓库外文件内容读进底稿
                warnings.append(_warn(_rel_posix(root, dirpath), W_SYMLINK,
                                      'symlinked file skipped: %s' % fn))
                continue
            out.append(_rel_posix(root, full))
    return out


def read_source(root, rel, lang, files, warnings):
    """读入源文件 → (file_record, data|None, text|None)；读取失败落 read-error。"""
    full = os.path.join(root, *rel.split('/'))
    rec = {'path': rel, 'lines': 0, 'language': lang, 'parse_error': None}
    if not os.path.isfile(full):
        # secP2-7：非普通文件（FIFO/设备/目录）不读——read 无超时，打开即可能挂死
        warnings.append(_warn(rel, W_READ, 'not a regular file; skipped'))
        files.append(rec)
        return rec, None, None
    try:
        size = os.path.getsize(full)
        if size > READ_MAX_BYTES:
            warnings.append(_warn(rel, W_TOO_LARGE,
                                  'file exceeds read cap (%d bytes)' % size))
            files.append(rec)
            return rec, None, None
        with open(full, 'rb') as fh:
            data = fh.read()
    except OSError as exc:
        warnings.append(_warn(rel, W_READ, 'cannot read file: %s' % exc))
        files.append(rec)
        return rec, None, None
    try:
        text = data.decode('utf-8-sig')   # P2-5：剥 BOM（无 BOM 时行为不变），否则
                                          # 首行行首锚定的 import 正则全部失配
    except UnicodeDecodeError:
        text = data.decode('utf-8', 'replace')
        warnings.append(_warn(rel, W_DECODE,
                              'file is not valid UTF-8; lines counted on a '
                              'replacement-decoded copy'))
    rec['lines'] = len(text.splitlines())
    files.append(rec)
    return rec, data, text


# ---------------------------------------------------------------- 构建清单入口点（F6.6 片段，1a 范围）
def manifest_entries(root, rel, base, warnings):
    """从元数据文件读入口点：pyproject.toml / setup.py 的 console-script 段。

    段扫描用冻结正则，**不引入任何 TOML 解析库**（D-23）；setup.py 只做文本匹配，
    绝不执行被分析仓库的代码（D-24）。
    """
    full = os.path.join(root, *rel.split('/'))
    try:
        size = os.path.getsize(full)
        if size > READ_MAX_BYTES:
            # secP2-3：与源文件同闸——超大 manifest 不读入内存（先于 read）
            warnings.append(_warn(rel, W_TOO_LARGE,
                                  'manifest exceeds read cap (%d bytes)' % size))
            return []
        with open(full, 'rb') as fh:
            data = fh.read()
    except OSError as exc:
        warnings.append(_warn(rel, W_MANIFEST, 'cannot read manifest: %s' % exc))
        return []
    try:
        text = data.decode('utf-8-sig')   # P2-5 同源：manifest 首行同样可能带 BOM
    except UnicodeDecodeError:
        warnings.append(_warn(rel, W_MANIFEST, 'manifest is not valid UTF-8'))
        return []
    out = []
    if base == 'pyproject.toml':
        section = None
        for idx, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if line.startswith('[') and line.endswith(']'):
                section = line[1:-1].replace('"', '').replace("'", '').strip()
                continue
            if section in PYPROJECT_SCRIPT_SECTIONS:
                if re.match(r'^[A-Za-z0-9_.\-]+\s*=\s*["\'][^"\']+["\']\s*$', line):
                    out.append({'kind': EP_CONSOLE_SCRIPT, 'file': rel, 'line': idx,
                                'evidence': '%s#%s' % (rel, section),
                                'confidence': CONF_VERIFIED})
    elif base == 'setup.py':
        for idx, raw_line in enumerate(text.splitlines(), 1):
            if 'console_scripts' in raw_line or 'entry_points' in raw_line:
                out.append({'kind': EP_CONSOLE_SCRIPT, 'file': rel, 'line': idx,
                            'evidence': '%s:%d' % (rel, idx),
                            'confidence': CONF_INFERRED})
                break
    elif base == 'package.json':
        lines = text.splitlines()
        for idx, raw_line in enumerate(lines, 1):     # pkg-bin（F6.6，verified）
            if re.match(r'"bin"\s*:', raw_line.strip()):
                out.append({'kind': EP_PKG_BIN, 'file': rel, 'line': idx,
                            'evidence': '%s#bin' % rel,
                            'confidence': CONF_VERIFIED})
        for idx, raw_line in enumerate(lines, 1):     # pkg-script（每个键一条，inferred）
            if re.match(r'"scripts"\s*:\s*\{', raw_line.strip()):
                for j in range(idx, len(lines)):
                    sub = lines[j].strip()
                    if sub.startswith('}'):
                        break
                    m2 = re.match(r'"([\w\-\.$@]+)"\s*:', sub)
                    if m2:
                        out.append({'kind': EP_PKG_SCRIPT, 'file': rel,
                                    'line': j + 1,
                                    'evidence': '%s#scripts.%s' % (rel, m2.group(1)),
                                    'confidence': CONF_INFERRED})
                break
    elif base == 'pom.xml':
        for idx, raw_line in enumerate(text.splitlines(), 1):
            if '<mainClass>' in raw_line:
                out.append({'kind': EP_MANIFEST_MAIN, 'file': rel, 'line': idx,
                            'evidence': '%s#mainClass' % rel,
                            'confidence': CONF_VERIFIED})
    elif base == 'cargo.toml':
        for idx, raw_line in enumerate(text.splitlines(), 1):
            if raw_line.strip() == '[[bin]]':         # 每个 [[bin]] 段各一条（F-a）
                out.append({'kind': EP_MANIFEST_MAIN, 'file': rel, 'line': idx,
                            'evidence': '%s#bin' % rel,
                            'confidence': CONF_VERIFIED})
    elif base == 'composer.json':
        for idx, raw_line in enumerate(text.splitlines(), 1):
            if re.match(r'"bin"\s*:', raw_line.strip()):
                out.append({'kind': EP_MANIFEST_MAIN, 'file': rel, 'line': idx,
                            'evidence': '%s#bin' % rel,
                            'confidence': CONF_VERIFIED})
                break
    return out


# ---------------------------------------------------------------- Python 引擎（F6.2 / F6.4 / F6.5）
def add_symbol(symbols, name, qualname, kind, rel, node, src_lines):
    symbols.append({
        'name': name,
        'qualname': qualname,
        'kind': kind,
        'file': rel,
        'start_line': node.lineno,          # def / class 行（不含装饰器行）
        'end_line': node.end_lineno,        # Python 3.8+ 可用
        'extractor': EXT_AST,
        'signature': _line_at(src_lines, node.lineno),
    })


def assign_names(targets):
    """赋值目标的 Name 列表（多目标 a = b = 1 与解包 a, b = ... 各产生多个符号）。"""
    names = []

    def walk(node):
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                walk(elt)
        elif isinstance(node, ast.Starred):
            walk(node.value)

    for target in targets:
        walk(target)
    return names


def dotted_text(node):
    """Name / Attribute 链 → 点号文本（a.b.c）；其余形态返回 None（不猜）。"""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        parts.reverse()
        return '.'.join(parts)
    return None


def default_exprs(args):
    """参数默认值表达式（在 def 处求值，属外层作用域）。"""
    out = list(args.defaults)
    for item in args.kw_defaults:
        if item is not None:
            out.append(item)
    return out


def collect_calls(node, caller, out):
    """收集子树中的调用点 → (line, caller, callee, receiver)。

    传入节点自身若是调用点同样收录（批次 7 修复：此前只看子树，
    装饰器/参数默认值表达式里的「直接调用」形态——@dec()、x=util()——
    会整条漏进调用边）。
    """
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            out.append((node.lineno, caller, func.attr,
                        dotted_text(func.value)))
        elif isinstance(func, ast.Name):
            out.append((node.lineno, caller, func.id, None))
    for child in ast.iter_child_nodes(node):
        collect_calls(child, caller, out)


def is_main_guard(test):
    """`if __name__ == '__main__'`（单双引号皆可，两侧顺序皆可）。"""
    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]

    def name_of(node):
        return node.id if isinstance(node, ast.Name) else None

    def str_of(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    return ((name_of(left) == '__name__' and str_of(right) == '__main__')
            or (name_of(right) == '__name__' and str_of(left) == '__main__'))


def walk_class(cls, prefix, symbols, calls_raw, rel, src_lines):
    """ClassDef（含嵌套类）：qualname 为点号连接的外层类名。"""
    qname = (prefix + '.' + cls.name) if prefix else cls.name
    add_symbol(symbols, cls.name, qname, K_CLASS, rel, cls, src_lines)
    for dec in cls.decorator_list:
        collect_calls(dec, prefix or None, calls_raw)
    for sub in cls.body:
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_q = qname + '.' + sub.name
            add_symbol(symbols, sub.name, method_q, K_METHOD, rel, sub, src_lines)
            for dec in sub.decorator_list:
                collect_calls(dec, qname, calls_raw)
            for expr in default_exprs(sub.args):
                collect_calls(expr, qname, calls_raw)
            for stmt in sub.body:
                collect_calls(stmt, method_q, calls_raw)
        elif isinstance(sub, ast.ClassDef):
            walk_class(sub, qname, symbols, calls_raw, rel, src_lines)
        else:
            collect_calls(sub, qname, calls_raw)


def python_import_locals(node):
    """import 语句的本地名绑定（B-P0-3 含点链根判定用）。

    `import a.b` 绑定的是 'a'（不是 'a.b'）；`import a.b as c` 绑定 'c'；
    `from m import x as y` 绑定 'y'；star-import 不产生可判定的本地名（不收）。
    """
    out = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            out.add(alias.asname or alias.name.split('.')[0])
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            if alias.name != '*':
                out.add(alias.asname or alias.name)
    return out


def analyze_python(root, rel, data, text, symbols, imports, entry_points,
                   warnings, bindings=None):
    """Python 文件 → (调用点原始表, 解析错误消息|None, 声明形名字集)。

    bindings：{file: set(本地名)}（v3 新增，B-P0-3 链根绑定判定用；None 时不收）。
    声明形名字集：本文件声明位置出现过的名字（含被跳过的嵌套函数）——unresolved
    边的 not_extracted_here 机检信号（A-P0-2）。
    """
    src_lines = text.splitlines()
    try:
        tree = ast.parse(data, filename=rel)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return [], '%s: %s' % (type(exc).__name__, exc), set()
    calls_raw = []
    try:
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_symbol(symbols, stmt.name, stmt.name, K_FUNCTION, rel, stmt, src_lines)
                for dec in stmt.decorator_list:
                    collect_calls(dec, None, calls_raw)
                for expr in default_exprs(stmt.args):
                    collect_calls(expr, None, calls_raw)
                for child in stmt.body:
                    collect_calls(child, stmt.name, calls_raw)
            elif isinstance(stmt, ast.ClassDef):
                walk_class(stmt, '', symbols, calls_raw, rel, src_lines)
            elif isinstance(stmt, ast.Assign):
                kind = K_FUNCTION if isinstance(stmt.value, ast.Lambda) else K_CONSTANT
                for name in assign_names(stmt.targets):
                    add_symbol(symbols, name, name, kind, rel, stmt, src_lines)
                if stmt.value is not None:
                    collect_calls(stmt.value, None, calls_raw)
            elif isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name):
                    kind = K_FUNCTION if isinstance(stmt.value, ast.Lambda) else K_CONSTANT
                    add_symbol(symbols, stmt.target.id, stmt.target.id, kind, rel, stmt, src_lines)
                if stmt.value is not None:
                    collect_calls(stmt.value, None, calls_raw)
            else:
                collect_calls(stmt, None, calls_raw)
            if isinstance(stmt, ast.If) and is_main_guard(stmt.test):
                entry_points.append({
                    'kind': EP_MAIN_GUARD, 'file': rel, 'line': stmt.lineno,
                    'evidence': _line_at(src_lines, stmt.lineno),
                    'confidence': CONF_VERIFIED,
                })
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.extend(python_import_edges(root, rel, node, src_lines))
                if bindings is not None:
                    locals_ = python_import_locals(node)
                    if locals_:
                        bindings.setdefault(rel, set()).update(locals_)
        decl_names = set(node.name for node in ast.walk(tree)
                         if isinstance(node, (ast.FunctionDef,
                                              ast.AsyncFunctionDef,
                                              ast.ClassDef)))
    except RecursionError:
        # P1-3：深嵌套合法文件（超长属性链/加法链）ast.parse 能过、遍历递归爆栈
        # ——单文件隔离（F1）：按 parse-error 优雅降级，不牵连整仓。截断前已
        # 提取的符号/入口如实保留，该文件调用/import 边跳过。
        # 覆盖率口径注（批次 7）：stdlib trace 口径下本分支行事件不可记录
        # （递归超限时 trace 函数自身先收到 RecursionError、线程 tracer 被
        # CPython 静默摘除）——其执行已由 sys.monitoring 交叉口径证实，
        # 属「测量协议限制」而非不可达，见 agent-out/b7-debt-report.md。
        return [], ('RecursionError: AST traversal exceeded the recursion '
                    'limit; per-file isolation (calls/imports of this file '
                    'skipped)'), set()
    return calls_raw, None, decl_names


def import_bases(dir_parts, level):
    """导入解析的起始目录候选（绝对导入：文件所在目录链上行至仓库根；相对导入：按 level 上溯）。"""
    if level == 0:
        bases = []
        current = tuple(dir_parts)
        while True:
            bases.append(current)
            if not current:
                break
            current = current[:-1]
        return bases
    parts = list(dir_parts)
    up = level - 1
    if up > len(parts):
        return None                       # 相对导入越过仓库根：无法解析（不猜）
    if up:
        parts = parts[:len(parts) - up]
    return [tuple(parts)]


def find_module_hit(root, bases, parts):
    """在候选起始目录中查找模块文件：<base>/<parts>.py 或 <base>/<parts>/__init__.py。"""
    for base in bases:
        cand = tuple(base) + tuple(parts)
        if not cand:
            continue
        module = os.path.join(root, *cand) + '.py'
        if os.path.isfile(module):
            return _rel_posix(root, module)
        package = os.path.join(root, *(cand + ('__init__.py',)))
        if os.path.isfile(package):
            return _rel_posix(root, package)
    return None


def python_import_edges(root, rel, node, src_lines):
    """Python import 边（F6.4 v1 口径）：命中仓库内 → verified，否则 inferred。"""
    raw = _line_at(src_lines, node.lineno)
    dir_parts = tuple(rel.split('/')[:-1])
    level = 0
    if isinstance(node, ast.ImportFrom):
        level = node.level or 0
    out = []

    def edge(target, found):
        out.append({
            'file': rel, 'line': node.lineno, 'raw': raw, 'kind': IMP_IMPORT,
            'target': target,
            'confidence': CONF_VERIFIED if found else CONF_INFERRED,
            'external': (not found) and (not level),
            'dynamic': False, 'extractor': EXT_AST,
        })

    if isinstance(node, ast.Import):
        for alias in node.names:
            parts = tuple(alias.name.split('.'))
            target = find_module_hit(root, import_bases(dir_parts, 0), parts)
            edge(target if target else alias.name, bool(target))
        return out
    module = node.module or ''
    module_parts = tuple(module.split('.')) if module else ()
    bases = import_bases(dir_parts, level)
    if bases is None:
        edge('.' * level + module, False)
        return out
    target = None
    if node.names:                       # 先试 from 名对应子模块，再退回模块本身
        target = find_module_hit(root, bases, module_parts + (node.names[0].name,))
    if target is None:
        target = find_module_hit(root, bases, module_parts)
    edge(target if target else ('.' * level + module), bool(target))
    return out


# ---------------------------------------------------------------- 剥离器与双引擎（F6.3，1b）
def _blank(out, start, end):
    """把 [start, end) 区间抹成空格（保留换行，行号不漂移）。"""
    for k in range(start, end):
        if out[k] != '\n':
            out[k] = ' '


def strip_source(text, table, mode):
    """按模式表剥离注释与字符串：mode='comments' 只剥注释（供 import/main/listen
    匹配），mode='all' 连字符串一并剥（供 decl/调用/块计数）。数字字面量按
    BORROW-NOTES §3.4 简化为通用 skip（匹配即跳过）。"""
    for pat in table.get('pre_strip', ()):
        text = re.sub(pat, lambda m: _blank_keep_nl(m.group(0)), text)
    out = list(text)
    n = len(text)
    i = 0
    line_comments = table['line_comment']
    block_pairs = table['block_comment']
    nested_block = table.get('nested_block', False)
    allow_re = mode == 'all' and ('RE',) in table['strings']
    string_pairs = () if mode == 'comments' else sorted(
        (p for p in table['strings'] if p != ('RE',)),
        key=lambda s: -len(s[0]))          # 长开定界符优先（""" 先于 "）
    prev_nonspace = ''
    while i < n:
        ch = text[i]
        if ch in ' \t\r\n':
            if ch == '\n':
                prev_nonspace = ''
            i += 1
            continue
        hit = False
        for lc in line_comments:
            if text.startswith(lc, i):
                j = text.find('\n', i)
                if j == -1:
                    j = n
                _blank(out, i, j)
                i = j
                hit = True
                break
        if hit:
            continue
        for op, cl in block_pairs:
            if text.startswith(op, i):
                if nested_block:
                    # 嵌套块注释（rust/swift/kotlin/scala，Pygments #push/#pop 同构）
                    depth = 1
                    j = i + len(op)
                    while j < n and depth:
                        if text.startswith(op, j):
                            depth += 1
                            j += len(op)
                        elif text.startswith(cl, j):
                            depth -= 1
                            j += len(cl)
                        else:
                            j += 1
                    end = j
                else:
                    k = text.find(cl, i + len(op))
                    end = n if k == -1 else k + len(cl)
                _blank(out, i, end)
                i = end
                hit = True
                break
        if hit:
            continue
        if allow_re and ch == '/' and prev_nonspace in '=(,:;[!&|?{};':
            # JS 族正则字面量启发式（F6.3）：闭 / 后跟 flags 才吞
            j = i + 1
            closed = False
            while j < n:
                c = text[j]
                if c == '\\' and j + 1 < n:
                    j += 2
                    continue
                if c == '\n':
                    break
                if c == '/':
                    closed = True
                    break
                j += 1
            if closed:
                j += 1
                while j < n and text[j].isalpha():
                    j += 1
                _blank(out, i, j)
                i = j
                continue
        if table.get('heredoc') and text.startswith('<<<', i):
            m = re.match(r"<<<['\"]?(\w+)['\"]?\r?\n", text[i:])
            if m:
                term = m.group(1)
                j = i + m.end()
                end = n
                while j <= n:
                    eol = text.find('\n', j)
                    if eol == -1:
                        eol = n
                    if text[j:eol].strip().rstrip(';,') == term:
                        end = eol
                        break
                    if eol >= n:
                        break
                    j = eol + 1
                _blank(out, i, end)
                i = end
                continue
        for spec in string_pairs:
            if text.startswith(spec[0], i):
                close, flags = spec[1], spec[2]
                multiline = 'multiline' in flags
                j = i + len(spec[0])
                closed = False
                while j < n:
                    c = text[j]
                    if c == '\n' and not multiline:
                        break
                    if 'escape' in flags and c == '\\' and j + 1 < n:
                        j += 2
                        continue
                    if ('dquote2' in flags and text.startswith(close, j)
                            and text.startswith(close, j + len(close))):
                        j += 2 * len(close)      # 双写引号 = 转义（C# @""）
                        continue
                    if text.startswith(close, j):
                        j += len(close)
                        closed = True
                        break
                    j += 1
                if closed:
                    end = j
                elif multiline:
                    end = n                      # 未闭多行串：吞到文件尾
                else:
                    end = text.find('\n', i)     # 未闭单行串：只吞到行尾
                    if end == -1:
                        end = n
                _blank(out, i, end)
                i = end
                prev_nonspace = close[-1]       # P2-4：字符串后不可能是正则起点
                hit = True
                break
        if hit:
            continue
        if '0' <= ch <= '9':
            m_num = re.match(r'[0-9][0-9a-zA-Z_.]*', text[i:])
            i += m_num.end() if m_num else 1    # 数字字面量：匹配即跳过（仅 ASCII 数字）
            prev_nonspace = '0'                 # P2-4：数字后不可能是正则起点
            continue
        prev_nonspace = ch
        i += 1
    return ''.join(out)


def _blank_keep_nl(s):
    """等长替换：保留换行、其余抹成空格（pre_strip 用）。"""
    return ''.join(c if c == '\n' else ' ' for c in s)


def find_body_pos(stripped, start):
    """声明 → 块体 '{' 位置；先遇 ';' / '}'（或无体的 '=' 表达式体）返回 None（不猜）。"""
    seg = stripped[start:start + 2000]
    first = None
    for idx, ch in enumerate(seg):
        if ch in '{;=}':
            first = (ch, idx)
            break
    if first is None:
        return None
    ch, idx = first
    if ch == '{':
        return start + idx
    if ch in (';', '}'):
        return None
    seg2 = stripped[start + idx:start + 2000]
    stop = seg2.find(';')
    sub = seg2 if stop == -1 else seg2[:stop]
    b2 = sub.find('{')
    if b2 != -1:                                 # '=' 之后同语句内有 '{'（scala/kotlin 风格）
        return start + idx + b2
    return None


def _brace_match_table(stripped):
    """一次 O(n) 栈扫描：'{' 位置 → 配对 '}' 位置（P2-4 惰性兜底；语义与
    brace_end_pos「首个使深度归零的 '}'」逐位等价）。"""
    match = {}
    stack = []
    for k, ch in enumerate(stripped):
        if ch == '{':
            stack.append(k)
        elif ch == '}' and stack:
            match[stack.pop()] = k
    return match


def brace_end_pos(stripped, body_pos, cache=None):
    """从块体 '{' 起配对计数；不平衡返回 None（禁止回退 start_line——R3）。

    P2-4：块不配平时每个声明都从 body_pos 扫到 EOF（O(声明数 × 文件长度)，恶意
    构造可到分钟-小时级）。裸扫描累计超过预算后，改走一次 O(n) 配对表；正常文件
    零额外开销（cache=None 即旧行为）。
    """
    table = cache.get('table') if cache is not None else None
    if table is not None:
        return table.get(body_pos)
    depth = 0
    for k in range(body_pos, len(stripped)):
        c = stripped[k]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return k
    if cache is not None:
        cache['budget'] = cache.get('budget', 0) - (len(stripped) - body_pos)
        if cache['budget'] <= 0:
            cache['table'] = _brace_match_table(stripped)
    return None


_WORD_RE = re.compile(r'\w+')


def end_block_end_pos(stripped, table, scan_from):
    """end 引擎：按 open/close 关键字计深（Ruby 单行修饰形式不开块——AC-54）。
    返回关闭关键字词首位置，不平衡返回 None。"""
    open_any = set(table['open_kw'])
    open_ls = set(table['open_kw_line_start'])
    close_kw = set(table['close_kw'])
    depth = 1                                    # 声明本身已开启一块
    ls_line = -1                                 # 最近一个「行首开块关键字」所在行的行首偏移
    for m in _WORD_RE.finditer(stripped, scan_from):
        w = m.group(0)
        if w in close_kw:
            depth -= 1
            if depth == 0:
                return m.start()
        elif w in open_any:
            if w == 'do' and stripped.rfind('\n', 0, m.start()) + 1 == ls_line:
                continue                         # P1-7 Ruby：`while/for/until … do` 的 do
                                                 # 是语法标记而非新块（同行已计开块）
            depth += 1
        elif w in open_ls:
            k = m.start() - 1
            while k >= 0 and stripped[k] in ' \t':
                k -= 1
            if k < 0 or stripped[k] == '\n':     # 仅逻辑行首的关键字开启新块
                depth += 1
                ls_line = stripped.rfind('\n', 0, m.start()) + 1
    return None


def _balanced_parens(text):
    """匹配文本的圆括号是否配平（P1-c：跨语句吞并的伪声明判据）。

    `explicit Progress(py::object c) : cb(std::move(c)), cb_none(cb.is_none()) {}`
    的 `std::move(...)` 一类匹配会因 `[^;{}]*` 贪婪跨过右括号吞到函数体的 `{`——
    括号不配平即可识别。构造函数本身的匹配（同一行）是配平的，不受影响。
    """
    depth = 0
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


_DIRECTIVE_LINE_RE = re.compile(r'[ \t]*#')


def _decl_span_start(text, mstart, nstart):
    """BS-5：块体声明的起点不得落在行首预处理指令行上。

    C/C++ 函数模式的「返回类型前缀链」（`(?:[\\w\\*&]+[\\s\\*&]+)+` 的 `\\s` 跨行）
    会把匹配起点锚到紧邻声明上方的指令行（#else/#endif…——剥注释后只剩裸词+
    空白，恰为前缀链燃料），start_line/signature 随之记到指令行：实证
    fmt-3.0.2 format.cc 的 fmt_snprintf 被记到 94 行（#else 行）、signature
    存成 `#else  // _MSC_VER`，真实定义在 95 行（幻觉率实验 Arm B 唯一 off
    的工具侧根源）。起点行是指令行且名字在后续行时，推进到首个「非指令、
    非空」行行首；名字与起点同行的匹配（宏体内函数等）原样返回。

    只对块体角色（func/type/impl）调用；value/bodyless（宏 #define 自身，
    其 signature 正是指令原文）不经此路径。
    """
    ls = text.rfind('\n', 0, mstart) + 1
    moved = False
    while True:
        le = text.find('\n', ls)
        if le == -1:
            le = len(text)
        if nstart < le:
            break                       # 名字在本行：不越过（含指令行同行形态）
        seg = text[ls:le].strip()
        if seg and not seg.startswith('#'):
            break                       # 首个真实声明行
        if le == len(text):
            break                       # 防御：扫到文件尾仍无声明行
        ls = le + 1
        moved = True
    return ls if moved else mstart


def _line_offsets(text):
    offsets = [0]
    for m in re.finditer('\n', text):
        offsets.append(m.end())
    return offsets


def _pos_line(offsets, pos):
    """位置 → 1-based 行号（二分；不引 bisect 以守白名单）。"""
    lo, hi = 0, len(offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if offsets[mid] <= pos:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def compile_table(lang):
    """预编译一张模式表的正则（进程内缓存于表自身）。"""
    table = LANG_TABLES[lang]
    if '_compiled' in table:
        return table
    decls = [(re.compile(p, re.MULTILINE), kind, role)
             for p, kind, role in table['decl']]
    imports = [(re.compile(p, re.MULTILINE), kind, resolver)
               for p, kind, resolver in table['imports']]
    table['_compiled'] = (decls, imports)
    table['_main'] = re.compile(table['main_re']) if table['main_re'] else None
    return table


_LISTEN_RE = re.compile(r'\b[A-Za-z_$][\w$]*\s*\.\s*listen\s*\(')

_JS_EXTS = ('.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx')


def _escapes_root(root, parts, ext):
    """候选绝对路径（解析 `..` 后）是否落在仓库根之外。P1-2：命中仓库外文件
    一律不产 verified 边（external+inferred），与 F6.4「命中仓库内→verified」
    及 Python 引擎的根闭包口径对齐。"""
    abs_p = os.path.abspath(os.path.join(root, *parts) + ext)
    return not (abs_p == root or abs_p.startswith(root + os.sep))


def _fs_exists(root, parts, suffix):
    path = os.path.join(root, *parts) + suffix
    return os.path.isfile(path)


def _resolve_dotfile(root, rel, spec, exts):
    """点号模块路径 → 文件（最深层优先，其次逐级回退）：a.b.C → a/b/C<ext>。"""
    parts = tuple(spec.split('.'))
    bases = []
    d = tuple(rel.split('/')[:-1])
    while True:
        bases.append(d)
        if not d:
            break
        d = d[:-1]
    for base in bases:
        for i in range(len(parts), 0, -1):
            for ext in exts:
                if _fs_exists(root, base + parts[:i], ext):
                    return _rel_posix(root, os.path.join(root,
                                     *(base + parts[:i]))) + ext
                if _fs_exists(root, base + parts[:i] + ('index',), ext):
                    return _rel_posix(root, os.path.join(root,
                                     *(base + parts[:i] + ('index',)))) + ext
    return None


def resolve_import(resolver, root, rel, spec):
    """import 说明符 → (target, found, external, dynamic)。"""
    if resolver == 'js':
        if spec.startswith('.'):
            d = rel.split('/')[:-1]
            ext = os.path.splitext(spec)[1].lower()
            parts = tuple(part for part in spec.split('/')
                          if part not in ('', '.'))
            for base in (tuple(d), ()):
                cand = base + parts
                if ext in _JS_EXTS:
                    # P1-1：已带受支持扩展名 → 按精确路径探测（不再拼扩展名链，
                    # `./app.js` 不再因 `app.js.js` 永不命中而误判 external）
                    if _fs_exists(root, cand, '') \
                            and not _escapes_root(root, cand, ''):
                        return _rel_posix(root, os.path.join(root, *cand)), \
                            True, False, False
                else:
                    for je in _JS_EXTS:
                        if _fs_exists(root, cand, je) \
                                and not _escapes_root(root, cand, je):
                            return _rel_posix(root,
                                              os.path.join(root, *cand)) \
                                + je, True, False, False
                        if _fs_exists(root, cand + ('index',), je) \
                                and not _escapes_root(root, cand + ('index',),
                                                      je):
                            return _rel_posix(root,
                                              os.path.join(root,
                                                           *(cand
                                                             + ('index',)))) \
                                + je, True, False, False
        return None, False, True, False        # bare / 逃逸仓库根 → inferred + external
    if resolver == 'js_dynamic':
        return None, False, True, True         # 动态形态 → inferred + dynamic
    if resolver == 'c_quote':
        d = rel.split('/')[:-1]
        for base in (tuple(d), ()):
            cand = base + (spec,)
            if _escapes_root(root, cand, ''):
                return None, False, True, False   # P1-2 逃逸仓库根：不探测、不产 verified 边
            if _fs_exists(root, cand, ''):
                return _rel_posix(root, os.path.join(root, *cand)), True, False, False
        return None, False, False, False
    if resolver == 'c_angle':
        return None, False, True, False        # 系统头 → inferred + external
    if resolver == 'dotfile':
        t = _resolve_dotfile(root, rel, spec, ('.java',))
        return (t, True, False, False) if t else (None, False, True, False)
    if resolver == 'dotfile_cs':
        t = _resolve_dotfile(root, rel, spec, ('.cs',))
        return (t, True, False, False) if t else (None, False, True, False)
    if resolver == 'dotfile_kt':
        t = _resolve_dotfile(root, rel, spec, ('.kt',))
        return (t, True, False, False) if t else (None, False, True, False)
    if resolver == 'dotfile_swift':
        t = _resolve_dotfile(root, rel, spec, ('.swift',))
        return (t, True, False, False) if t else (None, False, True, False)
    if resolver == 'dotfile_scala':
        t = _resolve_dotfile(root, rel, spec, ('.scala',))
        return (t, True, False, False) if t else (None, False, True, False)
    if resolver == 'go':
        parts = tuple(spec.split('/'))
        if _escapes_root(root, parts, ''):
            return None, False, True, False    # P1-2 逃逸仓库根：不探测、不产 verified 边
        if _fs_exists(root, (spec,), '.go'):
            return spec + '.go', True, False, False
        if os.path.isdir(os.path.join(root, *parts)):
            return spec + '/', True, False, False
        return None, False, True, False        # 模块路径非仓库相对 → inferred + external
    if resolver == 'rust':
        if spec.startswith(('crate::', 'self::', 'super::')):
            head, _, rest = spec.partition('::')
            parts = tuple(rest.split('::')) if rest else ()
            for base in (('src',), ()):
                for i in range(len(parts), 0, -1):
                    cand = base + parts[:i]
                    if _escapes_root(root, cand, '.rs'):
                        return None, False, True, False   # P1-2 逃逸仓库根
                    if _fs_exists(root, cand, '.rs'):
                        return _rel_posix(root, os.path.join(root, *cand)) + '.rs', True, False, False
                    if _fs_exists(root, cand + ('mod',), '.rs'):
                        return _rel_posix(root, os.path.join(root, *(cand + ('mod',)))) + '.rs', True, False, False
        return None, False, True, False        # 外部 crate → inferred + external
    if resolver == 'php_use':
        t = _resolve_dotfile(root, rel, spec.replace('\\', '.'), ('.php',))
        return (t, True, False, False) if t else (None, False, True, False)
    if resolver == 'path':
        if '://' in spec or spec.startswith(('dart:', 'package:')):
            return None, False, True, False
        d = rel.split('/')[:-1]
        for base in (tuple(d), ()):
            cand = base + tuple(part for part in spec.split('/') if part not in ('', '.'))
            if _fs_exists(root, cand, '') and not _escapes_root(root, cand, ''):
                return _rel_posix(root, os.path.join(root, *cand)), True, False, False
        return None, False, True, False
    if resolver == 'ruby_rel':
        d = rel.split('/')[:-1]
        cand = tuple(d) + tuple(spec.split('/'))
        if _fs_exists(root, cand, '.rb'):
            if _escapes_root(root, cand, '.rb'):
                return None, False, True, False   # P1-2 逃逸仓库根：external+inferred
            return _rel_posix(root, os.path.join(root, *cand)) + '.rb', True, False, False
        return None, False, False, False
    if resolver == 'ruby':
        d = tuple(rel.split('/')[:-1])
        while True:
            if _fs_exists(root, d + (spec,), '.rb') \
                    and not _escapes_root(root, d + (spec,), '.rb'):
                return _rel_posix(root, os.path.join(root, *(d + (spec,)))) + '.rb', True, False, False
            if not d:
                break
            d = d[:-1]
        return None, False, True, False
    if resolver == 'lua':
        modpath = spec.replace('.', '/')
        d = rel.split('/')[:-1]
        for base in (tuple(d), ()):
            cand = base + (modpath,)
            if _escapes_root(root, cand, '.lua'):
                return None, False, True, False   # P1-2 逃逸仓库根：不探测、不产 verified 边
            if _fs_exists(root, cand, '.lua'):
                return _rel_posix(root, os.path.join(root, *cand)) + '.lua', True, False, False
        return None, False, True, False
    return None, False, True, False


def _scan_go_block(root, rel, comments_only, start, imports, extractor, line_of):
    """Go import ( 块：逐行取 "path"（F6.4 Go 规则与单行形态一致）。"""
    n = len(comments_only)
    j = comments_only.find('\n', start)
    while j != -1 and j < n:
        j += 1
        line = comments_only[j:comments_only.find('\n', j) if comments_only.find('\n', j) != -1 else n]
        if line.strip().startswith(')'):
            break
        for m in re.finditer(r'"([^"]+)"', line):
            target, found, external, _dyn = resolve_import('go', root, rel, m.group(1))
            imports.append({'file': rel, 'line': line_of(j), 'raw': line.strip(),
                            'kind': IMP_IMPORT, 'target': target or m.group(1),
                            'confidence': CONF_VERIFIED if found else CONF_INFERRED,
                            'external': external, 'dynamic': False,
                            'extractor': extractor})
        j = comments_only.find('\n', j)
        if j == -1:
            break


def analyze_generic(root, rel, lang, data, text, symbols, imports,
                    entry_points, warnings):
    """brace/end 双引擎（表驱动）：返回 (调用点原始表, 停用表滤掉的调用数, 声明形名字集)。

    声明形名字集（v3 新增）：decl 正则命中且非停用词的名字——含后续因嵌套等原因
    未进符号表的名字，是 unresolved 边 not_extracted_here 机检信号的依据（A-P0-2）。
    """
    table = compile_table(lang)
    extractor = lang_extractor(lang)
    stripped = strip_source(text, table, 'all')
    comments_only = strip_source(text, table, 'comments')
    offsets = _line_offsets(text)
    total_lines = len(text.splitlines())
    src_lines = text.splitlines()        # P2-11：line_of 闭包复用（原来每次调用重切全文）

    def pos_line(pos):
        return min(_pos_line(offsets, pos), total_lines)

    def line_of(line_no):
        return _line_at(src_lines, line_no)   # P2-11：一次切分，闭包复用

    # ---- 1) 声明扫描（默认在完全剥离文本上；decl_on_comments 语言用仅剥注释文本）----
    found = []
    decl_spans = []
    decl_names = set()
    decls_compiled, imports_compiled = table['_compiled']
    decl_text = comments_only if table.get('decl_on_comments') else stripped
    for rx, kind, role in decls_compiled:
        for m in rx.finditer(decl_text):
            # P1-c 守卫只对「跨到块体 `{`」的模式生效：多数语言的声明模式只匹配
            # 到 `(` 为止（天然不配平），不能一并否掉
            mtext = m.group(0)
            if '{' in mtext and not _balanced_parens(mtext):
                # 括号不配平的匹配是跨语句吞并的伪声明（C++ 构造函数初始化列表、
                # 多行 std::stable_sort 调用的 lambda 体）——不进符号表，其区间也
                # 不当「声明自身」过滤（该行里的真实调用应照常产出）
                continue
            name = m.groupdict().get('n')
            mstart = m.start()
            if name and role in ('func', 'type', 'impl'):
                # BS-5：前缀链可跨行吞掉行首指令行（#else/#endif）→ 起点回归真实声明行
                mstart = _decl_span_start(decl_text, mstart, m.start('n'))
            decl_spans.append((mstart, m.end()))
            if not name:
                continue
            if name in table['decl_stops']:
                continue
            if name.startswith('~') or name.startswith('operator'):
                continue                       # 析构/运算符重载：盲区不猜
            decl_names.add(name)
            found.append((mstart, m.end(), name,
                          m.groupdict().get('recv'), kind, role))
    found.sort(key=lambda item: (item[0], -item[1]))

    # ---- 2) 逐声明解析块体 + 作用域栈 → 符号 ----
    scopes = []            # [end_pos, qualname, is_type]
    spans = []             # (start, end, qualname) 供 caller 归属
    unbalanced = False
    brace_cache = {'budget': 4 * (len(stripped) + 1)}   # P2-4：裸配对扫描预算
    for start, mend, name, recv, kind, role in found:
        while scopes and scopes[-1][0] < start:
            scopes.pop()
        top = scopes[-1] if scopes else None
        top_type = top[1] if top and top[2] else None
        top_func = top[1] if top and not top[2] else None
        start_line = pos_line(start)

        if role == 'value':
            if top_func is not None:
                continue                       # 函数体内赋值不算顶层常量
            qualname = (top_type + '.' + name) if top_type else name
            symbols.append({'name': name, 'qualname': qualname, 'kind': kind,
                            'file': rel, 'start_line': start_line,
                            'end_line': start_line, 'extractor': extractor,
                            'signature': line_of(start_line)})
            continue

        if role == 'bodyless':
            if top_func is not None:
                continue
            qualname = (top_type + '.' + name) if top_type else name
            symbols.append({'name': name.split('.')[-1], 'qualname': qualname,
                            'kind': kind, 'file': rel, 'start_line': start_line,
                            'end_line': start_line, 'extractor': extractor,
                            'signature': line_of(start_line)})
            continue

        # type / impl / func 都需要块体
        if extractor == EXT_END:
            body_pos = start                   # end 引擎：从声明起计关键字深度
            close_pos = end_block_end_pos(stripped, table, mend)
        else:
            body_pos = find_body_pos(stripped, start)
            close_pos = brace_end_pos(stripped, body_pos, brace_cache) \
                if body_pos is not None else None

        if role == 'impl':
            if close_pos is None:
                continue                       # 不平衡的 impl：不推作用域不产符号
            scopes.append([close_pos, name, True])
            spans.append((start, close_pos, name))
            continue

        if role == 'type':
            if close_pos is None:
                if extractor == EXT_END or body_pos is not None:
                    if not unbalanced:
                        unbalanced = True
                        warnings.append(_warn(rel, W_UNBALANCED,
                                              'unbalanced block; end_line unknown for later declarations'))
                    symbols.append({'name': name, 'qualname': name, 'kind': kind,
                                    'file': rel, 'start_line': start_line,
                                    'end_line': None, 'extractor': extractor,
                                    'signature': line_of(start_line)})
                continue                       # brace 无体声明（如 struct X;）静默跳过
            parent = top_type or (top[1] if top and top[2] else None)
            qualname = (parent + '.' + name) if parent else name
            end_line = pos_line(close_pos)
            symbols.append({'name': name, 'qualname': qualname, 'kind': kind,
                            'file': rel, 'start_line': start_line,
                            'end_line': end_line, 'extractor': extractor,
                            'signature': line_of(start_line)})
            scopes.append([close_pos, qualname, True])
            spans.append((start, close_pos, qualname))
            continue

        # role == 'func'
        is_method = False
        if recv:
            qualname = recv + '.' + name
            is_method = True
        elif ('.' in name) or (':' in name):
            qualname = name.replace(':', '.')
            is_method = True
        elif top_func is not None:
            continue                           # 嵌套函数：不算符号，调用归外层
        elif top_type is not None:
            qualname = top_type + '.' + name
            is_method = True
        else:
            qualname = name
        if close_pos is None:
            if extractor == EXT_END or body_pos is not None:
                # 不平衡：end_line=null+告警（禁止回退 start_line——R3）
                if not unbalanced:
                    unbalanced = True
                    warnings.append(_warn(rel, W_UNBALANCED,
                                          'unbalanced block; end_line unknown (never guessed)'))
                symbols.append({'name': name, 'qualname': qualname,
                                'kind': K_METHOD if is_method else K_FUNCTION,
                                'file': rel, 'start_line': start_line,
                                'end_line': None, 'extractor': extractor,
                                'signature': line_of(start_line)})
            # brace 无体签名（trait 签名/抽象方法/表达式体）：静默跳过
            continue
        end_line = pos_line(close_pos)
        symbols.append({'name': name, 'qualname': qualname,
                        'kind': K_METHOD if is_method else K_FUNCTION,
                        'file': rel, 'start_line': start_line,
                        'end_line': end_line, 'extractor': extractor,
                        'signature': line_of(start_line)})
        scopes.append([close_pos, qualname, False])
        spans.append((start, close_pos, qualname))

    # ---- 3) main-function / listen-call 入口点（F6.6）----
    if table['_main'] is not None:
        for m in table['_main'].finditer(comments_only):
            line_no = pos_line(m.start())
            entry_points.append({'kind': EP_MAIN_FUNCTION, 'file': rel,
                                 'line': line_no, 'evidence': line_of(line_no),
                                 'confidence': CONF_VERIFIED})
    if table.get('listen'):
        for m in _LISTEN_RE.finditer(comments_only):
            line_no = pos_line(m.start())
            entry_points.append({'kind': EP_LISTEN, 'file': rel,
                                 'line': line_no, 'evidence': line_of(line_no),
                                 'confidence': CONF_INFERRED})

    # ---- 4) import 边（注释剥离文本；字符串保留以读说明符）----
    for rx, kind, resolver in imports_compiled:
        for m in rx.finditer(comments_only):
            if resolver == 'go_block':
                _scan_go_block(root, rel, comments_only, m.start(), imports,
                               extractor, lambda p: pos_line(p))
                continue
            spec = m.group(1)
            if not spec:
                continue
            target, found_flag, external, dynamic = resolve_import(
                resolver, root, rel, spec)
            line_no = pos_line(m.start(1))     # 取捕获组起点，防 ^\s* 跨行吞并
            imports.append({'file': rel, 'line': line_no,
                            'raw': line_of(line_no), 'kind': kind,
                            'target': target or spec,
                            'confidence': CONF_VERIFIED if found_flag else CONF_INFERRED,
                            'external': external, 'dynamic': dynamic,
                            'extractor': extractor})

    # ---- 5) 调用边（剥离文本；F6.5 全语言统一口径）----
    sep = table['member_sep']
    sep_re = sep if sep.startswith('[') else re.escape(sep)
    name_re = r'[A-Za-z_$][\w$]*'
    bare_re = re.compile(r'(?<![\w$.:@])(?P<n>' + name_re + r')\s*\(')
    member_re = re.compile(r'(?P<recv>' + name_re + r'(?:\s*' + sep_re +
                           r'\s*' + name_re + r')*)\s*' + sep_re +
                           r'\s*(?P<n>' + name_re + r')\s*\(')
    macro_re = re.compile(r'\b(?P<n>[A-Za-z_]\w*)\s*!\s*\(')
    new_re = re.compile(r'\bnew\s+(?P<n>[A-Z][\w$]*)\s*\(')

    call_stops = set(table['call_stops'])
    global_stops = set(table['global_stops'])
    macro_stops = set(table.get('macro_stops', ()))
    filtered = 0
    hits = []
    for m in member_re.finditer(stripped):
        hits.append((m.start('n'), m.group('n'), m.group('recv')))
    for m in bare_re.finditer(stripped):
        hits.append((m.start('n'), m.group('n'), None))
    if table.get('new_call'):
        for m in new_re.finditer(stripped):
            hits.append((m.start('n'), m.group('n'), None))
    hits.sort(key=lambda item: item[0])
    # 声明自身（def f( / func f( / function f(）不是调用点：落在声明匹配区间内的
    # 命中剔除。P2-4③：区间按 start 排序 + 前缀最大 end + 二分 → O(log m) 判定
    # （原为「命中数 × 声明数」双重线性）
    span_pairs = sorted(decl_spans)
    span_starts = [pair[0] for pair in span_pairs]
    prefix_max_end = []
    run_end = -1
    for _span_s, _span_e in span_pairs:
        if _span_e > run_end:
            run_end = _span_e
        prefix_max_end.append(run_end)

    def in_decl_span(pos):
        if not span_starts or span_starts[0] > pos:
            return False
        lo, hi = 0, len(span_starts) - 1
        while lo < hi:                       # 最后一个 start <= pos 的下标
            mid = (lo + hi + 1) // 2
            if span_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return prefix_max_end[lo] > pos

    hits = [h for h in hits if not in_decl_span(h[0])]
    for m in macro_re.finditer(stripped):
        if m.group('n') in macro_stops:
            filtered += 1                      # 宏形态：只计数不列条
    seen = set()
    ordered_calls = []
    for pos, callee, receiver in hits:
        if callee in call_stops:
            continue
        if callee in global_stops:
            filtered += 1                      # 内建/全局名：只计数不列条
            continue
        line_no = pos_line(pos)
        key = (rel, line_no, callee)
        if key in seen:                        # (file, line, callee) 去重
            continue
        seen.add(key)
        caller = None
        best_start = -1
        for s_start, s_end, s_name in spans:
            if s_start <= pos < s_end and s_start > best_start:
                best_start = s_start
                caller = s_name
        ordered_calls.append((line_no, caller, callee, receiver))
    return ordered_calls, filtered, decl_names


# ---------------------------------------------------------------- 五件套组装
def build_facts(repo, selected_langs=None, extra_excludes=None):
    """扫描仓库 → facts 字典（J1/J2/J7：顶层 12 键、POSIX 相对路径、稳定排序）。"""
    root = os.path.abspath(repo)
    excludes = set(DEFAULT_EXCLUDES)
    for name in (extra_excludes or ()):
        name = name.strip()
        if name:
            excludes.add(name)

    warnings = []
    files = []
    symbols = []
    imports = []
    calls = []
    entry_points = []
    call_units = []                      # (rel, lang, [(line, caller, callee, receiver)])
    filtered_calls = 0
    py_bindings = {}                     # A-P0-2/B-P0-3：file → set(import 本地名)
    decl_names_by_file = {}              # A-P0-2：file → set(声明形名字，抽漏机检信号)

    for rel in scan_tree(root, excludes, warnings):
        base = os.path.basename(rel)
        ext = os.path.splitext(base)[1].lower()
        if base.lower() in METADATA_BASENAMES:
            # P2-6：大小写归一（Windows 文件系统不敏感，目录排除口径亦不敏感）；
            # 归一后的 basename 同时决定 manifest_entries 内的分派分支
            entry_points.extend(manifest_entries(root, rel, base.lower(), warnings))
            continue
        lang = EXT_TO_LANG.get(ext)
        if lang is None:
            rec, _data, _text = read_source(root, rel, None, files, warnings)
            # A-P0-1：未支持扩展名只做路径信号判定（无内容可扫，如实降级）
            rec['generated'] = detect_generated(rel)
            warnings.append(_warn(rel, W_UNSUPPORTED,
                                  'unsupported file extension: %s' % (ext or '(none)')))
            continue
        rec, data, text = read_source(root, rel, lang, files, warnings)
        # A-P0-1：生成文件双信号标注（只标注不排除，J4）；读取失败时 text=None，
        # detect_generated 如实退化为仅路径信号
        rec['generated'] = detect_generated(rel, text)
        if data is None:
            continue
        if len(data) > PARSE_MAX_BYTES:
            warnings.append(_warn(rel, W_TOO_LARGE,
                                  'file exceeds parse cap (%d bytes); not parsed'
                                  % len(data)))
            continue
        if selected_langs is not None and lang not in selected_langs:
            continue
        if lang == 'python':
            unit, parse_error, decl_names = analyze_python(
                root, rel, data, text, symbols, imports, entry_points,
                warnings, py_bindings)
            if parse_error is not None:
                rec['parse_error'] = parse_error
                warnings.append(_warn(rel, W_PARSE, parse_error))
            else:
                call_units.append((rel, lang, unit))
                decl_names_by_file[rel] = decl_names
        else:                          # brace / end 双引擎（表驱动，1b）
            unit, extra_filtered, decl_names = analyze_generic(
                root, rel, lang, data, text, symbols, imports,
                entry_points, warnings)
            filtered_calls += extra_filtered
            if unit:
                call_units.append((rel, lang, unit))
                decl_names_by_file[rel] = decl_names

    for rec in files:                    # 命名启发式入口点（清单口径，与引擎无关）
        parts = rec['path'].split('/')
        base = parts[-1]
        for rule_base, rule_dir in FILENAME_ENTRY_RULES:
            if base != rule_base:
                continue
            if rule_dir is None or (len(parts) >= 2 and parts[-2] == rule_dir):
                entry_points.append({
                    'kind': EP_FILENAME, 'file': rec['path'], 'line': 1,
                    'evidence': base,
                    'confidence': CONF_INFERRED,
                })
                break

    # A-P0-2：惰性配对表（末段名/限定名 → [符号引用]）替代 v2 的末段名计数表——
    # 一次构建、查询 O(1)；多候选时给出候选列表而非只给计数。防 O(K²)（B-P2-3）：
    # 任何消解策略都只对「该名字的候选数组」做线性扫描，绝不做 ref×cand 两两打分。
    by_tail = {}
    by_qual = {}
    for sym in symbols:
        by_tail.setdefault(sym['qualname'].split('.')[-1], []).append(sym)
        by_qual.setdefault(sym['qualname'], []).append(sym)

    # import 收窄的文件级依据：本文件 verified 且非外部的 import 目标文件集合
    file_set = set(rec['path'] for rec in files)
    import_targets = {}
    for imp in imports:
        if imp['confidence'] == CONF_VERIFIED and not imp.get('external') \
                and imp.get('target') in file_set:
            import_targets.setdefault(imp['file'], set()).add(imp['target'])

    def _ident(sym):
        return {'file': sym['file'], 'qualname': sym['qualname'],
                'start_line': sym['start_line']}

    capped = {}                          # 尾名 → 首个触发上限的文件（每名只告警一次）
    for rel, lang, raw_calls in call_units:
        seen = set()
        # A3-3：调用边的 extractor 与语言一致（原先硬编码 'ast'，brace/end 语言
        # 的调用边被标成 ast，与同一批文件的符号表口径矛盾）
        extractor = EXT_AST if lang == 'python' else lang_extractor(lang)
        for line, caller, callee, receiver in raw_calls:
            if lang == 'python' and callee in BUILTIN_NAMES:
                # P2-8/D-21：Python 内建清单只配 Python（ast 引擎）；其余 15 门
                # 启发式语言由各自 global_stops 收口——否则 JS `arr.map(fn)` /
                # `list.filter(...)` 被当内建名静默吞掉
                filtered_calls += 1      # 内建/全局名只计数、不逐条列出
                continue
            key = (rel, line, callee)
            if key in seen:              # (file, line, callee) 去重
                continue
            seen.add(key)

            cands = by_tail.get(callee) or ()
            n_cand = len(cands)
            if n_cand > CANDIDATE_CAP:
                # B-P2-3：同名候选超上限——放弃该边（宁可少、不错），计 filtered
                # 并对该名告警一次（message 里点名尾名与候选数）
                filtered_calls += 1
                if callee not in capped:
                    capped[callee] = rel
                    warnings.append(_warn(
                        rel, W_NAME_CAP,
                        'tail name %r has %d same-name symbols (cap %d); its '
                        'call edges are dropped (counted in filtered_calls)'
                        % (callee, n_cand, CANDIDATE_CAP)))
                continue

            cand_sorted = sorted(cands, key=lambda s: (s['file'], s['start_line'],
                                                       s['qualname'])) \
                if n_cand else []
            to = None
            to_candidates = None
            candidates_total = None
            if n_cand >= 2:
                to_candidates = [_ident(s) for s in cand_sorted[:TO_CANDIDATE_LIMIT]]
                candidates_total = n_cand

            self_shape = bool(caller) and _lastseg(caller) == callee
            dotted = bool(receiver) and '.' in receiver
            unresolved_reason = None
            resolved_by = None
            self_ref = False

            if n_cand == 0:
                # 未命中：推断 + 机检理由（not_extracted_here = 本文件声明形位置
                # 出现过该名字但符号表没有——「抽漏」信号，A-P0-2）
                conf = CONF_INFERRED
                resolution = R_UNRESOLVED
                unresolved_reason = U_NOT_EXTRACTED \
                    if callee in decl_names_by_file.get(rel, ()) else U_EXTERNAL
            elif self_shape:
                # B0 修订 A（无条件降级）：caller 末段名 == callee 一律推断并标
                # self_ref——真递归、`super().__init__()`（receiver=null）与跨 FFI
                # 同名自环静态不可分，不再依赖 receiver 形态或候选数
                conf = CONF_INFERRED
                resolution = R_SELF_REF
                self_ref = True
                if n_cand == 1:
                    to = _ident(cand_sorted[0])
            elif dotted:
                # B-P0-3 形态级排他：含点属性链一律不凭名字判 verified（无论候选
                # 数——D5-P0-1 的教训：同名命中可能就是调用者自己）。链根在本文件
                # 有绑定（import 本地名 / 同名顶层符号）且末段名唯一命中才判
                # 实锤(绑定)；多候选收不窄 → 拒绝即未解析（B-P0-4）
                root_seg = receiver.split('.', 1)[0]
                if n_cand == 1:
                    to = _ident(cand_sorted[0])
                    if root_seg in py_bindings.get(rel, ()) or any(
                            s['file'] == rel for s in by_qual.get(root_seg, ())):
                        conf = CONF_VERIFIED
                        resolution = R_UNIQUE
                        resolved_by = RB_BINDING
                    else:
                        conf = CONF_INFERRED
                        resolution = R_UNIQUE
                else:
                    conf = CONF_INFERRED
                    resolution = R_AMBIGUOUS
            else:
                if n_cand == 1:
                    # 策略 D：末段名唯一命中（v2 语义保留），限定名形态升级标签
                    conf = CONF_VERIFIED
                    resolution = R_UNIQUE
                    to = _ident(cand_sorted[0])
                    resolved_by = RB_QUALIFIED if (
                        receiver and '.' not in receiver
                        and cand_sorted[0]['qualname'] == receiver + '.' + callee
                    ) else RB_NAME
                else:
                    # 策略 E（B-P0-4）：多候选先收窄——同文件唯一 → import 目标
                    # 唯一 → 限定名唯一；收不窄一律推断（拒绝即未解析），绝不
                    # 「先 verified 再让下游剔」
                    narrowed = None
                    same = [s for s in cand_sorted if s['file'] == rel]
                    if len(same) == 1:
                        narrowed, resolved_by = same[0], RB_NAME
                    else:
                        imported = [s for s in cand_sorted
                                    if s['file'] in import_targets.get(rel, ())]
                        if len(imported) == 1:
                            narrowed, resolved_by = imported[0], RB_BINDING
                        elif receiver and '.' not in receiver:
                            qhits = by_qual.get(receiver + '.' + callee, ())
                            if len(qhits) == 1:
                                narrowed, resolved_by = qhits[0], RB_QUALIFIED
                    if narrowed is not None:
                        conf = CONF_VERIFIED
                        resolution = R_UNIQUE
                        to = _ident(narrowed)
                    else:
                        conf = CONF_INFERRED
                        resolution = R_AMBIGUOUS

            edge = {
                'file': rel, 'line': line, 'caller': caller, 'callee': callee,
                'receiver': receiver,
                'confidence': conf,
                'candidates': n_cand,
                'ambiguous': n_cand > 1,
                'extractor': extractor,
                'to': to,                    # A-P0-2：唯一指认的目标身份（否则 null）
                'to_candidates': to_candidates,   # 多候选候选列表（≤5）
                'candidates_total': candidates_total,
                'resolution': resolution,    # unique|ambiguous|unresolved|self_ref
                'resolved_by': resolved_by,  # verified 证据来源（name|binding|qualified）
            }
            if unresolved_reason is not None:
                edge['unresolved_reason'] = unresolved_reason
            if self_ref:
                edge['self_ref'] = True
            calls.append(edge)

    files.sort(key=lambda r: r['path'])
    symbols.sort(key=lambda s: (s['file'], s['start_line'], s['qualname']))
    imports.sort(key=lambda i: (i['file'], i['line'], i['target']))
    # A-P0-2：to 作稳定次级键（(file, line, callee) 去重后不新增分桶，仅锁序）
    calls.sort(key=lambda c: (c['file'], c['line'], c['callee'],
                              (c['to'] or {}).get('qualname', '')))
    entry_points.sort(key=lambda e: (e['kind'], e['file'], e['line']))
    warnings.sort(key=lambda w: (w['file'], w['kind'], w['message']))

    languages = sorted(set(
        rec['language'] for rec in files
        if rec['language'] and (selected_langs is None or rec['language'] in selected_langs)))

    counts = {
        'files': len(files),
        'symbols': len(symbols),
        'imports': len(imports),
        'calls': len(calls),
        'calls_verified': sum(1 for c in calls if c['confidence'] == CONF_VERIFIED),
        'calls_inferred': sum(1 for c in calls if c['confidence'] == CONF_INFERRED),
        'entry_points': len(entry_points),
        'parse_errors': sum(1 for rec in files if rec['parse_error']),
        'filtered_calls': filtered_calls,
        'languages': len(languages),
        'unsupported_files': sum(1 for rec in files if rec['language'] is None),
    }
    return {
        'schema_version': SCHEMA_VERSION,
        'tool': TOOL_NAME,
        'engine_version': ENGINE_VERSION,
        'root_name': os.path.basename(root) or root,
        'languages': languages,
        'counts': counts,
        'files': files,
        'symbols': symbols,
        'imports': imports,
        'calls': calls,
        'entry_points': entry_points,
        'warnings': warnings,
    }


def dumps_facts(facts):
    """J5：固定序列化参数（ensure_ascii=False / sort_keys=True / indent=2）。"""
    return json.dumps(facts, ensure_ascii=False, sort_keys=True, indent=2)


# ---------------------------------------------------------------- 人读底稿（F3）
def _conf_label(confidence, resolved_by=None):
    """B-P0-2：标签与置信来源绑定——实锤必须带括号说明凭什么。

    verified + resolved_by：实锤(名) / 实锤(绑定) / 实锤(限定)；verified 无
    resolved_by（import / 入口点等非调用边场景）→ 实锤；inferred → 推断。
    """
    if confidence != CONF_VERIFIED:
        return '推断'
    if resolved_by == RB_NAME:
        return '实锤(名)'
    if resolved_by == RB_BINDING:
        return '实锤(绑定)'
    if resolved_by == RB_QUALIFIED:
        return '实锤(限定)'
    return '实锤'


def render_md(facts):
    """MD 底稿：小节标题字面固定（M3），不嵌源码正文（M1），不截断（M2）。"""
    counts = facts['counts']
    out = []
    add = out.append
    add('# 结构事实底稿 · %s' % _md_cell(facts['root_name']))
    add('')
    add('- 工具：%s（schema_version %d，engine_version %d）'
        % (facts['tool'], facts['schema_version'],
           facts.get('engine_version') or 0))
    add('- 语言：%s' % _md_cell(', '.join(facts['languages'])
                               if facts['languages'] else '（无）'))
    add('- 计数摘要：files=%d symbols=%d imports=%d calls=%d（实锤 %d / 推断 %d）'
        'entry_points=%d warnings=%d'
        % (counts['files'], counts['symbols'], counts['imports'], counts['calls'],
           counts['calls_verified'], counts['calls_inferred'], counts['entry_points'],
           len(facts['warnings'])))
    add('')

    add('## 文件清单')
    add('')
    add('| 路径 | 行数 | 语言 | 生成 |')
    add('|---|---|---|---|')
    for rec in facts['files']:
        add('| %s | %d | %s | %s |'
            % (_md_cell(rec['path']), rec['lines'],
               _md_cell(rec['language'] or '-'),
               '是' if rec.get('generated') else '-'))
    if not facts['files']:
        add('| （无） | 0 | - | - |')
    add('')

    add('## 符号表')
    add('')
    add('| qualname | kind | 位置 | extractor |')
    add('|---|---|---|---|')
    for sym in facts['symbols']:
        end = sym['end_line'] if sym['end_line'] is not None else '?'
        add('| %s | %s | %s:%s-%s | %s |'
            % (_md_cell(sym['qualname']), _md_cell(sym['kind']),
               _md_cell(sym['file']), sym['start_line'], end,
               _md_cell(sym['extractor'])))
        if sym['signature']:
            add('    %s' % _md_cell(sym['signature']))
    if not facts['symbols']:
        add('| （无） | - | - | - |')
    add('')

    add('## 依赖边（import）')
    add('')
    add('| 位置 | 目标 | 置信 | kind | external |')
    add('|---|---|---|---|---|')
    for imp in facts['imports']:
        add('| %s:%d | %s | %s | %s | %s |'
            % (_md_cell(imp['file']), imp['line'], _md_cell(imp['target']),
               _conf_label(imp['confidence'],
                           RB_BINDING if imp['confidence'] == CONF_VERIFIED
                           else None),
               _md_cell(imp['kind']),
               'yes' if imp['external'] else 'no'))
    if not facts['imports']:
        add('| （无） | - | - | - | - |')
    add('')

    add('## 调用边')
    add('')
    add('置信列：实锤(名)=末段名唯一命中或多候选经同文件唯一收窄；'
        '实锤(绑定)=import 绑定收窄，或含点链根在本文件有绑定且末段名唯一命中；'
        '实锤(限定)=receiver+callee 限定名精确命中。推断=未命中、多候选收不窄、'
        '自引用形态（无条件降级）或含点链无绑定。verified 边必带 to 目标身份。')
    add('')
    add('| 位置 | callee | caller | receiver | 置信 | 候选 | 解析 |')
    add('|---|---|---|---|---|---|---|')
    for call in facts['calls']:
        res = call.get('resolution')
        if res == R_UNIQUE and call.get('to'):
            res_cell = '%s @%s:%d' % (call['to']['qualname'], call['to']['file'],
                                      call['to']['start_line'])
        elif res == R_AMBIGUOUS:
            res_cell = '%d 个候选' % (call.get('candidates_total')
                                      or call['candidates'])
        elif res == R_UNRESOLVED:
            res_cell = '未命中·%s' % (call.get('unresolved_reason') or 'external')
        elif res == R_SELF_REF:
            res_cell = '自引用'
        else:
            res_cell = res or '-'
        add('| %s:%d | %s | %s | %s | %s | %d | %s |'
            % (_md_cell(call['file']), call['line'], _md_cell(call['callee']),
               _md_cell(call['caller'] or '-'), _md_cell(call['receiver'] or '-'),
               _conf_label(call['confidence'], call.get('resolved_by')),
               call['candidates'], _md_cell(res_cell)))
    if not facts['calls']:
        add('| （无） | - | - | - | - | 0 | - |')
    add('')

    add('## 断点清单（Where the graph stops）')
    add('')
    add('「符号表未命中」既可能是真外部调用，也可能是本文件内的抽漏（启发式引擎不保证抽全）。')
    add('')
    inferred = [c for c in facts['calls'] if c['confidence'] == CONF_INFERRED]
    if not inferred:
        add('（无推断调用边：所有调用点都能对上本仓库符号表）')
    else:
        by_file = {}
        for call in inferred:
            by_file.setdefault(call['file'], []).append(call)
        for path in sorted(by_file):
            add('### %s' % _md_cell(path))
            add('')
            for call in sorted(by_file[path], key=lambda c: (c['line'], c['callee'])):
                add('- 行 %d 调用 `%s` — 断因：符号表未命中'
                    '（外部符号、跨语言绑定或本文件抽漏皆可能）'
                    % (call['line'], _md_cell(call['callee'])))
            add('')

    add('## 入口点')
    add('')
    add('| kind | 位置 | evidence | 置信 |')
    add('|---|---|---|---|')
    for entry in facts['entry_points']:
        add('| %s | %s:%d | %s | %s |'
            % (_md_cell(entry['kind']), _md_cell(entry['file']), entry['line'],
               _md_cell(entry['evidence']), _conf_label(entry['confidence'])))
    if not facts['entry_points']:
        add('| （无） | - | - | - |')
    add('')

    add('## 解析失败与警告')
    add('')
    if not facts['warnings']:
        add('（无）')
    else:
        for warn in facts['warnings']:
            add('- [%s] %s：%s' % (_md_cell(warn['kind']), _md_cell(warn['file']),
                                   _md_cell(warn['message'])))
    add('')

    add('## 诚实性声明')
    add('')
    add(HONESTY_BLOCK)
    add('')
    return '\n'.join(out)


def write_artifacts(facts, outdir):
    """落盘两份产物（J5：UTF-8 无 BOM、LF 换行）。返回 (json_path, md_path)。"""
    os.makedirs(outdir, exist_ok=True)
    json_path = os.path.join(outdir, 'structure-facts.json')
    md_path = os.path.join(outdir, 'structure-facts.md')
    with open(json_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(dumps_facts(facts))
        fh.write('\n')
    with open(md_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(render_md(facts))
    return json_path, md_path


# ---------------------------------------------------------------- CLI（F1）
def parse_lang(raw):
    """--lang 取值 → (语言集合|None=auto, 错误消息|None)：别名归一 + 闭集校验。"""
    value = (raw or 'auto').strip().lower()
    if value == 'auto':
        return None, None
    selected = set()
    for token in value.split(','):
        token = token.strip()
        if not token:
            continue
        lang = LANG_ALIASES.get(token, token)
        if lang not in LANG_IDS:
            return None, 'unknown language id: %s' % token
        selected.add(lang)
    if not selected:
        return None, '--lang has no valid language id'
    return selected, None


def main(argv):
    # Windows 控制台常见 GBK 编码：强制 UTF-8 输出（对齐既有校验脚本惯例）
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    if '--selftest' in argv[1:]:
        return run_selftest()
    # 查询层子命令分发（F8/D-39）：已知查询命令短路；`analyze` 剥壳后走 v1 流程；
    # 其余首参（含 mapx 等伪造名）按仓库路径处理——v1 命令行不破坏（AC-38）。
    if len(argv) > 1 and argv[1] in QUERY_COMMANDS:
        return run_query(argv)
    if len(argv) > 1 and argv[1] == 'analyze':
        argv = [argv[0]] + argv[2:]
        if len(argv) == 1:
            print(__doc__)
            return 2

    opts = {'--lang': None, '--exclude': None, '--outdir': None}
    flags = []
    args = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in opts:
            if i + 1 >= len(argv) or argv[i + 1].startswith('--'):
                print('[FAIL] option needs a value: %s' % a)
                return 2
            opts[a] = argv[i + 1]
            i += 2
        elif a.startswith('-') and len(a) > 1:
            if a != '--quiet' and a != '-':
                print('[WARN] unknown option ignored: %s' % a)
            flags.append(a)
            i += 1
        else:
            args.append(a)
            i += 1

    if not args:
        print(__doc__)
        return 2
    repo = args[0]
    if not os.path.isdir(repo):
        print('[FAIL] not a directory: %s' % repo)
        return 2

    selected, lang_error = parse_lang(opts['--lang'])
    if lang_error is not None:
        print('[FAIL] %s' % lang_error)
        return 2

    excludes = []
    if opts['--exclude']:
        for token in opts['--exclude'].split(','):
            token = token.strip()
            if token:
                excludes.append(token)

    outdir = opts['--outdir'] or os.path.join(os.getcwd(), 'structure-facts')
    quiet = '--quiet' in flags

    root_abs = os.path.abspath(repo)
    out_abs = os.path.abspath(outdir)
    if out_abs == root_abs or out_abs.startswith(root_abs + os.sep):
        print('[WARN] outdir is inside the analyzed repo (may pollute its git status)')

    try:
        facts = build_facts(repo, selected_langs=selected, extra_excludes=excludes)
    except Exception as exc:                       # 内部错误：响亮失败，不静默降级
        print('[FAIL] internal error: %r' % (exc,))
        return 1
    try:
        json_path, md_path = write_artifacts(facts, outdir)
    except OSError as exc:
        print('[FAIL] cannot write artifacts: %s' % exc)
        return 1

    counts = facts['counts']
    if not quiet:
        print('[OK] repo=%s files=%d symbols=%d imports=%d calls=%d '
              '(verified=%d inferred=%d filtered=%d) entry_points=%d warnings=%d'
              % (facts['root_name'], counts['files'], counts['symbols'],
                 counts['imports'], counts['calls'], counts['calls_verified'],
                 counts['calls_inferred'], counts['filtered_calls'],
                 counts['entry_points'], len(facts['warnings'])))
        print('[OK] wrote %s' % json_path)
        print('[OK] wrote %s' % md_path)
        for kind, vdir, vsyms, vshare in vendored_hints(facts)[:3]:
            # P1-a / P2-c：疑似 vendored 目录只提示不自动排除（默认排除清单是
            # 冻结契约），把「跑完 map 才知道该 exclude 什么」的返工前置
            if kind == 'exclude':
                print('[WARN] suspected vendored directory %r (%d/%d symbols, '
                      '%.0f%%) — consider re-running analyze with --exclude %s'
                      % (vdir, vsyms, counts['symbols'], vshare, vdir))
            else:
                print('[WARN] top-level directory %r holds %d/%d symbols '
                      '(%.0f%%) — check whether it is vendored or project code'
                      % (vdir, vsyms, counts['symbols'], vshare))
    if counts['files'] == 0 or counts['files'] == counts['unsupported_files']:
        print('[WARN] zero supported source files (artifacts written anyway)')
        return 1
    return 0


# ---------------------------------------------------------------- 查询层（F8/F9，1c）
#
# 索引与性能（F11 / D-42）：进程内 json.load facts → 建 dict 索引（by qualname /
# by 末段名 / by caller / by callee），再按需做集合运算与 BFS。不引入任何嵌入式
# SQL 索引引擎（标准库里的也不引）——保住 facts 的文本可 diff / 可审计性与
# F10 kind 闭集的可审性；典型量级（10^4 符号 / 10^5 边 / 数 MB JSON）内存
# dict 完全够用；查询层纯只读，嵌入式数据库只会引入锁 / 并发 / 写盘失败等新失败面。
# 重估触发条件（提前不引入，触发时另开修订）：单次查询冷启动 > 3s（AC-49 软门）、
# 或 structure-facts.json > 50MB、或跨文件边数 > 10^6——届时再评估嵌入式索引或
# 侧车索引（spec F11/D-42，届时另开修订）。

QUERY_COMMANDS = ('map', 'callers', 'callees', 'impact', 'path', 'entry', 'search')
DEFAULT_FACTS_PATH = os.path.join('structure-facts', 'structure-facts.json')
SEARCH_DOMAINS = ('symbol', 'file', 'call', 'all')
CONF_RANK = {CONF_VERIFIED: 0, CONF_INFERRED: 1}
ENTRY_KEYS = ('kind', 'file', 'line', 'evidence', 'confidence')


def load_facts(path):
    """读 facts JSON（F9 只读口径）。返回 (facts|None, 错误消息|None)。

    三类响亮失败（CLI exit 1，不静默降级）：文件不存在 / JSON 非法 /
    schema_version 与本工具不匹配。查询层绝不写任何文件（AC-47）。
    """
    if not os.path.isfile(path):
        return None, 'facts file not found: %s' % path
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, 'cannot read facts (%s): %r' % (path, exc)
    if not isinstance(data, dict) or data.get('schema_version') != SCHEMA_VERSION:
        got = data.get('schema_version') if isinstance(data, dict) \
            else type(data).__name__
        return None, ('schema_version mismatch: expected %r, got %r'
                      % (SCHEMA_VERSION, got))
    return data, None


def build_query_index(facts):
    """F11 内存索引：by qualname / by 末段名（符号），by caller / by callee（调用边）。"""
    by_qual = {}
    by_last = {}
    for sym in facts['symbols']:
        by_qual.setdefault(sym['qualname'], []).append(sym)
        # P2-9：by_last 与调用边同口径（末段名）——Lua `function M.shout` 的
        # name 带限定前缀，若按 name 登记则 `callers shout` 命中不了
        by_last.setdefault(_lastseg(sym['qualname']), []).append(sym)
    by_caller = {}
    by_callee = {}
    for call in facts['calls']:
        if call.get('caller'):
            by_caller.setdefault(call['caller'], []).append(call)
        by_callee.setdefault(call['callee'], []).append(call)
    return {'by_qual': by_qual, 'by_last': by_last,
            'by_caller': by_caller, 'by_callee': by_callee}


def resolve_symbols(index, name, exact):
    """符号参数口径（F8）：先 qualname 精确，再末段名；--exact 只接受精确。"""
    hits = index['by_qual'].get(name, [])
    if not hits and not exact:
        hits = index['by_last'].get(name, [])
    return hits


def _lastseg(qualname):
    return qualname.split('.')[-1] if qualname else ''


def _node_id(path, depth, file_granular):
    """map 节点归组：--files 时为文件本身；否则目录按 depth 层截断，根级文件归 '.'。"""
    if file_granular:
        return path
    parts = path.split('/')[:-1]
    if not parts:
        return '.'
    return '/'.join(parts[:max(1, depth)])


def _anchor_names(index, name, exact):
    """impact / path 的 BFS 节点名集合（末段名空间，与调用边 callee 口径一致）。

    符号命中 → 各命中符号的末段名；符号零命中（如 facts 变体删掉了目标符号，
    AC-56）而该末段名仍出现在调用边名字空间时，继续作为图节点可用；否则为空。
    callers / callees / search 不用此回退——它们「列出事实」，符号不存在即
    found:false（AC-39）。
    """
    names = set(_lastseg(s['qualname']) for s in resolve_symbols(index, name, exact))
    if not names and not exact:
        seg = _lastseg(name)
        if seg in index['by_callee'] or any(
                k == seg or k.endswith('.' + seg) for k in index['by_caller']):
            names.add(seg)
    return names


def _call_graph(facts, include_inferred):
    """符号级调用图（末段名节点空间）。

    fwd[u][v] / rev[v][u] = 代表调用点 (file, line, confidence)；同一 (u, v) 的
    多条记录取 (file, line) 字典序最小者（确定性，F8 裁定 3）。缺省只收 verified
    边（D-41：推断边不进推理链）；--include-inferred 才纳，逐跳/逐层带 confidence。
    模块级调用点（caller 为空）不产生符号级边——callers/callees 列事实时仍列出。
    """
    fwd = {}
    rev = {}
    for call in facts['calls']:
        if call['confidence'] == CONF_INFERRED and not include_inferred:
            continue
        u = _lastseg(call.get('caller'))
        if not u:
            continue
        v = call['callee']
        rec = (call['file'], call['line'], call['confidence'])
        best = fwd.setdefault(u, {}).get(v)
        if best is None or rec[:2] < best[:2]:
            fwd[u][v] = rec
        best = rev.setdefault(v, {}).get(u)
        if best is None or rec[:2] < best[:2]:
            rev[v][u] = rec
    return fwd, rev


def _resolved_note(index, name, exact):
    """P2-b：同名多候选时回显「解析到谁」（写进 notes，不新增 schema 字段）。

    单候选/零候选返回 None（无歧义可言）；多候选时给出首个命中（按 file:line 排序，
    与图节点排序口径一致），避免读者以为 impact/path 命中的是唯一同名符号。
    """
    hits = resolve_symbols(index, name, exact)
    if len(hits) <= 1:
        return None
    first = sorted(hits, key=lambda s: (s['file'], s['start_line'],
                                        s['qualname']))[0]
    return ('%d symbols share the name %r; anchors resolve by tail name '
            '(first: %s at %s:%d)'
            % (len(hits), name, first['qualname'], first['file'],
               first['start_line']))


# ------------------------------------------------ B3 查询层输出契约（C-P0-2/P1-1/P1-2/P1-6/P1-7）
# 门禁先于实现（J7）：本节常量与函数是 spec F8/F9（v2.1 增补）的机器侧形态——
# 表头计数不变量、列表三级全序、去重键单点、截断就地报告、双通道分流。

# 带 --limit 的列表型子命令（截断探测只发生在它们身上；其余子命令无输出上限）
LIMIT_CMDS = ('callers', 'callees', 'search')
# C-P1-6：截断标记固定尾缀 = note 文本自带的「下一步动作」（用什么参数放宽）
TRUNC_SUFFIX = '（--limit 可放宽）'


def _list_sort_key(primary, file_path, line, tail_name):
    """C-P1-2 列表全序单点：语义主键 → file → line，末级以符号名字典序收底。

    callers 主键 = caller（谁调它）、callees/search-call 主键 = callee；
    impact 层内条目只有符号名（无 file:line），直接按末级（名字典序）排序。
    所有列表型输出共用本键，禁止各处自定义偏序。
    """
    return (primary, file_path, line, tail_name)


def _call_site_key(call):
    """C-P1-2 去重键单点（与 AC-27 facts 口径一致）：调用点身份 = (file, line, callee)。

    tuple 定义一次、处处引用；禁止 '>' / '|' 之类字符串拼接键
    （C-P2-5 反例：无定界拼接存在歧义包含，'a.b>c' 与 'a>b.c' 同形）。
    """
    return (call['file'], call['line'], call['callee'])


def _cap_note(prefix, shown, total):
    """C-P0-2/C-P1-6：截断标记——就地行与 notes[] 共用这同一条文本。

    notes 数组是截断/降级信息的唯一结构化通道；文本自带下一步动作
    （TRUNC_SUFFIX 指明用 --limit 放宽），禁止末尾一句通用「输出已截断」。
    """
    return '%s已截断：显示 %d / 共 %d%s' % (prefix, shown, total, TRUNC_SUFFIX)


def _is_trunc_note(note):
    """识别截断类 note（md 渲染据它做就地摆放，而不是末尾通用一句）。"""
    return note.endswith(TRUNC_SUFFIX)


Q_SHAPE_RESULT = 'result'
Q_SHAPE_NO_MATCH = 'no-match'


def classify_query_outcome(found):
    """C-P1-1：查询出口形状单点判定——「无结果不是错误」（F8 语义裁定 2）
    收敛在这一处；emit_human 与 emit_json 两个出口共调本函数，禁止各自
    内联 found→(形状, 退出码) 的映射（CodeGraph 两处 catch 各写一遍、
    worker 路径形状漂移的反面对照）。

      found=True  → ('result', 0)     正文 / JSON 外壳照常输出
      found=False → ('no-match', 0)   SUCCESS 形状：exit 0 + [OK] no matches（md）
                                      / found:false 外壳（json）——绝不译成错误

    exit 1/2（facts 读不到 / 用法错误）不经过本函数：它们在 _query_fail
    单点出口短路；同样禁止「失败→成功形状」的翻译（schema 不匹配必须响亮）。
    """
    return (Q_SHAPE_RESULT if found else Q_SHAPE_NO_MATCH), 0


def emit_human(lines, fmt):
    """C-P1-7 人类通道：md 形态走 stdout（既有人类契约不变）；--format json
    时整体让路到 stderr——json 模式的 stdout 只允许出现 JSON 文档，
    用结构而不是纪律保证分流（人类文本没有第二条路能漏进 stdout）。"""
    stream = sys.stderr if fmt == 'json' else sys.stdout
    for ln in lines:
        print(ln, file=stream)


def _query_fail(message, code, fmt=None):
    """C-P1-1/C-P1-7：exit 1/2 失败单点出口。人类文本默认 stdout（md 既有
    契约）；fmt=='json' 时走 stderr（stdout 纯净性）；返回码原样透传。"""
    emit_human(['[FAIL] %s' % message], fmt)
    return code


def emit_json(shell):
    """C-P1-7 机器通道：stdout 只写这一个 JSON 文档——json.loads 全量一次
    成功（机检口径）；notes 等结构化信息都在外壳里，不走人类通道。"""
    sys.stdout.write(json.dumps(shell, ensure_ascii=False, sort_keys=True,
                                indent=2))
    sys.stdout.write('\n')


def cmd_map(facts, depth, subdir, file_granular):
    """项目地图（AC-43）：目录/文件级节点 + 跨节点 import 边聚合。

    节点 files 之和 = facts.counts.files（--dir 时按子树）；边只聚合 target
    落在仓库内的 import（未解析/外部的 import 无目录端点，不构成跨目录边，
    数量记入 notes）；同节点内部依赖不计。verified/inferred/external 分列
    之和恒等于 count（本工具产物中 resolved ⟺ verified，分列是为兼容
    hand-built/variant facts）。
    """
    sym_count = {}
    for s in facts['symbols']:
        sym_count[s['file']] = sym_count.get(s['file'], 0) + 1

    def in_scope(path):
        return subdir is None or path == subdir or path.startswith(subdir + '/')

    nodes = {}
    for rec in facts['files']:                 # facts 已按 path 稳定排序
        path = rec['path']
        if not in_scope(path):
            continue
        nid = _node_id(path, depth, file_granular)
        node = nodes.get(nid)
        if node is None:
            node = nodes[nid] = {'id': nid, 'path': nid, 'files': 0,
                                 'symbols': 0, 'lines': 0}
        node['files'] += 1
        node['symbols'] += sym_count.get(path, 0)
        if rec.get('language'):
            # P1-h：未支持/二进制文件的「行数」是字节里的换行计数（图标、日志、
            # zip 各能贡献十万级），不进 lines 聚合——语义见 notes
            node['lines'] += rec.get('lines') or 0

    file_set = set(rec['path'] for rec in facts['files'])
    edges = {}
    unmapped = 0
    for imp in facts['imports']:
        tgt = imp.get('target')
        if imp.get('external') or tgt not in file_set:
            unmapped += 1
            continue
        if not in_scope(imp['file']):
            continue
        u = _node_id(imp['file'], depth, file_granular)
        v = _node_id(tgt, depth, file_granular)
        if u == v:
            continue
        edge = edges.setdefault((u, v), {'from': u, 'to': v, 'count': 0,
                                         'verified': 0, 'inferred': 0,
                                         'external': 0})
        edge['count'] += 1
        # 批次 7：原 :3124-3125 `if imp.get('external'): edge['external'] += 1`
        # 为死代码——上游 :3111 已把 external 边计入 unmapped 后 continue，
        # 此处 confidence 只可能是 verified/inferred 二选一。
        if imp.get('confidence') == CONF_VERIFIED:
            edge['verified'] += 1
        else:
            edge['inferred'] += 1
    node_list = [nodes[k] for k in sorted(nodes)]
    edge_list = [edges[k] for k in sorted(edges)]
    notes = []
    if unmapped:
        notes.append('%d import(s) without an in-repo target are not mapped'
                     % unmapped)
    unlang = sum(1 for rec in facts['files'] if not rec.get('language'))
    if unlang:
        notes.append('%d file(s) without a supported language are excluded from '
                     'line counts (binary/unparsed; their line count is '
                     'byte-derived, not code lines)' % unlang)
    gen_n = sum(1 for rec in facts['files'] if rec.get('generated'))
    if gen_n:
        # A-P0-1：生成文件只标注不排除（J4）——在 notes 里解释噪声来源
        notes.append('%d file(s) match generated-file signals (path convention '
                     'or header banner); annotated in files[].generated, '
                     'never excluded' % gen_n)
    for kind, vdir, vsyms, vshare in vendored_hints(facts)[:3]:
        if kind == 'exclude':
            notes.append('suspected vendored directory %r (%d/%d symbols, %.0f%%); '
                         'consider re-running analyze with --exclude %s'
                         % (vdir, vsyms, len(facts['symbols']), vshare, vdir))
        else:
            notes.append('top-level directory %r holds %d/%d symbols (%.0f%%); '
                         'check whether it is vendored or project code'
                         % (vdir, vsyms, len(facts['symbols']), vshare))
    return bool(node_list), 0, None, {'nodes': node_list, 'edges': edge_list}, \
        notes, len(node_list) + len(edge_list)


def cmd_callers(facts, index, name, exact, limit):
    """谁调用它（列出事实，D-41）：verified/inferred 都返回，逐条带 confidence。

    C-P0-2：先取全量再截断——total=截断前真实命中数，kept=最终保留条目
    （表头数字只许用 kept）；截断时 notes 写「已截断：显示 X / 共 Y」。
    C-P1-2：行按 _list_sort_key 三级全序；行身份去重键 _call_site_key 单点。
    """
    hits = resolve_symbols(index, name, exact)
    if not hits:
        return False, 0, name, [], ['no symbol matches: %s' % name], 0
    wanted = set(_lastseg(s['qualname']) for s in hits)
    rows = []
    seen = set()
    for call in facts['calls']:                # 已按 (file, line, callee) 稳定排序
        if call['callee'] not in wanted:
            continue
        key = _call_site_key(call)
        if key in seen:                        # 同一调用点只列一行（C-P1-2）
            continue
        seen.add(key)
        rows.append({'symbol': call['callee'], 'file': call['file'],
                     'line': call['line'], 'caller': call.get('caller') or '',
                     'confidence': call['confidence'],
                     'resolved_by': call.get('resolved_by'),
                     'ambiguous': bool(call.get('ambiguous'))})
    rows.sort(key=lambda r: _list_sort_key(r['caller'], r['file'], r['line'],
                                           r['symbol']))
    total = len(rows)
    kept = rows[:limit] if limit else rows
    notes = [_cap_note('', len(kept), total)] if total > len(kept) else []
    return bool(kept), len(hits), name, kept, notes, total


def cmd_callees(facts, index, name, exact, limit):
    """它调用谁（列出事实，D-41）：与 callers 互为逆关系（同一事实的两个方向）。

    C-P0-2/C-P1-2 口径与 cmd_callers 相同（全量→截断→三级全序→tuple 去重键）。
    """
    hits = resolve_symbols(index, name, exact)
    if not hits:
        return False, 0, name, [], ['no symbol matches: %s' % name], 0
    wanted = set(s['qualname'] for s in hits)
    rows = []
    seen = set()
    for call in facts['calls']:
        if call.get('caller') not in wanted:
            continue
        key = _call_site_key(call)
        if key in seen:
            continue
        seen.add(key)
        rows.append({'symbol': call.get('caller') or '', 'file': call['file'],
                     'line': call['line'], 'callee': call['callee'],
                     'confidence': call['confidence'],
                     'resolved_by': call.get('resolved_by')})
    rows.sort(key=lambda r: _list_sort_key(r['callee'], r['file'], r['line'],
                                           r['symbol']))
    total = len(rows)
    kept = rows[:limit] if limit else rows
    notes = [_cap_note('', len(kept), total)] if total > len(kept) else []
    return bool(kept), len(hits), name, kept, notes, total


def cmd_impact(facts, index, name, exact, depth, include_inferred):
    """影响半径（推理，D-41）：反向 BFS，缺省只走 verified 边，逐层给出符号集。

    --include-inferred 时每层附 confidences 映射（逐符号标注到达边的 confidence，
    多条边时取最优：verified 优先于 inferred）。levels 为空 → found:false。
    """
    matched = len(resolve_symbols(index, name, exact))
    anchors = _anchor_names(index, name, exact)
    if not anchors:
        return False, matched, name, {'levels': []}, \
            ['no symbol matches: %s' % name]
    _fwd, rev = _call_graph(facts, include_inferred)
    levels = []
    visited = set(anchors)
    frontier = sorted(visited)
    for d in range(1, max(1, depth) + 1):
        nxt = {}
        for node in frontier:
            for caller, rec in sorted(rev.get(node, {}).items()):
                if caller in visited:
                    continue
                if caller not in nxt or CONF_RANK[rec[2]] < CONF_RANK[nxt[caller]]:
                    nxt[caller] = rec[2]
        if not nxt:
            break
        level = {'depth': d, 'symbols': sorted(nxt)}
        if include_inferred:
            level['confidences'] = dict((k, nxt[k]) for k in sorted(nxt))
        levels.append(level)
        visited.update(nxt)
        frontier = sorted(nxt)
    notes = []
    if not levels:
        notes.append('no reachable callers')
    elif not include_inferred:
        notes.append('default follows verified edges only; '
                     'retry with --include-inferred to widen')
    rnote = _resolved_note(index, name, exact)
    if rnote:
        notes.insert(0, rnote)
    total = sum(len(l['symbols']) for l in levels)
    return bool(levels), matched, name, {'levels': levels}, notes, total


def cmd_path(facts, index, a, b, exact, include_inferred):
    """调用路径（推理，D-41 + F8 裁定 3）：BFS 确定性最短路径。

    邻居扩展按排序键 (file, line, callee) 字典序；缺省只走 verified 边。
    无路径 → found:false + hops:[] + note 明说「未找到实锤路径」——绝不返回
    空图冒充结果（AC-42）。
    """
    matched = len(resolve_symbols(index, a, exact)) \
        + len(resolve_symbols(index, b, exact))
    a_names = _anchor_names(index, a, exact)
    b_names = _anchor_names(index, b, exact)
    empty = {'from': a, 'to': b, 'hops': []}
    if not a_names or not b_names:
        missing = a if not a_names else b
        return False, matched, a, empty, \
            ['no symbol matches: %s' % missing], 0
    if a_names & b_names:
        return True, matched, a, empty, \
            ['source and target coincide (%s); zero hops'
             % ', '.join(sorted(a_names & b_names))], 0
    fwd, _rev = _call_graph(facts, include_inferred)
    parent = {}
    queue = []
    for nm in sorted(a_names):
        parent[nm] = None
        queue.append(nm)
    head = 0
    end = None
    while head < len(queue) and end is None:
        u = queue[head]
        head += 1
        edges = sorted(((rec[0], rec[1], v), v, rec)
                       for v, rec in fwd.get(u, {}).items())
        for _key, v, rec in edges:             # 排序键 = (file, line, callee)
            if v in parent:
                continue
            parent[v] = (u, rec)
            if v in b_names:
                end = v
                break
            queue.append(v)
    if end is None:
        note = '未找到实锤路径 (no verified call path); try --include-inferred' \
            if not include_inferred \
            else 'no call path even with inferred edges included'
        pnotes = [note]
        for who in (a, b):
            rn = _resolved_note(index, who, exact)
            if rn:
                pnotes.append(rn)
        return False, matched, a, empty, pnotes, 0
    hops = []
    node = end
    while parent[node] is not None:
        u, rec = parent[node]
        hops.append({'from': u, 'to': node, 'file': rec[0], 'line': rec[1],
                     'confidence': rec[2]})
        node = u
    hops.reverse()
    pnotes = []
    for who in (a, b):
        rn = _resolved_note(index, who, exact)
        if rn:
            pnotes.append(rn)
    return True, matched, a, {'from': a, 'to': b, 'hops': hops}, pnotes, \
        len(hops)


def cmd_entry(facts, kind):
    """入口点列表（AC-44）：与 facts.entry_points 同构，--kind 过滤为子集。"""
    rows = [dict(e) for e in facts['entry_points']
            if kind is None or e['kind'] == kind]
    notes = []
    if not rows:
        notes.append('no entry points%s'
                     % ('' if kind is None else ' for kind %s' % kind))
    return bool(rows), 0, None, rows, notes, len(rows)


def cmd_search(facts, keyword, domain, limit):
    """关键字检索（AC-45）：大小写不敏感，--in 三域过滤，条目全部来自 facts。

    C-P0-2：各域先取全量再截断——表头（matched 与三域计数）只报保留数，
    截断域在触发点就地写「<域> 已截断：显示 X / 共 Y（--limit 可放宽）」，
    同一条文本进 notes（唯一结构化通道）。
    C-P1-2：files/calls 域按全序键排序（symbols 已按 (file, start_line)）。
    """
    kw = keyword.lower()
    full = {'symbols': [], 'files': [], 'calls': []}
    if domain in ('symbol', 'all'):
        full['symbols'] = sorted(
            (dict(s) for s in facts['symbols'] if kw in s['qualname'].lower()),
            key=lambda s: (s['file'], s['start_line']))
    if domain in ('file', 'all'):
        full['files'] = sorted(
            (dict(r) for r in facts['files'] if kw in r['path'].lower()),
            key=lambda r: r['path'])
    if domain in ('call', 'all'):
        full['calls'] = sorted(
            (dict(c) for c in facts['calls'] if kw in c['callee'].lower()),
            key=lambda c: _list_sort_key(c['callee'], c['file'], c['line'],
                                         c['callee']))
    results = {}
    notes = []
    for key in ('symbols', 'files', 'calls'):
        rows = full[key]
        results[key] = rows[:limit] if limit else rows
        if limit and len(rows) > limit:        # C-P1-6：截断在触发点报告
            notes.append(_cap_note('%s ' % key, limit, len(rows)))
    found = bool(results['symbols'] or results['files'] or results['calls'])
    if not found:
        notes = ['no matches for %r in domain %s' % (keyword, domain)]
    total = sum(len(full[k]) for k in full)
    matched = len(results['symbols'])          # 表头口径：保留数（不变量）
    return found, matched, keyword, results, notes, total


def render_query_md(shell):
    """--format md（F9）：人读形态，file:line + 实锤/推断标记（口径同 F3）。

    行排布与 universal-ctags `-x` 交叉引用行同构（符号 + file:line + 标记），
    仅借鉴输出形态，不引任何依赖。

    B3 表头计数不变量（C-P0-2）：表头数字 = 最终保留在输出里的条目数；
    截断标记（C-P1-6）在触发它的那个列表旁就地渲染（文本取自 notes，
    不在末尾另写一句通用「已截断」）。
    """
    cmd = shell['query']
    res = shell['results']
    notes = shell['notes']
    trunc = [n for n in notes if _is_trunc_note(n)]
    out = []
    add = out.append
    if cmd == 'search':
        # P2-a：表头口径与列出条目一致（原先只报 symbols 数，calls/files 不计数）
        add('matched: %d symbols, %d calls, %d files'
            % (shell['matched'], len(res['calls']), len(res['files'])))
    elif shell['matched'] > 1:
        add('matched: %d symbols' % shell['matched'])
    if cmd == 'map':
        for n in res['nodes']:
            add('- %s  files=%d symbols=%d lines=%d'
                % (_md_cell(n['id']), n['files'], n['symbols'], n['lines']))
        for e in res['edges']:
            add('- %s -> %s  count=%d (verified=%d inferred=%d external=%d)'
                % (_md_cell(e['from']), _md_cell(e['to']), e['count'],
                   e['verified'], e['inferred'], e['external']))
    elif cmd == 'callers':
        add('listed: %d call site(s)' % len(res))
        for r in res:
            add('- %s  %s:%d  (%s)  called by %s%s'
                % (_md_cell(r['symbol']), _md_cell(r['file']), r['line'],
                   _conf_label(r['confidence'], r.get('resolved_by')),
                   _md_cell(r['caller'] or '(module)'),
                   '  [ambiguous]' if r['ambiguous'] else ''))
        for n in trunc:                        # C-P1-6：就地，紧跟被截的列表
            add(n)
    elif cmd == 'callees':
        add('listed: %d call site(s)' % len(res))
        for r in res:
            add('- %s  %s:%d  (%s)  calls %s'
                % (_md_cell(r['symbol']), _md_cell(r['file']), r['line'],
                   _conf_label(r['confidence'], r.get('resolved_by')),
                   _md_cell(r['callee'])))
        for n in trunc:
            add(n)
    elif cmd == 'impact':
        # 表头 = 最终保留条目数（本命令无输出上限，total == 保留数）
        add('radius: %d symbol(s) in %d level(s)'
            % (sum(len(l['symbols']) for l in res['levels']),
               len(res['levels'])))
        for lvl in res['levels']:
            if 'confidences' in lvl:
                names = ', '.join('%s(%s)' % (_md_cell(s),
                                              _conf_label(lvl['confidences'][s]))
                                  for s in lvl['symbols'])
            else:
                names = ', '.join(_md_cell(s) for s in lvl['symbols'])
            add('- depth %d: %s' % (lvl['depth'], names or '(none)'))
    elif cmd == 'path':
        if res['hops']:
            add('- route: %s' % ' -> '.join(
                [_md_cell(res['hops'][0]['from'])]
                + [_md_cell(h['to']) for h in res['hops']]))
        for h in res['hops']:
            add('  - %s -> %s  %s:%d  (%s)'
                % (_md_cell(h['from']), _md_cell(h['to']), _md_cell(h['file']),
                   h['line'], _conf_label(h['confidence'])))
    elif cmd == 'entry':
        for r in res:
            add('- %s  %s:%d  (%s)  evidence: %s'
                % (_md_cell(r['kind']), _md_cell(r['file']), r['line'],
                   _conf_label(r['confidence']), _md_cell(r['evidence'])))
    elif cmd == 'search':
        for key in ('symbols', 'files', 'calls'):
            mark = next((n for n in trunc if n.startswith('%s ' % key)), None)
            if key == 'symbols':
                for s in res['symbols']:
                    add('- symbol  %s  %s:%d  %s'
                        % (_md_cell(s['qualname']), _md_cell(s['file']),
                           s['start_line'], _md_cell(s['kind'])))
            elif key == 'files':
                for r in res['files']:
                    add('- file  %s  (%s, %s lines)'
                        % (_md_cell(r['path']), _md_cell(r['language'] or 'unknown'),
                           r.get('lines')))
            else:
                for c in res['calls']:
                    add('- call  %s  %s:%d  (%s)'
                        % (_md_cell(c['callee']), _md_cell(c['file']), c['line'],
                           _conf_label(c['confidence'], c.get('resolved_by'))))
            if mark:                           # C-P1-6：截哪个域，标在哪个域旁
                add(mark)
    for note in notes:
        if _is_trunc_note(note):
            continue                           # 已就地渲染，不再末尾重复
        add('[NOTE] %s' % note)
    return '\n'.join(out)


def _query_usage_error(message):
    """用法错误（exit 2）。fmt 未解析阶段经此（人类文本走 stdout，行为不变）；
    fmt 已知后的用法错误直接调 _query_fail(msg, 2, fmt)。"""
    return _query_fail(message, 2)


def run_query(argv):
    """查询层入口（F8）：argv = [prog, <cmd>, ...]，返回退出码 0/1/2。

    0 = 查询完成（含无结果，found:false）；1 = facts 读不到 / JSON 非法 /
    schema_version 不匹配（响亮失败，不静默降级）；2 = 用法错误（缺 <symbol>、
    --depth 非整数、--in/--kind/--format 值非法、缺省路径无产物且未给 --facts 等）。
    只读纪律：除 stdout 外不触任何文件（AC-47）。
    """
    cmd = argv[1]
    val_opts = {'--facts': None, '--dir': None, '--depth': None,
                '--in': None, '--kind': None, '--limit': None,
                '--format': None}
    flag_opts = ('--exact', '--files', '--include-inferred', '--quiet')
    flags = []
    pos = []
    i = 2
    while i < len(argv):
        a = argv[i]
        if a in val_opts:
            if i + 1 >= len(argv):
                _query_usage_error('option needs a value: %s' % a)
                return 2
            val_opts[a] = argv[i + 1]
            i += 2
        elif a.startswith('-') and len(a) > 1:
            if a not in flag_opts:
                _query_usage_error('unknown option: %s' % a)
                return 2
            flags.append(a)
            i += 1
        else:
            pos.append(a)
            i += 1

    fmt = val_opts['--format'] or 'md'
    if fmt not in ('md', 'json'):
        # fmt 本身非法：不能按它分流，人类文本走 stdout（与旧行为一致）
        _query_usage_error('--format must be md or json: %s' % fmt)
        return 2
    depth = None
    if val_opts['--depth'] is not None:
        try:
            depth = int(val_opts['--depth'])
        except ValueError:
            return _query_fail('--depth needs an integer: %s'
                               % val_opts['--depth'], 2, fmt)
        if depth < 1:
            return _query_fail('--depth must be >= 1', 2, fmt)
    limit = 200
    if val_opts['--limit'] is not None:
        try:
            limit = int(val_opts['--limit'])
        except ValueError:
            return _query_fail('--limit needs an integer: %s'
                               % val_opts['--limit'], 2, fmt)
        if limit < 0:
            return _query_fail('--limit must be >= 0', 2, fmt)
    domain = val_opts['--in'] or 'all'
    if domain not in SEARCH_DOMAINS:
        return _query_fail('--in must be one of %s: %s'
                           % ('|'.join(SEARCH_DOMAINS), domain), 2, fmt)
    kind = val_opts['--kind']
    if kind is not None and kind not in ENTRY_KINDS:
        return _query_fail('--kind must be one of the frozen entry kinds: %s'
                           % kind, 2, fmt)
    if depth is not None and cmd not in ('map', 'impact'):
        return _query_fail('--depth applies to map/impact only', 2, fmt)

    need = {'map': 0, 'entry': 0, 'search': 1, 'callers': 1, 'callees': 1,
            'impact': 1, 'path': 2}[cmd]
    if len(pos) < need:
        return _query_fail('%s expects %d positional argument(s), got %d'
                           % (cmd, need, len(pos)), 2, fmt)
    if len(pos) > need:
        return _query_fail('%s takes at most %d positional argument(s)'
                           % (cmd, need), 2, fmt)
    if cmd == 'map' and depth is None:
        depth = 1
    if cmd == 'impact' and depth is None:
        depth = 2

    subdir = None
    if val_opts['--dir'] is not None:
        subdir = val_opts['--dir'].strip().replace('\\', '/').strip('/') or None

    facts_path = val_opts['--facts']
    if facts_path is None:
        facts_path = os.path.join(os.getcwd(), DEFAULT_FACTS_PATH)
        if not os.path.isfile(facts_path):
            return _query_fail(
                'no facts at default path (run analyze first or pass --facts):'
                ' %s' % facts_path, 2, fmt)
    facts, err = load_facts(facts_path)
    if err is not None:
        return _query_fail(err, 1, fmt)

    index = build_query_index(facts)
    exact = '--exact' in flags
    include_inferred = '--include-inferred' in flags
    if cmd == 'map':
        found, matched, sym_field, results, notes, total = cmd_map(
            facts, depth, subdir, '--files' in flags)
    elif cmd == 'callers':
        found, matched, sym_field, results, notes, total = cmd_callers(
            facts, index, pos[0], exact, limit)
    elif cmd == 'callees':
        found, matched, sym_field, results, notes, total = cmd_callees(
            facts, index, pos[0], exact, limit)
    elif cmd == 'impact':
        found, matched, sym_field, results, notes, total = cmd_impact(
            facts, index, pos[0], exact, depth, include_inferred)
    elif cmd == 'path':
        found, matched, sym_field, results, notes, total = cmd_path(
            facts, index, pos[0], pos[1], exact, include_inferred)
    elif cmd == 'entry':
        found, matched, sym_field, results, notes, total = cmd_entry(facts, kind)
    else:
        found, matched, sym_field, results, notes, total = cmd_search(
            facts, pos[0], domain, limit)

    # C-P0-2：json 外壳加 truncated/total/limit 三字段——total=截断前真实总数
    # （真数，不受 limit 影响）、limit=生效上限（0=无上限）、truncated=是否截断。
    if cmd in LIMIT_CMDS:
        if cmd == 'search':
            kept_n = sum(len(results[k])
                         for k in ('symbols', 'files', 'calls'))
        else:
            kept_n = len(results)
    else:
        kept_n = total                         # 无输出上限：保留数 == 总数
    shell = {'query': cmd, 'symbol': sym_field, 'matched': matched,
             'found': found, 'results': results, 'notes': notes,
             'total': total,
             'limit': limit if cmd in LIMIT_CMDS else 0,
             'truncated': total > kept_n}
    # C-P1-1：两个出口共调同一形状判定（无结果不是错误，收敛一处）
    shape, code = classify_query_outcome(found)
    if fmt == 'json':
        emit_json(shell)                       # stdout 只有这一个 JSON 文档
        return code
    quiet = '--quiet' in flags
    if shape == Q_SHAPE_NO_MATCH:
        if not quiet:
            emit_human(['[OK] no matches']
                       + ['[NOTE] %s' % n for n in notes], fmt)
        return code
    text = render_query_md(shell)
    if text:
        emit_human(text.split('\n'), fmt)
    return code


def run_selftest():
    """--selftest 兼容转发入口（DEV-01 拆分落地）。

    自测实现已整体迁至 tests/test_analyze_structure.py（以 import 方式加载
    主模块后执行全部断言）。此处定位相对本目录的 tests/ 子目录：存在则
    subprocess.run 以同一解释器执行并透传退出码与输出；缺失则提示检查
    技能包完整性并退出 2。"""
    test_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'tests', 'test_analyze_structure.py')
    if not os.path.isfile(test_path):
        print('[FAIL] 测试文件缺失，请检查技能包完整性: %s' % test_path)
        return 2
    return subprocess.run([sys.executable, test_path]).returncode


if __name__ == '__main__':
    sys.exit(main(sys.argv))
