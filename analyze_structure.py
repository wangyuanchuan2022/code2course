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
  * 语言面按冻结语言矩阵注册（16 门 Tier-1，F5）。当前实施步骤（1a）交付 Python 的
    ast 确定性引擎、基础 CLI、遍历阶段排除、序列化契约与自测框架；矩阵内非 Python
    文件先登记清单并标注语言，其表驱动启发式引擎（brace / end）由步骤 1b 接入。
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


# 步骤 1a 已接入抽取引擎的语言（其余语言 1b 接入：先登记清单、暂不产出符号）
ENGINES_READY = (LANG_IDS[0],)

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
FILENAME_ENTRY_BASENAMES = frozenset((
    'main.py', 'app.py', '__main__.py', 'manage.py', 'cli.py',
    'index.js', 'index.ts', 'app.js', 'app.ts', 'main.js', 'main.ts',
    'server.js', 'server.ts',
))

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
        if lang not in ENGINES_READY:
            continue                     # 矩阵内非 Python：1b 接入引擎前只登记清单
        if selected_langs is not None and lang not in selected_langs:
            continue
        unit, parse_error = analyze_python(root, rel, data, text, symbols,
                                           imports, entry_points, warnings)
        if parse_error is not None:
            rec['parse_error'] = parse_error
            warnings.append(_warn(rel, W_PARSE, parse_error))
        else:
            call_units.append((rel, unit))

    for rec in files:                    # 命名启发式入口点（清单口径，与引擎无关）
        if os.path.basename(rec['path']) in FILENAME_ENTRY_BASENAMES:
            entry_points.append({
                'kind': EP_FILENAME, 'file': rec['path'], 'line': 1,
                'evidence': os.path.basename(rec['path']),
                'confidence': CONF_INFERRED,
            })

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


def _write_bytes(root, rel, data):
    full = os.path.join(root, *rel.split('/'))
    parent = os.path.dirname(full)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(full, 'wb') as fh:
        fh.write(data)


def _materialize_fixture(root):
    """在临时目录物化 mini fixture（不落盘常驻文件，AC-01）。"""
    text_files = {
        'app.py': FIXTURE_APP,
        'pyproject.toml': FIXTURE_PYPROJECT,
        'docs/note.py': FIXTURE_DOCS,
        'src/__init__.py': '',
        'src/helper.py': FIXTURE_HELPER,
        'src/core.py': FIXTURE_CORE,
        'src/deco.py': FIXTURE_DECO,
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
        checker.check(call is not None and call['candidates'] == 2
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
        checker.check(len(heur) == 1 and heur[0]['file'] == 'app.py'
                      and heur[0]['confidence'] == 'inferred',
                      'F6.6 filename-heuristic for app.py (inferred)')
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
    finally:
        _rmtree(root)
        _rmtree(tmp)
    print('selftest: %d passed / %d failed' % (checker.passed, checker.failed))
    for label in checker.failures:
        print('  FAIL %s' % label)
    return 0 if checker.failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
