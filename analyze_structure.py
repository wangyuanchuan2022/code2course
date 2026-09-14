#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_structure.py — code2course 结构事实底稿生成器（零依赖，Python 3.8+ 纯标准库）

用法：
    python analyze_structure.py <repo> [--lang auto|<id>[,<id>...]]
                                [--exclude A,B,...] [--outdir DIR] [--quiet]
    python analyze_structure.py --selftest

产物（写入 <outdir>，缺省 <cwd>/structure-facts）：
    structure-facts.json — 机器可读五件套（schema_version=2，顶层键恰好 11 个）
    structure-facts.md   — 人读底稿（固定小节：文件清单 / 符号表 / 依赖边（import）/
                           调用边 / 断点清单（Where the graph stops）/ 入口点 /
                           解析失败与警告 / 诚实性声明）

说明：
  * 五件套 = 文件清单 / 符号表 / import 边 / 调用边 / 入口点。
  * 语言面：16 门 Tier-1 全部接入（F5）。python 走 ast 模块确定性提取（extractor: ast）；
    其余 15 门走表驱动启发式引擎（brace = 大括号系 / end = end 块系，extractor 如实标注），
    每门语言一张模式表（LANG_TABLES），token 正则借鉴 Pygments 2.21.0 lexer（见文末出处注记）。
    已知盲区见产物 MD 末尾的诚实性声明与 F5 各语言盲区列。
  * 边诚实性：调用边的 callee 末段名命中符号表 → verified（实锤，带调用处行号）；
    否则 inferred（推断）；同名多候选 → verified + ambiguous: true（不静默当唯一实锤）；
    内建/全局名只计入 filtered_calls，不逐条列出；(file, line, callee) 去重。
  * 默认排除清单按目录 basename 匹配（任意层级、大小写不敏感）；--exclude 为追加而非
    替换；排除在目录遍历阶段生效（被排除目录的探针在 files/symbols/imports/calls
    四处零出现）。
  * 被分析仓库零写入；产物确定性：同一仓库同一输入连跑两次字节一致（无时间戳、
    无绝对路径、所有列表按稳定键排序）。
  * 查询层子命令（map / callers / callees / impact / path / entry / search）由步骤 1c 接入。

退出码：0 成功产出（可含 warning）/ 1 产出不完整或内部错误 / 2 用法错误或路径不可读。

重估触发线（留档，供后续修订判断）：自测断言 > 150 条，或需要跨文件共享 fixture 时，
拆分独立测试目录（DEV-01）；facts JSON > 50MB，或进程内单次查询冷启动 > 3s，或跨文件
边数 > 10^6 时，重新评估索引形态（F11）。

Language token patterns adapted from Pygments 2.21.0 (BSD-2-Clause) lexers — https://pygments.org/docs/lexers/
"""
import ast
import builtins
import json
import os
import re
import sys
import tempfile

SCHEMA_VERSION = 2
TOOL_NAME = 'analyze_structure.py'
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
        'symlink-skipped'),
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
    'entry_points.kind': 8, 'warnings.kind': 8, 'language': 16,
    'counts.keys': 11,
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
    W_UNSUPPORTED, W_SYMLINK = WARNING_KINDS

LANG_IDS = CLOSED_SETS['language']
COUNT_KEYS = CLOSED_SETS['counts.keys']

CONF_VERIFIED = 'verified'
CONF_INFERRED = 'inferred'
CONFIDENCES = (CONF_VERIFIED, CONF_INFERRED)      # J3：二值枚举

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
            (r'\b(?P<recv>\w+)::(?P<n>\w+)\s*\([^;{}]*\)\s*\{', K_METHOD, 'func'),
            (r'\b(?:[\w\*]+\s+)+\**(?P<n>\w+)\s*\([^;{}]*\)\s*\{', K_FUNCTION, 'func'),
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
            (r'\b(?:const|static\s+readonly)\s+[\w<>\[\],\s\?]*?\b(?P<n>\w+)\s*=[^=]', K_CONSTANT, 'value'),
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
            (r'\b(?:final|const)\s+[\w<>\[\],\s\?]*?\b(?P<n>\w+)\s*=[^=]', K_CONSTANT, 'value'),
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
        'open_kw': ('function', 'if', 'for', 'while', 'do', 'repeat'),
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
METADATA_BASENAMES = frozenset((
    'package.json', 'pyproject.toml', 'setup.py', 'setup.cfg',
    'Cargo.toml', 'pom.xml', 'composer.json', 'go.mod',
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

HONESTY_BLOCK = '''> 本底稿由 analyze_structure.py 自动生成。Python 部分来自 ast 模块的确定性提取（extractor: ast）；
> 其余语言来自表驱动启发式引擎（extractor: brace = 大括号系 / end = end 块系），均为启发式而非事实。
> 已知盲区举例：C/C++ 宏定义函数与函数指针调用、Java/C# 注解处理器与 Lambda 体、Go 接口隐式实现、
> Rust 宏与 trait 默认方法、Ruby define_method 与单行修饰形式、Lua 表方法的两种调用形态、
> JS/TS 对象字面量方法与装饰器。以上均不保证被识别。
> 每条 import 边与调用边都标注了「实锤」（可在源码定位出处）或「推断」（未能对上本仓库符号表）；
> 入口点中的命名启发式、manifest 声明与 listen( 调用均属启发式而非事实。
> 底稿与源码冲突时，以源码为准。'''


# ---------------------------------------------------------------- 通用小工具
def _rel_posix(root, path):
    """绝对/相对路径 → 相对 root 的 POSIX 路径（J2：无盘符、无反斜杠、无前导 ./）。"""
    return os.path.relpath(path, root).replace(os.sep, '/')


def _line_at(src_lines, lineno):
    """声明行原文（trim、≤200 字符；行号越界返回空串）。"""
    if 1 <= lineno <= len(src_lines):
        return src_lines[lineno - 1].strip()[:SIGNATURE_MAX]
    return ''


def _warn(rel, kind, message):
    return {'file': rel, 'kind': kind, 'message': message}


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
            out.append(_rel_posix(root, os.path.join(dirpath, fn)))
    return out


def read_source(root, rel, lang, files, warnings):
    """读入源文件 → (file_record, data|None, text|None)；读取失败落 read-error。"""
    full = os.path.join(root, *rel.split('/'))
    rec = {'path': rel, 'lines': 0, 'language': lang, 'parse_error': None}
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
        text = data.decode('utf-8')
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
        with open(full, 'rb') as fh:
            data = fh.read()
    except OSError as exc:
        warnings.append(_warn(rel, W_MANIFEST, 'cannot read manifest: %s' % exc))
        return []
    try:
        text = data.decode('utf-8')
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
    elif base == 'Cargo.toml':
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
    """收集子树中的调用点 → (line, caller, callee, receiver)。"""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute):
                out.append((child.lineno, caller, func.attr, dotted_text(func.value)))
            elif isinstance(func, ast.Name):
                out.append((child.lineno, caller, func.id, None))
            collect_calls(child, caller, out)
        else:
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


def analyze_python(root, rel, data, text, symbols, imports, entry_points, warnings):
    """Python 文件 → (调用点原始表, 解析错误消息|None)。"""
    src_lines = text.splitlines()
    try:
        tree = ast.parse(data, filename=rel)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return [], '%s: %s' % (type(exc).__name__, exc)
    calls_raw = []
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
    return calls_raw, None


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
                hit = True
                break
        if hit:
            continue
        if '0' <= ch <= '9':
            m_num = re.match(r'[0-9][0-9a-zA-Z_.]*', text[i:])
            i += m_num.end() if m_num else 1    # 数字字面量：匹配即跳过（仅 ASCII 数字）
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


def brace_end_pos(stripped, body_pos):
    """从块体 '{' 起配对计数；不平衡返回 None（禁止回退 start_line——R3）。"""
    depth = 0
    for k in range(body_pos, len(stripped)):
        c = stripped[k]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return k
    return None


_WORD_RE = re.compile(r'\w+')


def end_block_end_pos(stripped, table, scan_from):
    """end 引擎：按 open/close 关键字计深（Ruby 单行修饰形式不开块——AC-54）。
    返回关闭关键字词首位置，不平衡返回 None。"""
    open_any = set(table['open_kw'])
    open_ls = set(table['open_kw_line_start'])
    close_kw = set(table['close_kw'])
    depth = 1                                    # 声明本身已开启一块
    for m in _WORD_RE.finditer(stripped, scan_from):
        w = m.group(0)
        if w in close_kw:
            depth -= 1
            if depth == 0:
                return m.start()
        elif w in open_any:
            depth += 1
        elif w in open_ls:
            k = m.start() - 1
            while k >= 0 and stripped[k] in ' \t':
                k -= 1
            if k < 0 or stripped[k] == '\n':     # 仅逻辑行首的关键字开启新块
                depth += 1
    return None


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
            for base in (tuple(d), ()):
                cand = base + tuple(spec.split('/'))
                for ext in _JS_EXTS:
                    if _fs_exists(root, cand, ext):
                        return _rel_posix(root, os.path.join(root, *cand)) + ext, True, False, False
                    if _fs_exists(root, cand + ('index',), ext):
                        return _rel_posix(root, os.path.join(root, *(cand + ('index',)))) + ext, True, False, False
        return None, False, True, False        # bare specifier → inferred + external
    if resolver == 'js_dynamic':
        return None, False, True, True         # 动态形态 → inferred + dynamic
    if resolver == 'c_quote':
        d = rel.split('/')[:-1]
        for base in (tuple(d), ()):
            if _fs_exists(root, base + (spec,), ''):
                return _rel_posix(root, os.path.join(root, *(base + (spec,)))), True, False, False
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
        if _fs_exists(root, (spec,), '.go'):
            return spec + '.go', True, False, False
        if os.path.isdir(os.path.join(root, *spec.split('/'))):
            return spec + '/', True, False, False
        return None, False, True, False        # 模块路径非仓库相对 → inferred + external
    if resolver == 'rust':
        if spec.startswith(('crate::', 'self::', 'super::')):
            head, _, rest = spec.partition('::')
            parts = tuple(rest.split('::')) if rest else ()
            for base in (('src',), ()):
                for i in range(len(parts), 0, -1):
                    if _fs_exists(root, base + parts[:i], '.rs'):
                        return _rel_posix(root, os.path.join(root, *(base + parts[:i]))) + '.rs', True, False, False
                    if _fs_exists(root, base + parts[:i] + ('mod',), '.rs'):
                        return _rel_posix(root, os.path.join(root, *(base + parts[:i] + ('mod',)))) + '.rs', True, False, False
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
            if _fs_exists(root, cand, ''):
                return _rel_posix(root, os.path.join(root, *cand)), True, False, False
        return None, False, True, False
    if resolver == 'ruby_rel':
        d = rel.split('/')[:-1]
        cand = tuple(d) + tuple(spec.split('/'))
        if _fs_exists(root, cand, '.rb'):
            return _rel_posix(root, os.path.join(root, *cand)) + '.rb', True, False, False
        return None, False, False, False
    if resolver == 'ruby':
        d = rel.split('/')[:-1]
        while True:
            if _fs_exists(root, d + (spec,), '.rb'):
                return _rel_posix(root, os.path.join(root, *(d + (spec,)))) + '.rb', True, False, False
            if not d:
                break
            d = d[:-1]
        return None, False, True, False
    if resolver == 'lua':
        modpath = spec.replace('.', '/')
        d = rel.split('/')[:-1]
        for base in (tuple(d), ()):
            if _fs_exists(root, base + (modpath,), '.lua'):
                return _rel_posix(root, os.path.join(root, *(base + (modpath,)))) + '.lua', True, False, False
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
    """brace/end 双引擎（表驱动）：返回 (调用点原始表, 停用表滤掉的调用数)。"""
    table = compile_table(lang)
    extractor = lang_extractor(lang)
    stripped = strip_source(text, table, 'all')
    comments_only = strip_source(text, table, 'comments')
    offsets = _line_offsets(text)
    total_lines = len(text.splitlines())

    def pos_line(pos):
        return min(_pos_line(offsets, pos), total_lines)

    def line_of(line_no):
        return _line_at(text.splitlines(), line_no)

    # ---- 1) 声明扫描（默认在完全剥离文本上；decl_on_comments 语言用仅剥注释文本）----
    found = []
    decl_spans = []
    decls_compiled, imports_compiled = table['_compiled']
    decl_text = comments_only if table.get('decl_on_comments') else stripped
    for rx, kind, role in decls_compiled:
        for m in rx.finditer(decl_text):
            decl_spans.append((m.start(), m.end()))
            name = m.groupdict().get('n')
            if not name:
                continue
            if name in table['decl_stops']:
                continue
            if name.startswith('~') or name.startswith('operator'):
                continue                       # 析构/运算符重载：盲区不猜
            found.append((m.start(), m.end(), name,
                          m.groupdict().get('recv'), kind, role))
    found.sort(key=lambda item: (item[0], -item[1]))

    # ---- 2) 逐声明解析块体 + 作用域栈 → 符号 ----
    scopes = []            # [end_pos, qualname, is_type]
    spans = []             # (start, end, qualname) 供 caller 归属
    unbalanced = False
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
            close_pos = brace_end_pos(stripped, body_pos) if body_pos is not None else None

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
    # 声明自身（def f( / func f( / function f(）不是调用点：落在声明匹配区间内的命中剔除
    hits = [h for h in hits
            if not any(d_start <= h[0] < d_end for d_start, d_end in decl_spans)]
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
    return ordered_calls, filtered


# ---------------------------------------------------------------- 五件套组装
def build_facts(repo, selected_langs=None, extra_excludes=None):
    """扫描仓库 → facts 字典（J1/J2/J7：顶层 11 键、POSIX 相对路径、稳定排序）。"""
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
    call_units = []                      # (rel, [(line, caller, callee, receiver)])
    filtered_calls = 0

    for rel in scan_tree(root, excludes, warnings):
        base = os.path.basename(rel)
        ext = os.path.splitext(base)[1].lower()
        if base in METADATA_BASENAMES:
            entry_points.extend(manifest_entries(root, rel, base, warnings))
            continue
        lang = EXT_TO_LANG.get(ext)
        if lang is None:
            rec, _data, _text = read_source(root, rel, None, files, warnings)
            warnings.append(_warn(rel, W_UNSUPPORTED,
                                  'unsupported file extension: %s' % (ext or '(none)')))
            continue
        rec, data, text = read_source(root, rel, lang, files, warnings)
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
            unit, parse_error = analyze_python(root, rel, data, text, symbols,
                                               imports, entry_points, warnings)
            if parse_error is not None:
                rec['parse_error'] = parse_error
                warnings.append(_warn(rel, W_PARSE, parse_error))
            else:
                call_units.append((rel, unit))
        else:                          # brace / end 双引擎（表驱动，1b）
            unit, extra_filtered = analyze_generic(
                root, rel, lang, data, text, symbols, imports,
                entry_points, warnings)
            filtered_calls += extra_filtered
            if unit:
                call_units.append((rel, unit))

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

    last_segment = {}
    for sym in symbols:                  # 命中判定：callee 与符号末段名相等（全库口径）
        key = sym['qualname'].split('.')[-1]
        last_segment[key] = last_segment.get(key, 0) + 1

    for rel, raw_calls in call_units:
        seen = set()
        for line, caller, callee, receiver in raw_calls:
            if callee in BUILTIN_NAMES:
                filtered_calls += 1      # 内建/全局名只计数、不逐条列出
                continue
            key = (rel, line, callee)
            if key in seen:              # (file, line, callee) 去重
                continue
            seen.add(key)
            candidates = last_segment.get(callee, 0)
            calls.append({
                'file': rel, 'line': line, 'caller': caller, 'callee': callee,
                'receiver': receiver,
                'confidence': CONF_VERIFIED if candidates else CONF_INFERRED,
                'candidates': candidates,
                'ambiguous': candidates > 1,
                'extractor': EXT_AST,
            })

    files.sort(key=lambda r: r['path'])
    symbols.sort(key=lambda s: (s['file'], s['start_line'], s['qualname']))
    imports.sort(key=lambda i: (i['file'], i['line'], i['target']))
    calls.sort(key=lambda c: (c['file'], c['line'], c['callee']))
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
def _conf_label(confidence):
    return '实锤' if confidence == CONF_VERIFIED else '推断'


def render_md(facts):
    """MD 底稿：小节标题字面固定（M3），不嵌源码正文（M1），不截断（M2）。"""
    counts = facts['counts']
    out = []
    add = out.append
    add('# 结构事实底稿 · %s' % facts['root_name'])
    add('')
    add('- 工具：%s（schema_version %d）' % (facts['tool'], facts['schema_version']))
    add('- 语言：%s' % (', '.join(facts['languages']) if facts['languages'] else '（无）'))
    add('- 计数摘要：files=%d symbols=%d imports=%d calls=%d（实锤 %d / 推断 %d）'
        'entry_points=%d warnings=%d'
        % (counts['files'], counts['symbols'], counts['imports'], counts['calls'],
           counts['calls_verified'], counts['calls_inferred'], counts['entry_points'],
           len(facts['warnings'])))
    add('')

    add('## 文件清单')
    add('')
    add('| 路径 | 行数 | 语言 |')
    add('|---|---|---|')
    for rec in facts['files']:
        add('| %s | %d | %s |' % (rec['path'], rec['lines'], rec['language'] or '-'))
    if not facts['files']:
        add('| （无） | 0 | - |')
    add('')

    add('## 符号表')
    add('')
    add('| qualname | kind | 位置 | extractor |')
    add('|---|---|---|---|')
    for sym in facts['symbols']:
        end = sym['end_line'] if sym['end_line'] is not None else '?'
        add('| %s | %s | %s:%s-%s | %s |'
            % (sym['qualname'], sym['kind'], sym['file'], sym['start_line'], end,
               sym['extractor']))
        if sym['signature']:
            add('    %s' % sym['signature'])
    if not facts['symbols']:
        add('| （无） | - | - | - |')
    add('')

    add('## 依赖边（import）')
    add('')
    add('| 位置 | 目标 | 置信 | kind | external |')
    add('|---|---|---|---|---|')
    for imp in facts['imports']:
        add('| %s:%d | %s | %s | %s | %s |'
            % (imp['file'], imp['line'], imp['target'], _conf_label(imp['confidence']),
               imp['kind'], 'yes' if imp['external'] else 'no'))
    if not facts['imports']:
        add('| （无） | - | - | - | - |')
    add('')

    add('## 调用边')
    add('')
    add('| 位置 | callee | caller | receiver | 置信 | 候选 |')
    add('|---|---|---|---|---|---|')
    for call in facts['calls']:
        add('| %s:%d | %s | %s | %s | %s | %d |'
            % (call['file'], call['line'], call['callee'], call['caller'] or '-',
               call['receiver'] or '-', _conf_label(call['confidence']),
               call['candidates']))
    if not facts['calls']:
        add('| （无） | - | - | - | - | 0 |')
    add('')

    add('## 断点清单（Where the graph stops）')
    add('')
    inferred = [c for c in facts['calls'] if c['confidence'] == CONF_INFERRED]
    if not inferred:
        add('（无推断调用边：所有调用点都能对上本仓库符号表）')
    else:
        by_file = {}
        for call in inferred:
            by_file.setdefault(call['file'], []).append(call)
        for path in sorted(by_file):
            add('### %s' % path)
            add('')
            for call in sorted(by_file[path], key=lambda c: (c['line'], c['callee'])):
                add('- 行 %d 调用 `%s` — 断因：未在本仓库符号表中找到同名符号'
                    % (call['line'], call['callee']))
            add('')

    add('## 入口点')
    add('')
    add('| kind | 位置 | evidence | 置信 |')
    add('|---|---|---|---|')
    for entry in facts['entry_points']:
        add('| %s | %s:%d | %s | %s |'
            % (entry['kind'], entry['file'], entry['line'], entry['evidence'],
               _conf_label(entry['confidence'])))
    if not facts['entry_points']:
        add('| （无） | - | - | - |')
    add('')

    add('## 解析失败与警告')
    add('')
    if not facts['warnings']:
        add('（无）')
    else:
        for warn in facts['warnings']:
            add('- [%s] %s：%s' % (warn['kind'], warn['file'], warn['message']))
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
    if counts['files'] == 0 or counts['files'] == counts['unsupported_files']:
        print('[WARN] zero supported source files (artifacts written anyway)')
        return 1
    return 0


# ---------------------------------------------------------------- 自测（--selftest）
class SelftestChecker(object):
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []

    def check(self, condition, label):
        if condition:
            self.passed += 1
        else:
            self.failed += 1
            self.failures.append(label)


FIXTURE_CORE = '''\
"""Core module of mini fixture."""
import os
from .helper import util_fn

MAX_ITEMS = 10
TAX_RATE, DISCOUNT = 0.1, 0.2

def compute_total(price, qty):
    base = price * qty
    print(base)
    return base * (1.0 + TAX_RATE) - DISCOUNT * base

class Cart:
    LIMIT = 5

    def add(self, item):
        return util_fn(len(item))

    def run(self, x):
        return self.add(x)

class Runner:
    def run(self, x):
        return undefined_helper(x)

def dispatch(obj):
    return obj.run(3)

make_counter = lambda n: n + 1
'''

FIXTURE_HELPER = '''\
def util_fn(x):
    return x + 1

def other_fn(x):
    return util_fn(x) + util_fn(x)
'''

FIXTURE_DECO = '''\
import functools


@functools.lru_cache(maxsize=None)
def cached_compute(n):
    return n * 2
'''

FIXTURE_APP = '''\
def main():
    print("app main")

if __name__ == '__main__':
    main()
'''

FIXTURE_PYPROJECT = '''\
[project]
name = "mini-fixture"

[project.scripts]
mini-cli = "mini.cli:main"
'''

FIXTURE_DOCS = '''\
def docs_probe():
    return 42
'''

FIXTURE_PROBE = '''\
def should_not_appear():
    return 1
'''

FIXTURE_JS = '''\
import { helper } from './helper';
import React from 'react';
const reg = /}.*{/g;

function greet(name) {
  const s = "}} string }";
  const t = `tpl } ${name}`;
  // comment with } braces
  return helper(s + t);
}

class Greeter {
  hello(x) {
    console.log(x);
    return x;
  }
}
'''

FIXTURE_JS_HELPER = '''\
function helper(s) {
  return s;
}
'''

FIXTURE_JS_SERVER = '''\
const app = require('./helper');
app.listen(3000, function () {
  console.log("up } ok");
});
'''

FIXTURE_TS = '''\
import React from 'react';

interface Config {
  name: string;
}

type Alias = Config | null;

enum Mode { On, Off }

const load = (c: Config): string => {
  return helper(c.name);
};
'''

FIXTURE_JAVA_MAIN = '''\
package demo;

import com.example.Util;

public class Main {
    public static final int MAX_TRIES = 3;

    public static void main(String[] args) {
        int total = Util.compute(2);
        System.out.println("java } brace");
    }
}
'''

FIXTURE_JAVA_UTIL = '''\
package com.example;

public class Util {
    public static int compute(int x) {
        return x * 2;
    }
}
'''

FIXTURE_JAVA_BROKEN = '''\
public class Broken {
    public void run() {
        System.out.println("never closed");
    }
'''

FIXTURE_C = '''\
#include "header.h"
#include <stdio.h>

#define MAX_NAME 32

struct Point {
    int x;
    int y;
};

int main(void) {
    struct Point p = {1, 2};
    printf("%d\\n", p.x);
    return p.x + MAX_NAME - 30;
}
'''

FIXTURE_H = '''\
#pragma once
#define HEADER_H 1
'''

FIXTURE_CPP = '''\
#include "geometry.hpp"
#include <vector>

namespace geo {
  class Rect {
  public:
    double w;
    double area() { return w; }
  };
}
'''

FIXTURE_HPP = '''\
#pragma once
#define GEO_HEADER 1
struct Vec { double x; };
'''

FIXTURE_CS = '''\
using System;

namespace Demo
{
  public class Window
  {
    public const int Max = 10;

    public string Title()
    {
      var msg = "brace } inside";
      return msg + DateTime.Now.Year;
    }
  }
}
'''

FIXTURE_GO = '''\
package main

import "fmt"

type Greeter struct {
    Name string
}

func (g Greeter) Shout() string {
    return "loud } text"
}

func main() {
    g := Greeter{Name: "x"}
    fmt.Println(g.Shout())
}
'''

FIXTURE_RUST = '''\
mod util;
use crate::util::helper;

pub struct Tag {
    pub name: String,
}

pub enum Mode { On, Off }

pub trait Shape {
    fn area(&self) -> f64;
}

impl Shape for Tag {
    fn area(&self) -> f64 {
        1.0
    }
}

const LIMIT: u32 = 3;
type Pair = (u32, u32);

fn main() {
    let v = helper(2);
    println!("{} {}", v, LIMIT);
}
'''

FIXTURE_RUST_UTIL = '''\
pub fn helper(x: u32) -> u32 {
    x + 1
}
'''

FIXTURE_PHP = '''\
<?php
require 'config.php';
use App\\Support\\Str;

define('APP_NAME', 'demo');

function shout($msg) {
    return strtoupper($msg);
}

$text = <<<EOT
brace } inside heredoc
EOT;

class Echo {
    public function send($m) {
        return shout($m);
    }
}
'''

FIXTURE_PHP_CFG = '<?php\n// config\n'

FIXTURE_RUBY = '''\
require_relative 'rhelper'

module Greet
  SIZE = 10

  class Greeter
    def initialize(name)
      @name = name
    end

    def shout
      words = ["end", "stop"]
      lines = words.map do |w|
        w.upcase
      end
      lines.join(" ")
    end
  end
end
'''

FIXTURE_RUBY_HELPER = '''\
def rhelper_fn(x)
  x + 1
end
'''

FIXTURE_RUBY_BROKEN = '''\
def broken_ruby(x)
  x + 1
'''

FIXTURE_KOTLIN = '''\
import java.util.Locale

class Widget(val name: String) {
  fun render(count: Int): String {
    return name + count
  }
}

fun main() {
  val w = Widget("demo")
  println(w.render(2))
}
'''

FIXTURE_SWIFT = '''\
import Foundation

struct Point {
  let x: Int
  func describe() -> String {
    return label
  }
}

protocol Drawable {
  func draw()
}

func mainish() -> Int {
  let p = Point(x: 1)
  return p.describe().count
}
'''

FIXTURE_SCALA = '''\
package demo

object Registry {
  val Limit = 3
  def lookup(key: String): String = {
    key
  }
}

trait Shape {
  def area(): Double
}

class Circle(r: Double) extends Shape {
  def area(): Double = {
    3.14 * r
  }
}

def main(args: Array[String]): Unit = {
  println(new Circle(1).area())
}
'''

FIXTURE_DART = '''\
import 'dart:math';

class Shape {
  double area() {
    return 0;
  }
}

class Square extends Shape {
  double side;
  Square(this.side);
  double area() {
    return side * side;
  }
}

void main() {
  final s = Square(2);
  print(s.area());
}
'''

FIXTURE_LUA = '''\
require 'lhelper'

local LIMIT = 5

function M.shout(msg)
  local up = string.upper(msg)
  return up
end

local function lx2(n)
  return n + 1
end
'''

FIXTURE_LUA_HELPER = '''\
local function lfn(x)
  return x * 2
end
'''

FIXTURE_VUE = '<template><div>probe</div></template>'

FIXTURE_ERL = '-module(skip).'

FIXTURE_PKG_JSON = '''\
{
  "name": "pkg",
  "bin": {"pkgcli": "bin/cli.js"},
  "scripts": {
    "start": "node index.js",
    "test": "echo ok"
  }
}
'''

FIXTURE_POM = '''\
<?xml version="1.0"?>
<project>
  <build>
    <plugins>
      <plugin>
        <configuration>
          <mainClass>demo.Main</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
'''

FIXTURE_CARGO = '''\
[package]
name = "demo"

[[bin]]
name = "demo-tool"
path = "src/main.rs"
'''

FIXTURE_COMPOSER = '''\
{
  "bin": ["bin/console"]
}
'''


def _write_bytes(root, rel, data):
    full = os.path.join(root, *rel.split('/'))
    parent = os.path.dirname(full)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(full, 'wb') as fh:
        fh.write(data)


def _materialize_fixture(root):
    """在临时目录物化多语言 mini fixture（不落盘常驻文件，AC-01/AC-34）。"""
    text_files = {
        'app.py': FIXTURE_APP,
        'pyproject.toml': FIXTURE_PYPROJECT,
        'docs/note.py': FIXTURE_DOCS,
        'src/__init__.py': '',
        'src/helper.py': FIXTURE_HELPER,
        'src/core.py': FIXTURE_CORE,
        'src/deco.py': FIXTURE_DECO,
        # --- 1b：多语言矩阵（16 门 + 排除目录探针 + manifest）---
        'langs/hello.js': FIXTURE_JS,
        'langs/helper.js': FIXTURE_JS_HELPER,
        'langs/server.js': FIXTURE_JS_SERVER,
        'langs/app.ts': FIXTURE_TS,
        'langs/Main.java': FIXTURE_JAVA_MAIN,
        'com/example/Util.java': FIXTURE_JAVA_UTIL,
        'langs/Broken.java': FIXTURE_JAVA_BROKEN,
        'langs/main.c': FIXTURE_C,
        'langs/header.h': FIXTURE_H,
        'langs/geometry.cpp': FIXTURE_CPP,
        'langs/geometry.hpp': FIXTURE_HPP,
        'langs/MainWindow.cs': FIXTURE_CS,
        'langs/main.go': FIXTURE_GO,
        'src/main.rs': FIXTURE_RUST,
        'src/util.rs': FIXTURE_RUST_UTIL,
        'langs/index.php': FIXTURE_PHP,
        'langs/config.php': FIXTURE_PHP_CFG,
        'langs/app.rb': FIXTURE_RUBY,
        'langs/rhelper.rb': FIXTURE_RUBY_HELPER,
        'langs/broken.rb': FIXTURE_RUBY_BROKEN,
        'langs/main.kt': FIXTURE_KOTLIN,
        'langs/app.swift': FIXTURE_SWIFT,
        'langs/Main.scala': FIXTURE_SCALA,
        'langs/main.dart': FIXTURE_DART,
        'langs/main.lua': FIXTURE_LUA,
        'langs/lhelper.lua': FIXTURE_LUA_HELPER,
        'langs/skip.vue': FIXTURE_VUE,
        'langs/skip.erl': FIXTURE_ERL,
        'apps/pkg/package.json': FIXTURE_PKG_JSON,
        'apps/java/pom.xml': FIXTURE_POM,
        'apps/rust/Cargo.toml': FIXTURE_CARGO,
        'apps/php/composer.json': FIXTURE_COMPOSER,
    }
    for rel in sorted(text_files):
        _write_bytes(root, rel, text_files[rel].encode('utf-8'))
    _write_bytes(root, 'src/no_trailing.py',
                 b'def no_tail(a):\n    return a * 3\n# no trailing newline')
    _write_bytes(root, 'src/crlf.py', b'def crlf_func(a):\r\n    return a - 1\r\n')
    _write_bytes(root, 'src/bad.py', b'def broken(:\n    pass\n')
    for name in PROBE_DIR_NAMES:
        _write_bytes(root, name + '/probe.py', FIXTURE_PROBE.encode('utf-8'))


def _find_symbol(facts, qualname):
    for sym in facts['symbols']:
        if sym['qualname'] == qualname:
            return sym
    return None


def _find_symbols(facts, qualname):
    """跨语言同名符号的全部匹配（末段名/限定名全局口径下的歧义消解）。"""
    return [s for s in facts['symbols'] if s['qualname'] == qualname]


def _find_call(facts, rel, line, callee):
    for call in facts['calls']:
        if (call['file'], call['line'], call['callee']) == (rel, line, callee):
            return call
    return None


def _paths_under(facts, dirname):
    """四个清单（+入口点）中位于该目录下的条目（AC-28 探针口径）。"""
    prefix = dirname + '/'
    hits = []
    hits += [r['path'] for r in facts['files'] if r['path'].startswith(prefix)]
    hits += [s['file'] for s in facts['symbols'] if s['file'].startswith(prefix)]
    hits += [i['file'] for i in facts['imports'] if i['file'].startswith(prefix)]
    hits += [c['file'] for c in facts['calls'] if c['file'].startswith(prefix)]
    hits += [e['file'] for e in facts['entry_points'] if e['file'].startswith(prefix)]
    return hits


def _fixture_root():
    """AC-01：fixture 物化到 tempfile.mkdtemp()，不落盘为常驻文件。

    兼容分支：本机受限进程令牌下，mkdtemp 以 0700 权限建出的目录会拒绝后续写入
    （2026-09-14 实测：该目录内建子目录/写文件均 WinError 5）。此时退回同父目录下
    的兄弟临时目录（仍由 mkdtemp 定名定址，仍属临时区，不留常驻文件）。
    返回 (mkdtemp 目录, fixture 根目录)。
    """
    tmp = tempfile.mkdtemp(prefix='c2c-structfacts-selftest-')
    root = os.path.join(tmp, 'mini')
    try:
        os.makedirs(root)
        return tmp, root
    except OSError:
        sibling = tmp + '-fixture'
        os.makedirs(sibling)
        return tmp, sibling


def run_selftest():
    checker = SelftestChecker()
    tmp, root = _fixture_root()
    try:
        _materialize_fixture(root)
        facts = build_facts(root)
        again = build_facts(root)
        excluded = build_facts(root, extra_excludes=['docs'])
        core = 'src/core.py'

        # --- F10 闭集表完备性 ---
        checker.check(all(len(CLOSED_SETS[k]) == v for k, v in CLOSED_SIZES.items()),
                      'F10 closed-set table sizes match the frozen contract')
        checker.check(set(LANG_EXTS) == set(LANG_IDS),
                      'F5 language matrix covers exactly the closed language set')
        checker.check(set(lang_extractor(l) for l in LANG_IDS) <= set(EXTRACTORS),
                      'F5 extractor mapping stays inside the closed extractor set')
        checker.check(len(EXT_TO_LANG) == sum(len(v) for v in LANG_EXTS.values()),
                      'F5 extension map has no duplicate extension')

        # --- F2 / J1 / J3 序列化契约 ---
        top_keys = ('schema_version', 'tool', 'root_name', 'languages', 'counts',
                    'files', 'symbols', 'imports', 'calls', 'entry_points', 'warnings')
        checker.check(set(facts) == set(top_keys),
                      'J1 top-level keys are exactly the frozen 11')
        checker.check(set(facts['counts']) == set(COUNT_KEYS),
                      'J1 counts keys are exactly the frozen 11')
        checker.check(facts['schema_version'] == SCHEMA_VERSION,
                      'F2 schema_version == 2')
        seen_conf = set([x['confidence'] for x in facts['calls']]
                        + [x['confidence'] for x in facts['imports']]
                        + [x['confidence'] for x in facts['entry_points']])
        checker.check(seen_conf <= set(CONFIDENCES),
                      'J3 confidence values stay inside {verified, inferred}')
        checker.check(dumps_facts(facts) == dumps_facts(again),
                      'AC-13 determinism: two runs serialize byte-identical')

        # --- 文件清单（F6.1）---
        rec = [r for r in facts['files'] if r['path'] == core]
        checker.check(len(rec) == 1 and rec[0]['language'] == 'python'
                      and rec[0]['lines'] == 29,
                      'F6.1 inventory: src/core.py is python with 29 lines')
        checker.check('pyproject.toml' not in [r['path'] for r in facts['files']],
                      'F5 metadata manifests are not registered as source files')
        checker.check('docs/note.py' in [r['path'] for r in facts['files']],
                      'AC-29 control: docs/note.py is registered without --exclude')

        # --- 符号表（F6.2 / AC-14）---
        sym = _find_symbol(facts, 'compute_total')
        checker.check(sym is not None
                      and (sym['kind'], sym['start_line'], sym['end_line'])
                      == ('function', 8, 11),
                      'F6.2 module function symbol (compute_total 8-11)')
        sym = _find_symbol(facts, 'Cart')
        checker.check(sym is not None
                      and (sym['kind'], sym['start_line'], sym['end_line'])
                      == ('class', 13, 20),
                      'F6.2 class symbol with end_line (Cart 13-20)')
        sym = _find_symbol(facts, 'Cart.add')
        checker.check(sym is not None
                      and (sym['kind'], sym['start_line'], sym['end_line'])
                      == ('method', 16, 17),
                      'F6.2 method qualname Class.method (Cart.add 16-17)')
        sym = _find_symbol(facts, 'Runner.run')
        checker.check(sym is not None
                      and (sym['kind'], sym['start_line'], sym['end_line'])
                      == ('method', 23, 24),
                      'F6.2 method of the second class (Runner.run 23-24)')
        sym = _find_symbol(facts, 'MAX_ITEMS')
        checker.check(sym is not None
                      and (sym['kind'], sym['start_line']) == ('constant', 5),
                      'F6.2 module-level assignment -> constant (MAX_ITEMS line 5)')
        tax = _find_symbol(facts, 'TAX_RATE')
        disc = _find_symbol(facts, 'DISCOUNT')
        checker.check(tax is not None and disc is not None
                      and tax['kind'] == 'constant' and disc['kind'] == 'constant'
                      and tax['start_line'] == 6 and disc['start_line'] == 6,
                      'F6.2 tuple unpacking yields two constants on line 6')
        sym = _find_symbol(facts, 'make_counter')
        checker.check(sym is not None
                      and (sym['kind'], sym['start_line']) == ('function', 29),
                      'F6.2 lambda assignment -> function kind (line 29)')
        checker.check(_find_symbol(facts, 'Cart.LIMIT') is None,
                      'F6.2 class-body assignment is not a module constant')
        sym = _find_symbol(facts, 'cached_compute')
        checker.check(sym is not None
                      and (sym['start_line'], sym['end_line']) == (5, 6),
                      'AC-14 decorator line excluded: start_line is the def line')

        # --- 行数口径（AC-16）---
        rec = [r for r in facts['files'] if r['path'] == 'src/no_trailing.py']
        checker.check(len(rec) == 1 and rec[0]['lines'] == 3,
                      'AC-16 file without trailing newline counts 3 lines')
        rec = [r for r in facts['files'] if r['path'] == 'src/crlf.py']
        checker.check(len(rec) == 1 and rec[0]['lines'] == 2,
                      'AC-16 CRLF file counts its line breaks once (2 lines)')

        # --- import 边（F6.4）---
        rel_imp = None
        std_imp = None
        for imp in facts['imports']:
            if imp['file'] == core and imp['line'] == 3:
                rel_imp = imp
            elif imp['file'] == core and imp['line'] == 2:
                std_imp = imp
        checker.check(rel_imp is not None
                      and rel_imp['target'] == 'src/helper.py'
                      and rel_imp['confidence'] == 'verified'
                      and rel_imp['external'] is False,
                      'F6.4 relative import resolves inside repo (verified)')
        checker.check(std_imp is not None
                      and std_imp['confidence'] == 'inferred'
                      and std_imp['external'] is True,
                      'F6.4 unresolvable stdlib import stays inferred + external')

        # --- 调用边诚实性（AC-23 正反两例 / F6.5）---
        call = _find_call(facts, core, 17, 'util_fn')
        checker.check(call is not None and call['confidence'] == 'verified'
                      and call['caller'] == 'Cart.add'
                      and call['candidates'] == 1,
                      'AC-23 defined callee -> verified with call-site line 17')
        call = _find_call(facts, core, 24, 'undefined_helper')
        checker.check(call is not None and call['confidence'] == 'inferred'
                      and call['caller'] == 'Runner.run',
                      'AC-23 undefined callee -> inferred (never verified)')
        call = _find_call(facts, core, 20, 'add')
        checker.check(call is not None and call['receiver'] == 'self'
                      and call['confidence'] == 'verified',
                      'F6.5 receiver captured for attribute call (self.add)')
        call = _find_call(facts, core, 27, 'run')
        checker.check(call is not None and call['candidates'] >= 2
                      and call['ambiguous'] is True
                      and call['confidence'] == 'verified',
                      'F6.5 same tail-name candidates -> ambiguous verified')
        checker.check(all(c['callee'] != 'print' for c in facts['calls'])
                      and facts['counts']['filtered_calls'] >= 3,
                      'F6.5 builtins filtered from calls but counted')
        keys = [(c['file'], c['line'], c['callee']) for c in facts['calls']]
        checker.check(len(keys) == len(set(keys))
                      and keys.count(('src/helper.py', 5, 'util_fn')) == 1,
                      'F6.5 duplicate (file, line, callee) collapsed to one edge')

        # --- 入口点（F6.6，1a 范围三类）---
        guard = [e for e in facts['entry_points'] if e['kind'] == 'main-guard']
        checker.check(len(guard) == 1 and guard[0]['file'] == 'app.py'
                      and guard[0]['line'] == 4
                      and guard[0]['confidence'] == 'verified',
                      'F6.6 main-guard at app.py:4 (verified)')
        heur = [e for e in facts['entry_points']
                if e['kind'] == 'filename-heuristic']
        heur_files = [e['file'] for e in heur]
        checker.check('app.py' in heur_files
                      and all(e['confidence'] == 'inferred' for e in heur),
                      'F6.6 filename-heuristic for app.py (inferred)')
        checker.check('src/main.rs' in heur_files and 'langs/broken.rb' not in heur_files,
                      'F6.6 main.rs rule requires src/ parent dir (1b 扩列)')
        script = [e for e in facts['entry_points'] if e['kind'] == 'console-script']
        checker.check(len(script) == 1
                      and script[0]['evidence'] == 'pyproject.toml#project.scripts'
                      and script[0]['confidence'] == 'verified',
                      'F6.6 console-script via section scan (no TOML library)')

        # --- 单文件解析失败不牵连（F1）---
        bad = [r for r in facts['files'] if r['path'] == 'src/bad.py']
        parse_warns = [w for w in facts['warnings'] if w['kind'] == 'parse-error']
        checker.check(len(bad) == 1 and bad[0]['parse_error']
                      and len(parse_warns) == 1
                      and facts['counts']['parse_errors'] == 1,
                      'F1 parse failure -> warning + parse_error, others unaffected')

        # --- AC-28 逐目录探针负例（四个清单零出现）---
        for name in PROBE_DIR_NAMES:
            checker.check(not _paths_under(facts, name),
                          'AC-28 excluded dir probe absent in four lists: ' + name)
        checker.check('should_not_appear' not in [s['name'] for s in facts['symbols']],
                      'AC-28 probe symbol never enters the symbol table')

        # --- AC-29 --exclude 追加而非替换 ---
        exc_paths = [r['path'] for r in excluded['files']]
        checker.check('docs/note.py' not in exc_paths
                      and 'docs_probe' not in [s['name'] for s in excluded['symbols']],
                      'AC-29 --exclude docs removes the docs probe')
        checker.check(not _paths_under(excluded, 'node_modules'),
                      'AC-29 default excludes stay active when --exclude appends')

        # ============ 1b：多语言矩阵断言（数据表驱动——R9 缓解：加语言=加一行）============
        EXPECT_SYMBOLS = (
            ('python', 'compute_total', 'function', 8, 11),
            ('javascript', 'greet', 'function', 5, 10),
            ('javascript', 'Greeter', 'class', 12, 17),
            ('javascript', 'Greeter.hello', 'method', 13, 16),
            ('typescript', 'Config', 'interface', 3, 5),
            ('typescript', 'Alias', 'type_alias', 7, 7),
            ('typescript', 'Mode', 'enum', 9, 9),
            ('typescript', 'load', 'function', 11, 13),
            ('java', 'Main', 'class', 5, 12),
            ('java', 'Main.MAX_TRIES', 'constant', 6, 6),
            ('java', 'Main.main', 'method', 8, 11),
            ('java', 'Util', 'class', 3, 7),
            ('java', 'Util.compute', 'method', 4, 6),
            ('c', 'Point', 'struct', 6, 9),
            ('c', 'MAX_NAME', 'constant', 4, 4),
            ('c', 'main', 'function', 11, 15),
            ('cpp', 'geo', 'module', 4, 10),
            ('cpp', 'geo.Rect', 'class', 5, 9),
            ('cpp', 'geo.Rect.area', 'method', 8, 8),
            ('csharp', 'Demo', 'module', 3, 15),
            ('csharp', 'Demo.Window', 'class', 5, 14),
            ('csharp', 'Demo.Window.Max', 'constant', 7, 7),
            ('csharp', 'Demo.Window.Title', 'method', 9, 13),
            ('go', 'Greeter', 'struct', 5, 7),
            ('go', 'Greeter.Shout', 'method', 9, 11),
            ('go', 'main', 'function', 13, 16),
            ('rust', 'util', 'module', 1, 1),
            ('rust', 'Tag', 'struct', 4, 6),
            ('rust', 'Mode', 'enum', 8, 8),
            ('rust', 'Shape', 'trait', 10, 12),
            ('rust', 'Tag.area', 'method', 15, 17),
            ('rust', 'LIMIT', 'constant', 20, 20),
            ('rust', 'Pair', 'type_alias', 21, 21),
            ('rust', 'main', 'function', 23, 26),
            ('php', 'APP_NAME', 'constant', 5, 5),
            ('php', 'shout', 'function', 7, 9),
            ('php', 'Echo', 'class', 15, 19),
            ('php', 'Echo.send', 'method', 16, 18),
            ('ruby', 'Greet', 'module', 3, 19),
            ('ruby', 'Greet.SIZE', 'constant', 4, 4),
            ('ruby', 'Greet.Greeter', 'class', 6, 18),
            ('ruby', 'Greet.Greeter.initialize', 'method', 7, 9),
            ('ruby', 'Greet.Greeter.shout', 'method', 11, 17),
            ('kotlin', 'Widget', 'class', 3, 7),
            ('kotlin', 'Widget.render', 'method', 4, 6),
            ('kotlin', 'main', 'function', 9, 12),
            ('swift', 'Point', 'struct', 3, 8),
            ('swift', 'Point.x', 'constant', 4, 4),
            ('swift', 'Point.describe', 'method', 5, 7),
            ('swift', 'Drawable', 'interface', 10, 12),
            ('swift', 'mainish', 'function', 14, 17),
            ('scala', 'Registry', 'module', 3, 8),
            ('scala', 'Registry.Limit', 'constant', 4, 4),
            ('scala', 'Registry.lookup', 'method', 5, 7),
            ('scala', 'Shape', 'trait', 10, 12),
            ('scala', 'Circle', 'class', 14, 18),
            ('scala', 'Circle.area', 'method', 15, 17),
            ('scala', 'main', 'function', 20, 22),
            ('dart', 'Shape', 'class', 3, 7),
            ('dart', 'Square', 'class', 9, 15),
            ('dart', 'Square.area', 'method', 12, 14),
            ('dart', 'main', 'function', 17, 20),
            ('lua', 'M.shout', 'method', 5, 8),
            ('lua', 'lx2', 'function', 10, 12),
            ('lua', 'LIMIT', 'variable', 3, 3),
        )
        sym_langs = set()
        for lang_id, qname, kind, s_line, e_line in EXPECT_SYMBOLS:
            cands = _find_symbols(facts, qname)
            checker.check(
                any(s['kind'] == kind and s['start_line'] == s_line
                    and s['end_line'] == e_line for s in cands),
                'AC-20 %s %s (%s %s-%s)' % (lang_id, qname, kind, s_line, e_line))
            sym_langs.add(lang_id)
        checker.check(sym_langs == set(LANG_IDS),
                      'AC-20 symbol matrix covers all 16 Tier-1 languages')

        # AC-21：brace 抗干扰（JS 串}/模板}/注释}/正则} 四例 + Java/C#/Go 各一例
        # 已由上表 end_line 精确断言承载；此处断言不平衡负例）
        brokenc = _find_symbol(facts, 'Broken')
        checker.check(brokenc is not None and brokenc['end_line'] is None,
                      'AC-21 unbalanced brace class -> end_line null (never guessed)')
        brokerr = _find_symbol(facts, 'broken_ruby')
        checker.check(brokerr is not None and brokerr['end_line'] is None,
                      'AC-54 unbalanced ruby def -> end_line null')
        unb_warns = [w for w in facts['warnings']
                     if w['kind'] == 'unbalanced-block']
        checker.check(len(unb_warns) == 2,
                      'AC-21/54 each unbalanced file carries one unbalanced-block warning')

        # AC-22：import 边多语言（(file, line, target, confidence, external) 数据表）
        EXPECT_IMPORTS = (
            ('src/core.py', 3, 'src/helper.py', 'verified', False),
            ('src/core.py', 2, 'os', 'inferred', True),
            ('langs/hello.js', 1, 'langs/helper.js', 'verified', False),
            ('langs/hello.js', 2, 'react', 'inferred', True),
            ('langs/Main.java', 3, 'com/example/Util.java', 'verified', False),
            ('langs/main.c', 1, 'langs/header.h', 'verified', False),
            ('langs/main.c', 2, 'stdio.h', 'inferred', True),
            ('langs/geometry.cpp', 1, 'langs/geometry.hpp', 'verified', False),
            ('langs/geometry.cpp', 2, 'vector', 'inferred', True),
            ('langs/main.go', 3, 'fmt', 'inferred', True),
            ('src/main.rs', 2, 'src/util.rs', 'verified', False),
            ('langs/index.php', 2, 'langs/config.php', 'verified', False),
            ('langs/app.rb', 1, 'langs/rhelper.rb', 'verified', False),
            ('langs/main.lua', 1, 'langs/lhelper.lua', 'verified', False),
            ('langs/app.ts', 1, 'react', 'inferred', True),
            ('langs/MainWindow.cs', 1, 'System', 'inferred', True),
            ('langs/main.kt', 1, 'java.util.Locale', 'inferred', True),
            ('langs/main.dart', 1, 'dart:math', 'inferred', True),
            ('langs/app.swift', 1, 'Foundation', 'inferred', True),
        )
        imp_index = {}
        for imp in facts['imports']:
            imp_index.setdefault((imp['file'], imp['line']), imp)
        for f, ln, tgt, conf, ext in EXPECT_IMPORTS:
            imp = imp_index.get((f, ln))
            checker.check(
                imp is not None and imp['target'] == tgt
                and imp['confidence'] == conf and imp['external'] == ext,
                'AC-22 import %s:%s -> %s (%s)' % (f, ln, tgt, conf))

        # AC-25：入口点八类各 ≥1（F-a：多 manifest 各自产条目，evidence 带相对路径）
        entry_kinds = set(e['kind'] for e in facts['entry_points'])
        checker.check(entry_kinds == set(ENTRY_KINDS),
                      'AC-25 all 8 entry-point kinds present')
        entries_of = lambda k: [e for e in facts['entry_points'] if e['kind'] == k]
        checker.check(len(entries_of('main-function')) >= 5,
                      'AC-25 main-function across at least 5 languages')
        checker.check(len(entries_of('manifest-main')) == 3,
                      'AC-25 manifest-main: pom mainClass + Cargo [[bin]] + composer bin')
        checker.check(len(entries_of('pkg-script')) == 2,
                      'AC-25 pkg-script one entry per scripts key')
        listen = entries_of('listen-call')
        checker.check(len(listen) == 1 and listen[0]['file'] == 'langs/server.js'
                      and listen[0]['line'] == 2,
                      'F6.6 listen-call at server.js:2 (inferred)')
        pkgb = entries_of('pkg-bin')
        checker.check(len(pkgb) == 1
                      and pkgb[0]['evidence'] == 'apps/pkg/package.json#bin',
                      'F-a pkg-bin evidence carries the manifest relative path')

        # AC-26：内建/全局名只计数不列条
        noise = ('print', 'printf', 'make', 'log', 'parseInt', 'println',
                 'Println', 'WriteLine', 'strtoupper', 'define', 'require',
                 'listen')
        call_names = set(c['callee'] for c in facts['calls'])
        checker.check(not (call_names & set(noise)),
                      'AC-26 builtins/global names never listed in calls')
        checker.check(facts['counts']['filtered_calls'] >= 10,
                      'AC-26 filtered calls counted (got %d)'
                      % facts['counts']['filtered_calls'])

        # AC-27：跨语言全量去重
        keys = [(c['file'], c['line'], c['callee']) for c in facts['calls']]
        checker.check(len(keys) == len(set(keys)),
                      'AC-27 no duplicate (file, line, callee) across languages')

        # AC-51：语言探测矩阵 + --lang 过滤
        checker.check(facts['counts']['languages'] == 16,
                      'AC-51 all 16 Tier-1 languages detected in fixture')
        checker.check(facts['counts']['unsupported_files'] == 2,
                      'AC-51 unsupported files counted (vue + erl)')
        py_only = build_facts(root, selected_langs={'python'})
        checker.check(all(s['extractor'] == 'ast' for s in py_only['symbols']),
                      'AC-51 --lang python filters non-python extraction')
        checker.check('langs/hello.js' in [r['path'] for r in py_only['files']],
                      'AC-51 inventory still lists other languages under --lang')

        # AC-52：闭集机检（全量产物，多一个取值都算违约）
        closed_ok = (
            all(s['kind'] in SYM_KINDS for s in facts['symbols'])
            and all(s['extractor'] in EXTRACTORS for s in facts['symbols'])
            and all(i['kind'] in IMPORT_KINDS for i in facts['imports'])
            and all(e['kind'] in ENTRY_KINDS for e in facts['entry_points'])
            and all(w['kind'] in WARNING_KINDS for w in facts['warnings'])
            and all(f['language'] in LANG_IDS for f in facts['files']
                    if f['language'] is not None))
        checker.check(closed_ok,
                      'AC-52 every enum value stays inside the F10 closed sets')

        # AC-53：extractor 归属（ast 只在 .py；.rb/.lua 为 end；其余 brace）
        py_paths = set(r['path'] for r in facts['files']
                       if r['path'].endswith('.py'))
        end_paths = set(r['path'] for r in facts['files']
                        if r['path'].endswith(('.rb', '.lua')))
        checker.check(all(s['extractor'] == 'ast' for s in facts['symbols']
                          if s['file'] in py_paths),
                      'AC-53 ast extractor appears only on python files')
        checker.check(all(s['extractor'] == 'end' for s in facts['symbols']
                          if s['file'] in end_paths),
                      'AC-53 end extractor on ruby/lua files')
        checker.check(all(s['extractor'] == 'brace' for s in facts['symbols']
                          if s['file'] not in py_paths
                          and s['file'] not in end_paths),
                      'AC-53 brace extractor on the other brace languages')

        # AC-55：未支持扩展名只进 files + 告警
        unsupported_warns = [w for w in facts['warnings']
                             if w['kind'] == 'unsupported-language'
                             and w['file'] in ('langs/skip.vue', 'langs/skip.erl')]
        checker.check(len(unsupported_warns) == 2,
                      'AC-55 unsupported extensions carry warnings')
        sym_files = set(s['file'] for s in facts['symbols'])
        checker.check('langs/skip.vue' not in sym_files
                      and 'langs/skip.erl' not in sym_files,
                      'AC-55 unsupported files never produce symbols')

        # AC-57：MD 断点清单条目集合恰好等于 inferred 调用边集合
        md_text = render_md(facts)
        checker.check('## 断点清单（Where the graph stops）' in md_text,
                      'AC-57 MD carries the breakpoint section heading')
        inferred_n = sum(1 for c in facts['calls']
                         if c['confidence'] == CONF_INFERRED)
        section = md_text.split('## 断点清单（Where the graph stops）', 1)[1]
        section = section.split('## 入口点', 1)[0]
        bullets = [ln for ln in section.splitlines() if ln.startswith('- 行 ')]
        checker.check(len(bullets) == inferred_n and inferred_n > 0,
                      'AC-57 breakpoint bullets equal inferred call edges (%d)'
                      % inferred_n)

        # 模式表完备性（R3 关键缓解：缺字段=机检红，不是引擎分支漏写）
        tables_complete = True
        for lang_id in LANG_IDS:
            if lang_id == 'python':
                continue
            tbl = LANG_TABLES.get(lang_id)
            if tbl is None or not tbl.get('decl') or not tbl.get('imports'):
                tables_complete = False
                break
            tables_complete = tables_complete and all(
                key in tbl for key in TABLE_REQUIRED_KEYS)
        checker.check(tables_complete,
                      'F6.3 pattern tables complete for all 15 non-python languages')

        # 边诚实性抽查：跨语言 verified 调用边带调用处行号（AC-23 多语言扩展）
        xcheck = (
            _find_call(facts, 'langs/Main.java', 9, 'compute') is not None
            and _find_call(facts, 'langs/main.go', 15, 'Shout') is not None
            and _find_call(facts, 'src/main.rs', 24, 'helper') is not None
            and _find_call(facts, 'langs/main.kt', 11, 'render') is not None
            and _find_call(facts, 'langs/index.php', 17, 'shout') is not None
            and _find_call(facts, 'langs/app.ts', 12, 'helper') is not None)
        checker.check(xcheck,
                      'AC-23 multi-language verified call edges at exact call sites')
    finally:
        _rmtree(root)
        _rmtree(tmp)
    print('selftest: %d passed / %d failed' % (checker.passed, checker.failed))
    for label in checker.failures:
        print('  FAIL %s' % label)
    return 0 if checker.failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
