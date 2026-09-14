#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_analyze_structure.py -- analyze_structure.py 独立自测套件。

DEV-01 触发线落地（自测断言 > 150 条 → 拆分独立测试目录）：整个自测区自
analyze_structure.py 内嵌实现整体平移至此（fixture 常量 / checker / 全部断言 /
run 入口逐字保真，断言数不减：371 passed / 0 failed，exit 0）。

运行方式（等价二选一）：
    python tests/test_analyze_structure.py     # 直跑：selftest: N passed / M failed
    python analyze_structure.py --selftest     # 主文件兼容转发入口（子进程执行本文件）

加载方式：注入上级目录后 import analyze_structure as AS -- import 方式加载
主模块（旧自测为「主脚本方式」内嵌执行；该差异是 stdlib trace 覆盖率谜团的
裁决变量，复测结论见 agent-out/b5-c-split-report.md）。

主模块耦合面：被测常量与查询层辅助函数仍留在主文件，下方解包块显式登记全部
耦合名（缺名即 AttributeError 响亮失败）；仅测试使用的 FIXTURE_* 与断言逻辑
全部在本文件。
"""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyze_structure as AS

# ---- 主模块耦合白名单（拆分保真手段：区域逐字平移，经解包引用生产符号） ----
CLOSED_SETS = AS.CLOSED_SETS
CLOSED_SIZES = AS.CLOSED_SIZES
CONFIDENCES = AS.CONFIDENCES
CONF_INFERRED = AS.CONF_INFERRED
CONF_VERIFIED = AS.CONF_VERIFIED
COUNT_KEYS = AS.COUNT_KEYS
ENGINE_VERSION = AS.ENGINE_VERSION
ENTRY_KEYS = AS.ENTRY_KEYS
ENTRY_KINDS = AS.ENTRY_KINDS
EP_MANIFEST_MAIN = AS.EP_MANIFEST_MAIN
EP_PKG_BIN = AS.EP_PKG_BIN
EXTRACTORS = AS.EXTRACTORS
EXT_TO_LANG = AS.EXT_TO_LANG
GENERATED_STEM = AS.GENERATED_STEM
HONESTY_BLOCK = AS.HONESTY_BLOCK
IMPORT_KINDS = AS.IMPORT_KINDS
LANG_EXTS = AS.LANG_EXTS
LANG_IDS = AS.LANG_IDS
LANG_TABLES = AS.LANG_TABLES
PROBE_DIR_NAMES = AS.PROBE_DIR_NAMES
QUERY_COMMANDS = AS.QUERY_COMMANDS
RB_BINDING = AS.RB_BINDING
RB_NAME = AS.RB_NAME
RB_QUALIFIED = AS.RB_QUALIFIED
READ_MAX_BYTES = AS.READ_MAX_BYTES
RESOLUTIONS = AS.RESOLUTIONS
RESOLVED_BY = AS.RESOLVED_BY
R_AMBIGUOUS = AS.R_AMBIGUOUS
R_SELF_REF = AS.R_SELF_REF
R_UNIQUE = AS.R_UNIQUE
R_UNRESOLVED = AS.R_UNRESOLVED
SCHEMA_VERSION = AS.SCHEMA_VERSION
SYM_KINDS = AS.SYM_KINDS
TABLE_REQUIRED_KEYS = AS.TABLE_REQUIRED_KEYS
TO_CANDIDATE_LIMIT = AS.TO_CANDIDATE_LIMIT
UNRESOLVED_REASONS = AS.UNRESOLVED_REASONS
U_BUILTIN = AS.U_BUILTIN
U_EXTERNAL = AS.U_EXTERNAL
U_NOT_EXTRACTED = AS.U_NOT_EXTRACTED
WARNING_KINDS = AS.WARNING_KINDS
_call_site_key = AS._call_site_key
_cap_note = AS._cap_note
_conf_label = AS._conf_label
_is_trunc_note = AS._is_trunc_note
_lastseg = AS._lastseg
_list_sort_key = AS._list_sort_key
_node_id = AS._node_id
_rmtree = AS._rmtree
build_facts = AS.build_facts
build_query_index = AS.build_query_index
cmd_callees = AS.cmd_callees
cmd_callers = AS.cmd_callers
cmd_entry = AS.cmd_entry
cmd_impact = AS.cmd_impact
cmd_map = AS.cmd_map
cmd_path = AS.cmd_path
cmd_search = AS.cmd_search
detect_generated = AS.detect_generated
dumps_facts = AS.dumps_facts
has_generated_header = AS.has_generated_header
lang_extractor = AS.lang_extractor
load_facts = AS.load_facts
main = AS.main
manifest_entries = AS.manifest_entries
read_source = AS.read_source
render_md = AS.render_md
resolve_import = AS.resolve_import
resolve_symbols = AS.resolve_symbols
scan_tree = AS.scan_tree
vendored_hints = AS.vendored_hints

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
import { helper2 } from './helper.js';
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

# P2-4：数字/字符串字面量之后的 `/` 不是正则起点——曾被误当正则起点吞掉整段
# （`scale(2)` / `span(1)` 静默丢边）；`limit(3)` / `tail(2)` 是「没被吞」的正控制。
FIXTURE_JS_ARITH = '''\
const RATE = 8 / scale(2) / limit(3);
const SPAN = "n" / span(1) / tail(2);
'''

# P2-8：JS 方法调用不得被 Python 内建名清单过滤（map / filter 均在 dir(builtins)）
FIXTURE_JS_METHODS = '''\
function useAll(arr) {
  const mapped = arr.map(double);
  const kept = arr.filter(odd);
  return mapped;
}
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
require 'rhelper'
require 'no_such_ruby_gem'

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

# P1-7：Ruby `while/for … do … end` —— do 是语法标记而非新块；含循环的 def
# 曾经因 do 双计数永远凑不回 0（end_line=null + 假 unbalanced 告警）。
FIXTURE_RUBY_LOOPS = '''\
module Loop
  def self.count_down(items)
    i = 0
    while i < 3 do
      i += 1
    end
    for it in items do
      puts it
    end
    items.each do |x|
      puts x
    end
    0
  end
end
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

function M.loopy(items)
  for _, it in ipairs(items) do
    print(it)
  end
  while #items > 0 do
    print('drain')
  end
end

function M.driver(items)
  M.shout('x')
  return #items
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

# P0-1：FFI 边界形态（照 experiment-report D5-P0-1 的 :1075/:1332 真实形状构造）
FIXTURE_FFI = '''\
class Ffi:
    def win_rate(self, seq):
        return native.mscore.win_rate(seq)

    def helper(self, seq):
        return native.mscore.other(seq)

    def recurse_like(self, seq):
        return self.recurse_like(seq)

class Base:
    def __init__(self):
        pass

class Derived(Base):
    def __init__(self):
        super().__init__()
'''

# B0-A 变异体②：同一尾名在另一文件再定义一次 → win_rate 候选数升为 2
FIXTURE_FFI2 = '''\
def win_rate(seq):
    return seq
'''

# B-P0-3：含点属性链 + 链根本文件绑定（import 本地名）→ 实锤(绑定)
FIXTURE_NATIVE = '''\
def nat_target(x):
    return x
'''

FIXTURE_BINDER = '''\
import native

class B:
    def go(self, x):
        return native.bridge.nat_target(x)
'''

# B-P0-3 负向变异体：链根无任何本文件绑定 → 含点链不判 verified
FIXTURE_ORPHAN = '''\
class O:
    def go2(self, x):
        return ghost.bridge.nat_target(x)
'''

# B-P0-4 收窄正例：多候选但同文件唯一 → 保持 verified(名)
FIXTURE_AMB1 = '''\
def twin():
    return 1

def call_local():
    return twin()
'''

FIXTURE_AMB2 = '''\
def twin():
    return 2
'''

# B-P0-4 负例：多候选且同文件/import/限定名都收不窄 → inferred + 候选列表
FIXTURE_AMB_CALL = '''\
def caller_twin():
    return twin()
'''

# B-P0-2 限定名标签：receiver+callee 组成完整限定名精确命中
FIXTURE_QUALCALL = '''\
def qualify():
    return Cart.add(3)
'''

# A-P0-2 not_extracted_here：嵌套函数是声明形名字但不进符号表（JS 引擎跳过嵌套）
FIXTURE_JS_NESTED = '''\
function outerFn() {
  function innerFn() {
    return 1;
  }
  return innerFn();
}
'''

# A-P0-1：路径信号（_pb2.py 命名约定）
FIXTURE_PB2 = 'X = 1\n'

# A-P0-1：内容信号（banner 落在第 1 行的注释上；v2 口径：弱信号与指代词同行共现）
FIXTURE_GEN_BANNER = '''\
# This file is generated by the fixture generator tool.
# Do not edit.

def real_fn(x):
    return x
'''

# A-P0-1 负向变异体：banner 在 60 行窗口之外（按行数计）
FIXTURE_GEN_LATE = ('# late: banner beyond the 60-line window must not count\n'
                    'X = 1\n'
                    + ''.join('# pad line %d\n' % i for i in range(2, 62))
                    + '# Generated by the late tool. Do not edit.\n')

# A-P0-1 负向变异体：banner 在 8192 字符窗口之外（按字符计，行数不超限）
FIXTURE_GEN_WIDE = ('# ' + 'x' * 9000 + '\n'
                    '# Generated by the wide tool. Do not edit.\n')

# A-P0-1 负向变异体：同样的词出现在代码行（字符串字面量）不算 banner
FIXTURE_GEN_CODELINE = "msg = 'Generated by the build. Do not edit.'\n"

# P1-b：模板/限定返回类型、const / noexcept 限定成员、访问标号、pybind 模块出口
FIXTURE_CPP_FORMS = '''\
namespace forms {

struct Labeled {
public:
  int get() { return 1; }
private:
  int secret() const { return 2; }
};

struct Grid {
  std::vector<int> get_sizes(int n) {
    return {};
  }
  std::vector<std::vector<int>> make_grid(int n) {
    return {};
  }
  bool check_any(const std::vector<int>& xs) const {
    return true;
  }
  int safe() noexcept {
    return 0;
  }
};

}  // namespace forms

PYBIND11_MODULE(demo, m) {
  m.attr("x") = 1;
}
'''

# P1-c：构造函数初始化列表 + 多行 std::stable_sort(lambda) 两种跨语句吞并形态
FIXTURE_CPP_CTOR = '''\
struct Box {
  explicit Box(int c) : val(std::move(c)), flag(cb_none(c.is_none())) {}
  int val;
};

inline void sorter(std::vector<int>& v) {
  std::stable_sort(v.begin(), v.end(),
                   [](int a, int b) { return a < b; });
}
'''

# P1-a/P2-c：第三方目录名命中（vendored 提示信号）
FIXTURE_THIRD_PARTY = '''\
def vendored_helper(x):
    return x
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
        'langs/arith.js': FIXTURE_JS_ARITH,
        'langs/methods.js': FIXTURE_JS_METHODS,
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
        'langs/loops.rb': FIXTURE_RUBY_LOOPS,
        'langs/main.kt': FIXTURE_KOTLIN,
        'langs/app.swift': FIXTURE_SWIFT,
        'langs/Main.scala': FIXTURE_SCALA,
        'langs/main.dart': FIXTURE_DART,
        'langs/main.lua': FIXTURE_LUA,
        'langs/lhelper.lua': FIXTURE_LUA_HELPER,
        'langs/cppforms.hpp': FIXTURE_CPP_FORMS,
        'langs/box.hpp': FIXTURE_CPP_CTOR,
        'third_party/lib.py': FIXTURE_THIRD_PARTY,
        'src/ffi.py': FIXTURE_FFI,
        'src/ffi2.py': FIXTURE_FFI2,
        'src/native.py': FIXTURE_NATIVE,
        'src/binder.py': FIXTURE_BINDER,
        'src/orphan.py': FIXTURE_ORPHAN,
        'src/amb1.py': FIXTURE_AMB1,
        'src/amb2.py': FIXTURE_AMB2,
        'src/amb_call.py': FIXTURE_AMB_CALL,
        'src/qualcall.py': FIXTURE_QUALCALL,
        'langs/nested.js': FIXTURE_JS_NESTED,
        'langs/legacy_pb2.py': FIXTURE_PB2,
        'src/gen_banner.py': FIXTURE_GEN_BANNER,
        'src/gen_late.py': FIXTURE_GEN_LATE,
        'src/gen_wide.py': FIXTURE_GEN_WIDE,
        'src/gen_codeline.py': FIXTURE_GEN_CODELINE,
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
    _write_bytes(root, 'langs/bom.h',                  # P2-5：首行带 BOM
                 b'\xef\xbb\xbf#include "header.h"\n#define BOM_H 1\n')
    _write_bytes(root, 'apps/upper/GO.MOD',            # P2-6：大小写变体 manifest
                 b'module example.com/demo\n')
    _write_bytes(root, 'langs/esc.c',                  # secP2-5：签名含 ESC + 管道
                 b'int esc_fn(int a) {\x1b[31m /* | */\n'
                 b'  return a;\n'
                 b'}\n'
                 b'#include "weird|inc.h"\n')
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


def _writable_dir(base):
    """在 base 下建可写子目录；base 不可写（mkdtemp 0700 症候）时退回兄弟目录。"""
    probe = os.path.join(base, 'w')
    try:
        os.makedirs(probe)
        return probe
    except OSError:
        sibling = base + '-w'
        os.makedirs(sibling)
        return sibling


def _probe_dir(base, name, registry):
    """selftest 探针目录（物化在临时区；收尾按 registry 统一删除——含大体积 DoS 夹具）。"""
    path = os.path.join(base, name)
    os.makedirs(path, exist_ok=True)
    registry.append(path)
    return path


def run_selftest():
    checker = SelftestChecker()
    tmp, root = _fixture_root()
    probe_dirs = []
    try:
        _materialize_fixture(root)
        # P1-3 深嵌套探针文件（程序化生成，勿在 fixture 文本硬写巨串）：
        # ast.parse 可过、collect_calls 递归爆栈的真实形态。
        with open(os.path.join(root, 'src', 'deep_nest.py'), 'w',
                  encoding='utf-8') as dh:
            dh.write('x = ' + 'a.' * 1500 + 'b\n')
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
        top_keys = ('schema_version', 'tool', 'engine_version', 'root_name',
                    'languages', 'counts', 'files', 'symbols', 'imports',
                    'calls', 'entry_points', 'warnings')
        checker.check(set(facts) == set(top_keys),
                      'J1 top-level keys are exactly the frozen 12')
        checker.check(set(facts['counts']) == set(COUNT_KEYS),
                      'J1 counts keys are exactly the frozen 11')
        checker.check(facts['schema_version'] == SCHEMA_VERSION,
                      'F2 schema_version == 3')
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
                      and call['confidence'] == 'verified'
                      and call['resolved_by'] == RB_NAME,
                      'F6.5 receiver captured for attribute call (self.add)')
        call = _find_call(facts, core, 27, 'run')
        checker.check(call is not None and call['candidates'] == 3
                      and call['ambiguous'] is True
                      and call['confidence'] == 'inferred'
                      and call['resolution'] == R_AMBIGUOUS
                      and call['to'] is None
                      and call['candidates_total'] == 3
                      and len(call['to_candidates'])
                      == min(3, TO_CANDIDATE_LIMIT),
                      'B-P0-4 multi-candidate that cannot narrow -> inferred '
                      '(rejection is unresolved, never verified-then-filtered)')
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

        # --- 单文件解析失败不牵连（F1）+ P1-3 深嵌套隔离 ---
        bad = [r for r in facts['files'] if r['path'] == 'src/bad.py']
        bad_warns = [w for w in facts['warnings']
                     if w['kind'] == 'parse-error' and w['file'] == 'src/bad.py']
        deep_files = [r for r in facts['files']
                      if r['path'] == 'src/deep_nest.py']
        checker.check(len(bad) == 1 and bad[0]['parse_error']
                      and len(bad_warns) == 1
                      and len(deep_files) == 1 and deep_files[0]['parse_error']
                      and facts['counts']['parse_errors'] == 2,
                      'F1 parse failure + P1 deep-nest isolation: per-file '
                      'parse_error/warning, others unaffected')

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
            ('javascript', 'greet', 'function', 6, 11),
            ('javascript', 'Greeter', 'class', 13, 18),
            ('javascript', 'Greeter.hello', 'method', 14, 17),
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
            ('ruby', 'Greet', 'module', 5, 21),
            ('ruby', 'Greet.SIZE', 'constant', 6, 6),
            ('ruby', 'Greet.Greeter', 'class', 8, 20),
            ('ruby', 'Greet.Greeter.initialize', 'method', 9, 11),
            ('ruby', 'Greet.Greeter.shout', 'method', 13, 19),
            ('ruby', 'Loop', 'module', 1, 15),
            ('ruby', 'Loop.count_down', 'method', 2, 14),
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
            ('lua', 'M.loopy', 'method', 14, 21),
            ('lua', 'M.driver', 'method', 23, 26),
            ('cpp', 'forms.Labeled', 'struct', 3, 8),
            ('cpp', 'forms.Labeled.get', 'method', 5, 5),
            ('cpp', 'forms.Labeled.secret', 'method', 7, 7),
            ('cpp', 'forms.Grid', 'struct', 10, 23),
            ('cpp', 'forms.Grid.get_sizes', 'method', 11, 13),
            ('cpp', 'forms.Grid.make_grid', 'method', 14, 16),
            ('cpp', 'forms.Grid.check_any', 'method', 17, 19),
            ('cpp', 'forms.Grid.safe', 'method', 20, 22),
            ('cpp', 'PYBIND11_MODULE', 'function', 27, 29),
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
            ('langs/hello.js', 2, 'langs/helper.js', 'verified', False),
            ('langs/hello.js', 3, 'react', 'inferred', True),
            ('langs/Main.java', 3, 'com/example/Util.java', 'verified', False),
            ('langs/main.c', 1, 'langs/header.h', 'verified', False),
            ('langs/main.c', 2, 'stdio.h', 'inferred', True),
            ('langs/geometry.cpp', 1, 'langs/geometry.hpp', 'verified', False),
            ('langs/geometry.cpp', 2, 'vector', 'inferred', True),
            ('langs/main.go', 3, 'fmt', 'inferred', True),
            ('src/main.rs', 2, 'src/util.rs', 'verified', False),
            ('langs/index.php', 2, 'langs/config.php', 'verified', False),
            ('langs/app.rb', 1, 'langs/rhelper.rb', 'verified', False),
            ('langs/app.rb', 2, 'langs/rhelper.rb', 'verified', False),
            ('langs/app.rb', 3, 'no_such_ruby_gem', 'inferred', True),
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

        # P0 回归锁（ruby 裸 require 分支，2026-09-14 崩溃修复）：resolved /
        # evidence 语义断言——可解析裸 require 走逐级上溯命中 verified；不可解析
        # 保持 inferred + external。
        bare = imp_index.get(('langs/app.rb', 2))
        checker.check(
            bare is not None and bare['target'] == 'langs/rhelper.rb'
            and bare['confidence'] == CONF_VERIFIED and bare['external'] is False,
            'P0 ruby bare require resolves via the walked-up branch '
            '(langs/rhelper.rb, verified)')
        bare2 = imp_index.get(('langs/app.rb', 3))
        checker.check(
            bare2 is not None and bare2['target'] == 'no_such_ruby_gem'
            and bare2['confidence'] == CONF_INFERRED and bare2['external'] is True,
            'P0 unresolvable bare require keeps inferred+external semantics')

        # 分支级覆盖表：LANG_TABLES imports 引用的每个 resolver 分支都必须被
        # 一条最小合成片段探针执行到（防「分支从未被断言执行」——本表由 P0
        # ruby 漏测事故引入）。go_block 是 analyze_generic 的分发伪 resolver
        # （内部逐行转调 'go'），由 fixture 管线覆盖（EXPECT_IMPORTS main.go），
        # 不进直接探针表。
        RESOLVER_PROBES = (
            # (resolver, rel, spec, 期望 (target 后缀|None, found, external, dynamic))
            ('js', 'langs/hello.js', './helper',
             ('langs/helper.js', True, False, False)),
            ('js', 'langs/hello.js', 'react', (None, False, True, False)),
            ('js_dynamic', 'langs/hello.js', 'dyn()',
             (None, False, True, True)),
            ('c_quote', 'langs/main.c', 'header.h',
             ('langs/header.h', True, False, False)),
            ('c_angle', 'langs/main.c', 'stdio.h', (None, False, True, False)),
            ('dotfile', 'com/example/Main.java', 'Util',
             ('com/example/Util.java', True, False, False)),
            ('dotfile_cs', 'src/X.cs', 'System.Drawing',
             (None, False, True, False)),
            ('dotfile_kt', 'langs/main.kt', 'java.util.Locale',
             (None, False, True, False)),
            ('dotfile_swift', 'langs/app.swift', 'Foundation',
             (None, False, True, False)),
            ('dotfile_scala', 'langs/app.scala', 'scala.math',
             (None, False, True, False)),
            ('go', 'langs/main.go', 'fmt', (None, False, True, False)),
            ('rust', 'src/main.rs', 'crate::util',
             ('src/util.rs', True, False, False)),
            ('rust', 'src/main.rs', 'serde_json', (None, False, True, False)),
            ('php_use', 'langs/index.php', 'App\\Nope',
             (None, False, True, False)),
            ('path', 'langs/main.dart', 'dart:math',
             (None, False, True, False)),
            ('path', 'langs/main.dart', './nope.dart',
             (None, False, True, False)),
            ('ruby_rel', 'langs/app.rb', 'rhelper',
             ('langs/rhelper.rb', True, False, False)),
            ('ruby', 'langs/app.rb', 'rhelper',
             ('langs/rhelper.rb', True, False, False)),
            ('ruby', 'langs/app.rb', 'no_such_ruby_gem',
             (None, False, True, False)),
            ('lua', 'langs/main.lua', 'lhelper',
             ('langs/lhelper.lua', True, False, False)),
            ('lua', 'langs/main.lua', 'no_such_mod',
             (None, False, True, False)),
        )
        probed = set()
        for resolver, rel, spec, expect in RESOLVER_PROBES:
            got = resolve_import(resolver, root, rel, spec)
            suffix, p_found, p_ext, p_dyn = expect
            ok = (got[1] == p_found and got[2] == p_ext and got[3] == p_dyn
                  and (got[0].endswith(suffix) if suffix else got[0] is None))
            checker.check(ok,
                          'P0 resolver probe %s %r -> %r (got %r)'
                          % (resolver, spec, expect, got))
            probed.add(resolver)
        table_resolvers = set()
        for lang_id in LANG_IDS:
            tbl = LANG_TABLES.get(lang_id) or {}
            for _pat, _kind, resolver in tbl.get('imports', ()):
                table_resolvers.add(resolver)
        checker.check('go_block' in table_resolvers,
                      'P0 go_block pseudo-resolver present in tables '
                      '(pipeline-covered via EXPECT_IMPORTS main.go)')
        checker.check(table_resolvers - {'go_block'} == probed,
                      'P0 resolver branch coverage: every table resolver '
                      'directly probed, no stray probes (%d direct branches)'
                      % len(probed))

        # P1-2 逃逸闭包探针：仓库根 = out/，`../shared/` 真实存在于仓库根外
        # ——`../` 相对导入一律 external+inferred（永不 verified）；仓内控制组
        # 仍 verified。v1.13.2 补齐 c_quote / go / rust / lua 四分支（其余分支
        # 早已带闭包检查）。
        esc_root = _probe_dir(os.path.dirname(root), 'escape-probe', probe_dirs)
        esc_repo = _probe_dir(esc_root, 'out', probe_dirs)
        esc_shared = os.path.join(esc_root, 'shared')
        os.makedirs(esc_shared, exist_ok=True)
        esc_writes = (
            (esc_repo, 'a.js', 'import { u } from "../shared/util";\n'),
            (esc_repo, 'a.dart', "import '../shared/util.dart';\n"),
            (esc_repo, 'a.rb', "require_relative '../shared/helper'\n"),
            (esc_repo, 'a.c', '#include "../shared/util.h"\n'),
            (esc_repo, 'a.go', 'package main\n\nimport "../shared/goutil"\n'),
            (esc_repo, 'a.rs', 'use crate::..::..::shared::rustlib;\n'),
            (esc_repo, 'a.lua', "require('../shared/lua_mod')\n"),
            (esc_repo, 'self.js', 'const self = 1;\n'),
            # 仓内控制组：闭包检查不得误伤仓库内候选（四门新分支各一 + js）
            (esc_repo, 'util.h', '#pragma once\n#define LOCAL_H 1\n'),
            (esc_repo, 'golocal.go', 'package main\n'),
            (esc_repo, 'lua_local.lua', 'local function lf() end\n'),
            (esc_repo, 'src/local.rs', 'pub fn local_fn() {}\n'),
            (esc_shared, 'util.js', 'export const u = 1;\n'),
            (esc_shared, 'util.dart', 'const u = 1;\n'),
            (esc_shared, 'helper.rb', 'def u_helper(x)\n  x\nend\n'),
            # 仓库根外真实存在的目标：证明「逃逸被拦」不是「目标不存在」
            (esc_shared, 'util.h', '#pragma once\n'),
            (esc_shared, 'goutil.go', 'package shared\n'),
            (esc_shared, 'rustlib.rs', 'pub fn r() {}\n'),
            (esc_shared, 'lua_mod.lua', 'return {}\n'),
        )
        for esc_base, esc_name, esc_body in esc_writes:
            esc_full = os.path.join(esc_base, *esc_name.split('/'))
            esc_dir = os.path.dirname(esc_full)
            if esc_dir:
                os.makedirs(esc_dir, exist_ok=True)
            open(esc_full, 'w', encoding='utf-8').write(esc_body)
        esc_cases = (
            ('js', 'a.js', '../shared/util'),
            ('js', 'a.js', '../shared/util.js'),
            ('path', 'a.dart', '../shared/util.dart'),
            ('ruby_rel', 'a.rb', '../shared/helper'),
            ('ruby', 'a.rb', '../shared/helper'),
            ('c_quote', 'a.c', '../shared/util.h'),
            ('go', 'a.go', '../shared/goutil'),
            ('rust', 'a.rs', 'crate::..::..::shared::rustlib'),
            ('lua', 'a.lua', '../shared/lua_mod'),
        )
        for resolver, rel, spec in esc_cases:
            got = resolve_import(resolver, esc_repo, rel, spec)
            checker.check(got == (None, False, True, False),
                          'P1 escape blocked: %s %r -> inferred+external '
                          '(got %r)' % (resolver, spec, got))
        esc_controls = (
            ('js', 'a.js', './self', 'self.js'),
            ('c_quote', 'a.c', 'util.h', 'util.h'),
            ('go', 'golocal.go', 'golocal', 'golocal.go'),
            ('rust', 'a.rs', 'crate::local', 'src/local.rs'),
            ('lua', 'a.lua', 'lua_local', 'lua_local.lua'),
        )
        for resolver, rel, spec, want in esc_controls:
            got = resolve_import(resolver, esc_repo, rel, spec)
            checker.check(got == (want, True, False, False),
                          'P1 in-root control still verified: %s %r -> %r '
                          '(got %r)' % (resolver, spec, want, got))

        # P1-7：Ruby `while/for … do … end` 不再双计数——符号/行界由
        # EXPECT_SYMBOLS 的 (ruby, Loop.count_down, method, 2, 14) 锁定，
        # 此处锁「不再产生假 unbalanced 告警」。
        checker.check(not [w for w in facts['warnings']
                           if w['kind'] == 'unbalanced-block'
                           and w['file'] == 'langs/loops.rb'],
                      'P1-7 ruby loops.rb produces no spurious '
                      'unbalanced-block warning')

        # P1-3 深嵌套隔离断言：该文件 parse-error 优雅降级、其余文件照常
        deep_errs = [w for w in facts['warnings']
                     if w['file'] == 'src/deep_nest.py'
                     and w['kind'] == 'parse-error']
        checker.check(
            len(deep_errs) == 1 and 'RecursionError' in deep_errs[0]['message'],
            'P1 deep-nested file degrades to per-file parse-error warning')
        checker.check('src/deep_nest.py' in [r['path'] for r in facts['files']],
                      'P1 deep-nest file still inventoried')
        checker.check(_find_symbol(facts, 'compute_total') is not None,
                      'P1 deep-nested file does not taint the rest of the repo')

        # ---- P2 修订批次探针（v1.13.2）----
        # P2-4：数字/字符串之后的除法链不再被当正则字面量整段抹掉
        checker.check(_find_call(facts, 'langs/arith.js', 1, 'scale') is not None,
                      'P2-4 digits do not start a regex literal (scale(2) kept)')
        checker.check(_find_call(facts, 'langs/arith.js', 2, 'span') is not None,
                      'P2-4 string literals do not start a regex literal '
                      '(span(1) kept)')
        checker.check(_find_call(facts, 'langs/arith.js', 1, 'limit') is not None
                      and _find_call(facts, 'langs/arith.js', 2, 'tail') is not None,
                      'P2-4 control: calls after the division chain stay present')
        # P2-5：UTF-8 BOM 不再吞掉首行行首锚定的 import / 段头
        bom_imp = imp_index.get(('langs/bom.h', 1))
        checker.check(bom_imp is not None and bom_imp['target'] == 'langs/header.h'
                      and bom_imp['confidence'] == CONF_VERIFIED
                      and bom_imp['external'] is False,
                      'P2-5 BOM file still yields its first-line #include')
        checker.check(_find_symbol(facts, 'BOM_H') is not None,
                      'P2-5 control: the rest of the BOM file parses normally')
        bom_dir = os.path.join(os.path.dirname(root), 'bom-probe')
        os.makedirs(bom_dir, exist_ok=True)
        _write_bytes(bom_dir, 'pyproject.toml',
                     b'\xef\xbb\xbf[project.scripts]\nbom-cli = "bom:main"\n')
        bom_entries = manifest_entries(bom_dir, 'pyproject.toml',
                                       'pyproject.toml', [])
        checker.check(len(bom_entries) == 1
                      and bom_entries[0]['evidence']
                      == 'pyproject.toml#project.scripts'
                      and bom_entries[0]['confidence'] == CONF_VERIFIED,
                      'P2-5 BOM manifest still opens its first-line section')
        # P2-6：manifest 判定大小写不敏感（且不落进 files / unsupported）
        checker.check('apps/upper/GO.MOD' not in [r['path'] for r in facts['files']],
                      'P2-6 case-folded manifest is not registered as a source file')
        up_dir = os.path.join(os.path.dirname(root), 'upper-probe')
        os.makedirs(up_dir, exist_ok=True)
        _write_bytes(up_dir, 'PACKAGE.JSON', FIXTURE_PKG_JSON.encode('utf-8'))
        _write_bytes(up_dir, 'CARGO.TOML', FIXTURE_CARGO.encode('utf-8'))
        up_entries = manifest_entries(up_dir, 'PACKAGE.JSON', 'package.json', [])
        checker.check(len(up_entries) == 3
                      and sum(1 for e in up_entries if e['kind'] == EP_PKG_BIN) == 1,
                      'P2-6 case-folded basename dispatches to the package.json branch')
        up_cargo = manifest_entries(up_dir, 'CARGO.TOML', 'cargo.toml', [])
        checker.check(len(up_cargo) == 1 and up_cargo[0]['kind'] == EP_MANIFEST_MAIN,
                      'P2-6 cargo.toml branch reachable via the case-folded name')
        # P2-8：JS 方法调用不再被 Python 内建名清单吞掉（正控制见 AC-26 的 print）
        checker.check(_find_call(facts, 'langs/methods.js', 2, 'map') is not None,
                      'P2-8 JS arr.map() is not filtered as a python builtin')
        checker.check(_find_call(facts, 'langs/methods.js', 3, 'filter') is not None,
                      'P2-8 JS arr.filter() is not filtered as a python builtin')

        # ---- secP2 修订批次探针（v1.13.2，安全评审）----
        probe_base = os.path.dirname(root)
        # secP2-3：manifest 读取大小闸（真文件，不改全局常量）
        man_dir = _probe_dir(probe_base, 'manifest-probe', probe_dirs)
        with open(os.path.join(man_dir, 'package.json'), 'wb') as mh:
            mh.seek(READ_MAX_BYTES + 1)
            mh.write(b'\n')
        man_warns = []
        man_entries = manifest_entries(man_dir, 'package.json', 'package.json',
                                       man_warns)
        checker.check(man_entries == [] and len(man_warns) == 1
                      and man_warns[0]['kind'] == 'too-large',
                      'secP2-3 oversized manifest is not read (too-large warning)')
        # secP2-7：非普通文件不读（目录路径触发 isfile 预检；FIFO 在 Windows 不可建）
        rd_files = []
        rd_warns = []
        rd_rec, rd_data, _rd_text = read_source(root, 'langs', 'c',
                                                rd_files, rd_warns)
        checker.check(rd_data is None and len(rd_warns) == 1
                      and 'regular file' in rd_warns[0]['message']
                      and rd_rec['path'] == 'langs',
                      'secP2-7 non-regular path is skipped before open '
                      '(read-error warning)')
        # secP2-4：二次方扫描回归计时（不平衡块 × 声明数、无 '=' 的 C# const）
        dos_dir = _probe_dir(probe_base, 'dos-probe', probe_dirs)
        with open(os.path.join(dos_dir, 'unclosed.c'), 'w',
                  encoding='utf-8') as dh:
            for i in range(4000):
                dh.write('int f%d() {\n' % i)
        with open(os.path.join(dos_dir, 'consts.cs'), 'w',
                  encoding='utf-8') as dh:
            dh.write('class C {\n')
            for i in range(4000):
                dh.write('  const int a%d\n' % i)
            dh.write('}\n')
        cpu0 = os.times()[0] + os.times()[1]
        dos_facts = build_facts(dos_dir)
        dos_cpu = (os.times()[0] + os.times()[1]) - cpu0
        checker.check(len(dos_facts['symbols']) >= 4000,
                      'secP2-4 DoS fixture still extracts every declaration')
        checker.check(dos_cpu < 5.0,
                      'secP2-4 quadratic-scan regression: 4000 unclosed decls + '
                      '4000 const decls in %.2fs CPU (< 5s)' % dos_cpu)
        # secP2-2：文件 symlink 跳过（本机受限令牌无 SeCreateSymbolicLinkPrivilege
        # → 建不出链接时该断言退化为 host-gated 占位，详见报告第三节）
        sym_dir = _probe_dir(probe_base, 'symlink-probe', probe_dirs)
        outside = os.path.join(probe_base, 'outside-secret.txt')
        open(outside, 'w', encoding='utf-8').write('TOP SECRET\n')
        open(os.path.join(sym_dir, 'plain.py'), 'w', encoding='utf-8').write('x = 1\n')
        sym_ok = True
        try:
            os.symlink(outside, os.path.join(sym_dir, 'linked.py'))
        except (OSError, NotImplementedError, AttributeError):
            sym_ok = False
        sym_warns = []
        sym_paths = scan_tree(sym_dir, set(), sym_warns)
        checker.check('plain.py' in sym_paths,
                      'secP2-2 control: ordinary files stay listed by scan_tree')
        if sym_ok:
            checker.check('linked.py' not in sym_paths
                          and any(w['kind'] == 'symlink-skipped' for w in sym_warns),
                          'secP2-2 symlinked file is skipped with a '
                          'symlink-skipped warning')
        else:
            checker.check(True, 'secP2-2 file-symlink skip host-gated: os.symlink '
                                'denied on this host (no such privilege)')
        # AC-37②/D2：性能软门实测——10k 行多语言合成仓库（100k 行一次性探针见
        # agent-out\ac37b-probe-1132.py）。软门语义：超时只 WARN、退出码仍 0；
        # 本工具无超时逻辑，故此处以 CPU 上限锁「不得退化为分钟级」。
        ac_dir = _probe_dir(probe_base, 'ac37-probe', probe_dirs)
        with open(os.path.join(ac_dir, 'big.js'), 'w', encoding='utf-8') as ah:
            for i in range(2200):
                ah.write('function fn%d(a) {\n  return helper%d(a);\n}\n' % (i, i))
        with open(os.path.join(ac_dir, 'big.c'), 'w', encoding='utf-8') as ah:
            for i in range(900):
                ah.write('int cf%d(int a) {\n  return a + %d;\n}\n' % (i, i))
        with open(os.path.join(ac_dir, 'big.py'), 'w', encoding='utf-8') as ah:
            for i in range(700):
                ah.write('def pf%d(a):\n    return a + %d\n\n' % (i, i))
        cpu0 = os.times()[0] + os.times()[1]
        ac_facts = build_facts(ac_dir)
        ac_cpu = (os.times()[0] + os.times()[1]) - cpu0
        ac_lines = sum(r['lines'] for r in ac_facts['files'])
        checker.check(ac_lines >= 10000
                      and ac_facts['counts']['symbols'] >= 3800,
                      'AC-37 10k-line synthetic repo fully extracted (lines=%d '
                      'symbols=%d)'
                      % (ac_lines, ac_facts['counts']['symbols']))
        checker.check(ac_cpu < 20.0,
                      'AC-37 soft gate (10k lines, wall < 60s): %.2fs CPU'
                      % ac_cpu)

        # ---- v1.13.3 修订批次探针（R6 实验 backlog）----
        # P0-1：FFI 边界调用不得消解成「实锤自环」（报告 :1075/:1332 的真实形状）
        ffi_self = _find_call(facts, 'src/ffi.py', 3, 'win_rate')
        checker.check(ffi_self is not None
                      and ffi_self['confidence'] == CONF_INFERRED
                      and ffi_self.get('self_ref') is True
                      and ffi_self['receiver'] == 'native.mscore'
                      and ffi_self['resolution'] == R_SELF_REF
                      and ffi_self['candidates'] == 2
                      and ffi_self['to'] is None
                      and len(ffi_self['to_candidates']) == 2,
                      'P0-1/B0-A mutant: dotted-receiver multi-candidate '
                      'self-name call -> inferred + self_ref (got %r)'
                      % (ffi_self,))
        ffi_other = _find_call(facts, 'src/ffi.py', 6, 'other')
        checker.check(ffi_other is not None and not ffi_other.get('self_ref')
                      and ffi_other['confidence'] == CONF_INFERRED
                      and ffi_other['resolution'] == R_UNRESOLVED
                      and ffi_other['unresolved_reason'] == U_EXTERNAL,
                      'P0-1 control: a non-self FFI call carries no self_ref')
        ffi_selfcall = _find_call(facts, 'src/ffi.py', 9, 'recurse_like')
        checker.check(ffi_selfcall is not None
                      and ffi_selfcall.get('self_ref') is True
                      and ffi_selfcall['confidence'] == CONF_INFERRED
                      and ffi_selfcall['resolution'] == R_SELF_REF
                      and ffi_selfcall['to'] is not None
                      and ffi_selfcall['to']['qualname'] == 'Ffi.recurse_like',
                      'B0-A: same-name call (non-dotted receiver) downgraded '
                      'unconditionally; to keeps the unique same-name symbol')
        ffi_super = _find_call(facts, 'src/ffi.py', 17, '__init__')
        checker.check(ffi_super is not None
                      and ffi_super.get('self_ref') is True
                      and ffi_super['confidence'] == CONF_INFERRED
                      and ffi_super['receiver'] is None
                      and ffi_super['candidates'] == 2
                      and ffi_super['resolution'] == R_SELF_REF
                      and len(ffi_super['to_candidates']) == 2,
                      'B0-A mutant (G3 form): super().__init__ receiver=null '
                      'self-loop with candidates>=2 downgraded')
        checker.check('self_ref' in HONESTY_BLOCK and 'FFI' in HONESTY_BLOCK,
                      'P0-1 honesty block documents the FFI boundary / self_ref')
        # P1-b：模板/限定返回类型、const / noexcept 成员、pybind 模块出口；
        # 访问标号（public:/private:）不得被当成返回类型（实测踩过的回归）
        cpp_rows = [s for s in facts['symbols']
                    if s['file'] == 'langs/cppforms.hpp']
        checker.check(bool(cpp_rows)
                      and not [s for s in cpp_rows
                               if s['signature'].startswith(('public:',
                                                             'private:'))],
                      'P1-b access labels are not treated as return types')
        checker.check(_find_symbol(facts, 'PYBIND11_MODULE') is not None,
                      'P1-b pybind11 module init function is extracted')
        # P1-c：跨语句吞并的伪声明不进符号表；其行内的真实调用照常产出
        box_rows = [s for s in facts['symbols'] if s['file'] == 'langs/box.hpp']
        checker.check(bool(box_rows)
                      and not [s for s in box_rows
                               if s['qualname'].startswith('std.')],
                      'P1-c greedy-paren pseudo declarations dropped (got %r)'
                      % ([s['qualname'] for s in box_rows],))
        checker.check(_find_symbol(facts, 'Box.Box') is not None,
                      'P1-c control: the constructor itself is still a symbol')
        checker.check(_find_call(facts, 'langs/box.hpp', 7,
                                 'begin') is not None
                      and _find_call(facts, 'langs/box.hpp', 7,
                                     'end') is not None,
                      'P1-c control: calls inside the previously swallowed '
                      'multi-line call stay listed')
        # P1-d(B-P0-2) / A3-3：标签与证据来源绑定 + 调用边 extractor 归属
        checker.check(_conf_label(CONF_VERIFIED, RB_NAME) == '实锤(名)'
                      and _conf_label(CONF_VERIFIED, RB_BINDING) == '实锤(绑定)'
                      and _conf_label(CONF_VERIFIED, RB_QUALIFIED) == '实锤(限定)'
                      and _conf_label(CONF_VERIFIED) == '实锤'
                      and _conf_label(CONF_INFERRED) == '推断',
                      'B-P0-2 labels bind confidence to resolved_by evidence')
        hpp_calls = [c for c in facts['calls'] if c['file'].endswith('.hpp')]
        checker.check(bool(hpp_calls)
                      and all(c['extractor'] == 'brace' for c in hpp_calls)
                      and any(c['extractor'] == 'ast' for c in facts['calls']),
                      'A3-3 call edges carry the per-language extractor')
        # P1-a / P2-c：vendored 提示（只建议不自动排除）
        hints = vendored_hints(facts)
        checker.check(any(h[0] == 'exclude' and h[1] == 'third_party'
                          for h in hints),
                      'P1-a/P2-c vendored hint detects a third-party-named dir')
        checker.check(vendored_hints({'symbols': []}) == [],
                      'P1-a/P2-c vendored hint is empty when there are no symbols')

        # ---- v3 批次探针（facts schema v3 + 消解诚实性）----
        # ① A-P0-1 生成文件双信号：路径 / banner / 三条负向变异体
        gen_path = [r for r in facts['files']
                    if r['path'] == 'langs/legacy_pb2.py']
        checker.check(len(gen_path) == 1 and gen_path[0]['generated'] is True,
                      'A-P0-1 path signal: *_pb2.py convention flagged generated')
        gen_banner = [r for r in facts['files']
                      if r['path'] == 'src/gen_banner.py']
        checker.check(len(gen_banner) == 1 and gen_banner[0]['generated'] is True,
                      'A-P0-1 banner signal: comment-line banner flagged generated')
        for neg_path in ('src/gen_late.py', 'src/gen_wide.py',
                         'src/gen_codeline.py', 'src/core.py'):
            neg_rec = [r for r in facts['files'] if r['path'] == neg_path]
            checker.check(len(neg_rec) == 1
                          and neg_rec[0]['generated'] is False,
                          'A-P0-1 negative: %s stays not-generated' % neg_path)
        with open(os.path.abspath(__file__), 'r', encoding='utf-8') as _sf:
            self_src = _sf.read()
        checker.check(has_generated_header(self_src) is False
                      and detect_generated('analyze_structure.py',
                                           self_src) is False,
                      'A-P0-1 self-classification guard: the tool never flags '
                      'its own source as generated')
        checker.check(has_generated_header('') is False
                      and detect_generated('x.py', None) is False,
                      'A-P0-1 empty/unread input degrades to not-generated')
        checker.check(detect_generated('pkg/model_pb2.py') is True
                      and detect_generated('pkg/model.py') is False,
                      'A-P0-1 path-only signal works without content')
        # v2 双信号口径：中文正例 / 引用型与无指代负例 / 强信号单凭自身 / 快速拒绝放行
        checker.check(has_generated_header(
            '# 本文件由 protoc 自动生成，请勿手动修改\n') is True,
            'A-P0-1 v2: Chinese banner (self-ref + auto-gen) flagged generated')
        checker.check(has_generated_header(
            '# 该文件由代码生成器自动生成\n') is True,
            'A-P0-1 v2: Chinese banner with that-file ref flagged generated')
        checker.check(has_generated_header(
            '# Wraps the protobuf-generated classes '
            '(do not edit those files directly).\n') is False,
            'A-P0-1 v2: header referencing generated code without self-ref '
            'stays not-generated')
        checker.check(has_generated_header(
            '# Generated by protoc from schema.proto; see that file for '
            'details.\n') is False,
            'A-P0-1 v2: third-person generated-by note stays not-generated')
        checker.check(has_generated_header(
            '# 生成物在 build/ 目录，请勿手动修改生成文件\n') is False,
            'A-P0-1 v2: Chinese note without self-ref stays not-generated')
        checker.check(has_generated_header('# @generated by protoc\n') is True,
                      'A-P0-1 v2: @generated stays a standalone strong signal')
        checker.check(GENERATED_STEM.search('本文件由 X 自动生成') is not None,
                      'A-P0-1 v2: quick-reject stem passes Chinese banners')

        # ② A-P0-2 边身份：to 三元组 / unresolved_reason
        call = _find_call(facts, core, 17, 'util_fn')
        checker.check(call is not None and call['to'] ==
                      {'file': 'src/helper.py', 'qualname': 'util_fn',
                       'start_line': 1}
                      and call['resolution'] == R_UNIQUE
                      and call['resolved_by'] == RB_NAME
                      and call['to_candidates'] is None
                      and call['candidates_total'] is None,
                      'A-P0-2 unique tail-name edge carries the to identity')
        call = _find_call(facts, core, 24, 'undefined_helper')
        checker.check(call is not None and call['to'] is None
                      and call['resolution'] == R_UNRESOLVED
                      and call['unresolved_reason'] == U_EXTERNAL,
                      'A-P0-2 unresolved edge carries reason=external (ast '
                      'extraction never misses declarations)')
        call = _find_call(facts, 'langs/nested.js', 5, 'innerFn')
        checker.check(call is not None and call['resolution'] == R_UNRESOLVED
                      and call['unresolved_reason'] == U_NOT_EXTRACTED,
                      'A-P0-2 not_extracted_here: decl-shaped name missing '
                      'from the symbol table (nested JS function)')
        checker.check(U_BUILTIN in UNRESOLVED_REASONS
                      and all(c.get('unresolved_reason') != U_BUILTIN
                              for c in facts['calls']),
                      'A-P0-2 builtin_filtered stays a reserved reason (edges '
                      'are pre-filtered before entering calls)')

        # ③ B-P0-4 拒绝即未解析：收窄成功 vs 收不窄（正例+负例成对）
        call = _find_call(facts, 'src/amb_call.py', 2, 'twin')
        checker.check(call is not None and call['confidence'] == CONF_INFERRED
                      and call['resolution'] == R_AMBIGUOUS
                      and call['to'] is None
                      and call['to_candidates'] is not None
                      and len(call['to_candidates']) == 2
                      and call['candidates_total'] == 2,
                      'B-P0-4 un-narrowable multi-candidate -> inferred + '
                      'candidate list (never verified-then-filtered)')
        checker.check(all(set(c) == {'file', 'qualname', 'start_line'}
                          for c in call['to_candidates']),
                      'A-P0-2 candidate entries are identity triples')
        call = _find_call(facts, 'src/amb1.py', 5, 'twin')
        checker.check(call is not None and call['confidence'] == CONF_VERIFIED
                      and call['resolved_by'] == RB_NAME
                      and call['to'] == {'file': 'src/amb1.py',
                                         'qualname': 'twin',
                                         'start_line': 1},
                      'B-P0-4 control: same-file narrowing keeps the edge '
                      'verified(名) with a to identity')

        # ④ B-P0-3 含点链：绑定正例 / 无绑定负例 / 限定名标签
        call = _find_call(facts, 'src/binder.py', 5, 'nat_target')
        checker.check(call is not None and call['confidence'] == CONF_VERIFIED
                      and call['resolved_by'] == RB_BINDING
                      and call['resolution'] == R_UNIQUE
                      and call['to'] == {'file': 'src/native.py',
                                         'qualname': 'nat_target',
                                         'start_line': 1},
                      'B-P0-3 dotted chain with bound root -> verified(绑定)')
        call = _find_call(facts, 'src/orphan.py', 3, 'nat_target')
        checker.check(call is not None and call['confidence'] == CONF_INFERRED
                      and call['resolved_by'] is None
                      and call['to'] is not None
                      and call['resolution'] == R_UNIQUE,
                      'B-P0-3 negative: unbound dotted chain is never verified')
        call = _find_call(facts, 'src/qualcall.py', 2, 'add')
        checker.check(call is not None and call['confidence'] == CONF_VERIFIED
                      and call['resolved_by'] == RB_QUALIFIED
                      and call['to'] is not None
                      and call['to']['qualname'] == 'Cart.add',
                      'B-P0-2 qualified label: receiver+callee exact qualname hit')

        # ⑤ v3 不变式 + 注入必红变异体
        def _v3_ok(edges):
            return (
                all(e['confidence'] != CONF_VERIFIED
                    or (e.get('resolved_by') in RESOLVED_BY
                        and e['to'] is not None)
                    for e in edges)
                and all(e['confidence'] == CONF_INFERRED
                        for e in edges if e.get('self_ref'))
                and all(e['confidence'] == CONF_INFERRED and e['to'] is None
                        for e in edges if e['resolution'] == R_UNRESOLVED)
                and all(e['confidence'] == CONF_INFERRED and e['to'] is None
                        and e['to_candidates'] is not None
                        for e in edges if e['resolution'] == R_AMBIGUOUS)
                and all(e['to'] is not None
                        for e in edges if e['resolution'] == R_UNIQUE))
        checker.check(_v3_ok(facts['calls']),
                      'v3 invariants: verified <=> resolved_by+to; self_ref / '
                      'unresolved / ambiguous edges are never verified')
        m_flip = json.loads(dumps_facts(facts))
        next(e for e in m_flip['calls'] if e.get('self_ref'))['confidence'] = \
            CONF_VERIFIED
        checker.check(not _v3_ok(m_flip['calls']),
                      'v3 mutant: flipping a self_ref edge to verified turns '
                      'the invariant red')
        m_nob = json.loads(dumps_facts(facts))
        next(e for e in m_nob['calls']
             if e['confidence'] == CONF_VERIFIED)['resolved_by'] = None
        checker.check(not _v3_ok(m_nob['calls']),
                      'v3 mutant: verified edge without resolved_by turns red')
        m_unres = json.loads(dumps_facts(facts))
        next(e for e in m_unres['calls']
             if e['resolution'] == R_UNRESOLVED)['confidence'] = CONF_VERIFIED
        checker.check(not _v3_ok(m_unres['calls']),
                      'v3 mutant: verifying an unresolved edge turns red')
        m_cand = json.loads(dumps_facts(facts))
        next(e for e in m_cand['calls']
             if e['resolution'] == R_AMBIGUOUS)['to_candidates'] = None
        checker.check(not _v3_ok(m_cand['calls']),
                      'v3 mutant: ambiguous edge without candidates turns red')

        # ⑥ AC-52 v3 扩展：新字段闭集机检（全量产物，多一个取值都算违约）
        checker.check(
            all(e.get('resolution') in RESOLUTIONS for e in facts['calls'])
            and all(e.get('resolved_by') in (None,) + RESOLVED_BY
                    for e in facts['calls'])
            and all(e.get('unresolved_reason') in (None,) + UNRESOLVED_REASONS
                    for e in facts['calls'])
            and all(r['generated'] in (True, False) for r in facts['files']),
            'AC-52 v3: resolution/resolved_by/unresolved_reason/generated '
            'stay inside the frozen sets')

        # ⑦ A-P1-6 engine_version
        checker.check(isinstance(facts['engine_version'], int)
                      and facts['engine_version'] == ENGINE_VERSION,
                      'A-P1-6 engine_version is a top-level integer constant')
        checker.check('engine_version' in render_md(facts),
                      'A-P1-6 MD header carries engine_version')

        # ⑧ B-P2-3 同名候选上限：501 同名 → 整条放弃 + filtered 计数 + 按名告警
        cap_dir = _probe_dir(probe_base, 'namecap-probe', probe_dirs)
        with open(os.path.join(cap_dir, 'cap.js'), 'w', encoding='utf-8') as ch:
            for i in range(501):
                ch.write('function capme() { return %d; }\n' % i)
            ch.write('const cap_out = capme();\n')
        cap_cpu0 = os.times()[0] + os.times()[1]
        cap_facts = build_facts(cap_dir)
        cap_cpu = (os.times()[0] + os.times()[1]) - cap_cpu0
        checker.check(all(c['callee'] != 'capme'
                          for c in cap_facts['calls']),
                      'B-P2-3 cap: 501 same-name symbols -> the call edge is '
                      'dropped (never guessed)')
        checker.check(cap_facts['counts']['filtered_calls'] == 1,
                      'B-P2-3 cap: the dropped edge is counted in '
                      'filtered_calls')
        cap_warns = [w for w in cap_facts['warnings']
                     if w['kind'] == 'name-cap-exceeded']
        checker.check(len(cap_warns) == 1
                      and 'capme' in cap_warns[0]['message'],
                      'B-P2-3 cap: exactly one name-cap-exceeded warning '
                      'naming the tail name')
        checker.check(cap_cpu < 5.0,
                      'B-P2-3 cap probe stays linear (%.2fs CPU < 5s)'
                      % cap_cpu)

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

        # secP2-5：MD 注入防护（签名控制字符 / 表格单元格管道符）
        esc_sym = _find_symbol(facts, 'esc_fn')
        checker.check(esc_sym is not None
                      and '\x1b' not in esc_sym['signature'],
                      'secP2-5 control characters do not survive into signatures')
        esc_rows = [ln for ln in md_text.splitlines() if 'esc_fn' in ln]
        checker.check(bool(esc_rows) and all('\x1b' not in ln for ln in esc_rows)
                      and any('\\|' in ln for ln in esc_rows),
                      'secP2-5 MD escapes pipes from source lines (no raw ESC)')
        checker.check('weird\\|inc.h' in md_text
                      and 'weird|inc.h' not in md_text,
                      'secP2-5 MD escapes pipes inside import-target cells')

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

        # ============ 查询层（F8/F9，1c）============
        snapshot = dumps_facts(facts)          # AC-47 只读基线（查询前后逐字节比对）
        index = build_query_index(facts)

        # P2-9：Lua 点号符号的查询口径与调用边对齐（末段名）——`callers shout`
        # 原先查不到 M.shout（by_last 按带前缀的 name 登记）
        checker.check(any(s['qualname'] == 'M.shout'
                          for s in index['by_last'].get('shout', [])),
                      'P2-9 by_last is keyed on the tail name (index shout -> M.shout)')
        checker.check(any(s['qualname'] == 'M.driver'
                          for s in resolve_symbols(index, 'driver', False)),
                      'P2-9 tail-name query reaches a dotted Lua symbol '
                      '(resolve_symbols driver -> M.driver)')
        checker.check(_find_call(facts, 'langs/main.lua', 24, 'shout') is not None,
                      'P2-9 the diverging call edge is present (M.driver -> shout)')

        # P1-h / P2-b（v1.13.3）：map 行数聚合口径 + 多候选回显
        _mfh, _xh, _sh, mres_h, mnotes_h, _mtot_h = cmd_map(facts, 1, None,
                                                            False)
        checker.check(
            sum(n['lines'] for n in mres_h['nodes'])
            == sum(r['lines'] for r in facts['files'] if r['language']),
            'P1-h map line aggregate excludes unsupported/binary files')
        checker.check(any('without a supported language' in n
                          for n in mnotes_h),
                      'P1-h map note explains the line-count exclusion')
        multi_name = None
        for tail in sorted(index['by_last']):
            if len(index['by_last'][tail]) > 1 and tail not in index['by_qual']:
                multi_name = tail
                break
        checker.check(multi_name is not None,
                      'P2-b fixture provides a multi-candidate tail name')
        imp_notes = cmd_impact(facts, index, multi_name, False, 2, False)[4]
        checker.check(any('symbols share the name' in n for n in imp_notes),
                      'P2-b multi-candidate impact echoes the resolved symbol')
        pth_notes = cmd_path(facts, index, multi_name, 'compute_total', False,
                             False)[4]
        checker.check(any('symbols share the name' in n for n in pth_notes),
                      'P2-b multi-candidate path echoes the resolved symbol')
        prog = sys.argv[0] or 'analyze_structure.py'
        outdir_w = _writable_dir(tmp)
        facts_path = os.path.join(outdir_w, 'structure-facts.json')

        def _quiet_main(args):
            """进程内跑一次 CLI，stdout 重定向到临时文件（不污染 selftest 输出）。"""
            cap = os.path.join(outdir_w, 'capture.txt')
            old = sys.stdout
            fh = open(cap, 'w', encoding='utf-8')
            sys.stdout = fh
            try:
                code = main(list(args))
            finally:
                sys.stdout = old
                fh.close()
            with open(cap, 'r', encoding='utf-8') as rh:
                return code, rh.read()

        def _quiet_main2(args):
            """C-P1-1/C-P1-7 机检用：stdout+stderr 双捕获（SUCCESS 形状三件套
            要断「stderr 为空」，stdout 纯度要断 json.loads 全量一次成功）。"""
            cap_o = os.path.join(outdir_w, 'capture-out.txt')
            cap_e = os.path.join(outdir_w, 'capture-err.txt')
            old_o, old_e = sys.stdout, sys.stderr
            fo = open(cap_o, 'w', encoding='utf-8')
            fe = open(cap_e, 'w', encoding='utf-8')
            sys.stdout, sys.stderr = fo, fe
            try:
                code = main(list(args))
            finally:
                sys.stdout, sys.stderr = old_o, old_e
                fo.close()
                fe.close()
            with open(cap_o, 'r', encoding='utf-8') as ro:
                out = ro.read()
            with open(cap_e, 'r', encoding='utf-8') as reh:
                err = reh.read()
            return code, out, err

        # --- AC-38 子命令分发与向后兼容 ---
        old_cwd = os.getcwd()
        os.chdir(outdir_w)                     # 缺省 facts 路径必不存在 → 裸命令=用法错
        try:
            for sc in QUERY_COMMANDS:
                code, _out = _quiet_main([prog, sc])
                checker.check(code == 2,
                              'AC-38 bare subcommand %r exits 2 (usage)' % sc)
            code, _out = _quiet_main([prog, 'mapx', os.path.join(root, 'nope')])
            checker.check(code == 2,
                          'AC-38 forged subcommand name falls back to path '
                          'handling (exit 2, no crash)')
        finally:
            os.chdir(old_cwd)
        code, _out = _quiet_main([prog, 'analyze', root, '--outdir', outdir_w])
        checker.check(code == 0,
                      'AC-38 analyze subcommand form runs the v1 flow (exit 0)')
        cli_facts, err = load_facts(facts_path)
        checker.check(cli_facts is not None and err is None,
                      'F9 load_facts validates the analyze product')
        checker.check(cli_facts is not None
                      and dumps_facts(cli_facts) == dumps_facts(facts),
                      'AC-13 CLI-built facts equal the in-memory facts')

        # --- callers / callees（AC-39/40）---
        call_set = set((c['file'], c['line'], c['callee'])
                       for c in facts['calls'])
        vcall = None
        for c in facts['calls']:
            if c['confidence'] == CONF_VERIFIED and c.get('caller') \
                    and c['candidates'] == 1 \
                    and _find_symbol(facts, c['caller']) is not None:
                vcall = c
                break
        checker.check(vcall is not None,
                      'query fixture has an unambiguous verified '
                      'symbol-to-symbol call edge')
        caller_q = vcall['caller']
        callee_n = vcall['callee']
        code, out = _quiet_main([prog, 'callers', callee_n, '--facts',
                                 facts_path, '--format', 'json'])
        checker.check(code == 0,
                      'AC-48 callers CLI exits 0 with facts present')
        shell = json.loads(out)
        checker.check(sorted(shell) == ['found', 'limit', 'matched', 'notes',
                                        'query', 'results', 'symbol', 'total',
                                        'truncated'],
                      'F9 json shell keys are exactly the frozen nine (B3)')
        checker.check(shell['found'] and len(shell['results']) >= 1,
                      'AC-39 CLI callers returns call sites for known callee')
        bad = [r for r in shell['results']
               if r['confidence'] == CONF_VERIFIED
               and (r['file'], r['line'], r['symbol']) not in call_set]
        checker.check(not bad,
                      'AC-39 every verified callers row exists in facts.calls')
        crows = shell['results']
        cf, em, _s, erows, _n, _ct = cmd_callees(facts, index, caller_q,
                                                 False, 200)
        checker.check(cf and em >= 1,
                      'F8 matched reports symbol hits (callers/callees)')
        inv = [r for r in erows
               if (r['file'], r['line'], r['callee'])
               in set((x['file'], x['line'], x['symbol']) for x in crows)]
        checker.check(bool(inv) or not crows,
                      'AC-40 callees(caller) mirrors callers(callee) rows')
        nf, _m, _s, _r, _n, _nt = cmd_callers(facts, index, '__no_such__',
                                              False, 200)
        checker.check(nf is False,
                      'AC-39 callers on unknown symbol -> found:false')

        # --- impact（AC-41 / D-41）---
        def _verified_callers(node, seen):
            hit = set()
            for c in facts['calls']:
                if c['confidence'] != CONF_VERIFIED or not c.get('caller'):
                    continue
                if c['callee'] == node and _lastseg(c['caller']) not in seen:
                    hit.add(_lastseg(c['caller']))
            return hit

        caller_last = _lastseg(caller_q)
        imp_d = cmd_impact(facts, index, caller_q, False, 2, False)[3]['levels']
        exp1 = _verified_callers(caller_last, {caller_last})
        exp2 = set()
        for nm in exp1:
            exp2 |= _verified_callers(nm, {caller_last} | exp1)
        got1 = set(imp_d[0]['symbols']) if imp_d else set()
        got2 = set(imp_d[1]['symbols']) if len(imp_d) > 1 else set()
        checker.check(got1 == exp1 and got2 == exp2,
                      'AC-41 default impact levels equal an independent '
                      'verified-only oracle')
        imp_w = cmd_impact(facts, index, caller_q, False, 2, True)[3]['levels']
        checker.check(sum(len(l['symbols']) for l in imp_w)
                      >= sum(len(l['symbols']) for l in imp_d),
                      'AC-41 --include-inferred radius >= default radius')
        imp_1 = cmd_impact(facts, index, caller_q, False, 1, False)[3]['levels']
        checker.check(len(imp_1) <= 1, 'F8 --depth caps impact levels')
        imp_x = cmd_impact(facts, index, '__no_such__', False, 2, False)
        checker.check(imp_x[0] is False and imp_x[3]['levels'] == [],
                      'AC-41 impact on unknown symbol -> found:false')

        # --- path（AC-42 / D-41）---
        pf, _m, _s, pres, _n, _pt = cmd_path(facts, index, caller_q, callee_n,
                                             False, False)
        checker.check(pf is True and len(pres['hops']) >= 1,
                      'AC-42 path finds a verified route')
        checker.check(all(h['confidence'] == CONF_VERIFIED
                          for h in pres['hops']),
                      'D-41 default path hops are verified-only')
        checker.check(all((h['file'], h['line'], h['to']) in call_set
                          for h in pres['hops']),
                      'AC-42 every hop exists in facts.calls')
        chain = [pres['hops'][0]['from']] + [h['to'] for h in pres['hops']]
        checker.check(chain[0] == caller_last and chain[-1] == callee_n,
                      'AC-42 hop chain connects from -> to')
        _pf2, _m2, _s2, pres2, _n2, _pt2 = cmd_path(facts, index, caller_q,
                                                    callee_n, False, False)
        checker.check(json.dumps(pres, sort_keys=True)
                      == json.dumps(pres2, sort_keys=True),
                      'AC-42 two runs identical (deterministic shortest path)')
        npf, _m, _s, nres, nnotes, _npt = cmd_path(facts, index, callee_n,
                                                   '__no_such__', False, False)
        checker.check(npf is False and nres['hops'] == [] and nnotes,
                      'AC-42 unknown target -> found:false + hops:[] + note')
        lpf, _m, _s, lres, lnotes, _lpt = cmd_path(facts, index, 'Util',
                                                   'compute_total', False,
                                                   False)
        checker.check(lpf is False and lres['hops'] == []
                      and any('实锤' in n for n in lnotes),
                      'AC-42 no route between known endpoints -> found:false '
                      '+ hops:[] + 未找到实锤路径 note')

        # --- map（AC-43）---
        _mf, _x, _s, mres, _n, _mt = cmd_map(facts, 1, None, False)
        checker.check(sum(n['files'] for n in mres['nodes'])
                      == facts['counts']['files'],
                      'AC-43 map node files sum == counts.files')
        checker.check(all(e['verified'] + e['inferred'] + e['external']
                          == e['count'] for e in mres['edges']),
                      'AC-43 per-edge columns sum to count')
        file_set = set(r['path'] for r in facts['files'])
        xdir = sum(1 for i in facts['imports']
                   if not i.get('external') and i['target'] in file_set
                   and _node_id(i['file'], 1, False)
                   != _node_id(i['target'], 1, False))
        checker.check(sum(e['count'] for e in mres['edges']) == xdir,
                      'AC-43 edge count sum == cross-directory import edges')
        _mf2, _x, _s, mres_f, _n, _mt2 = cmd_map(facts, 1, None, True)
        checker.check(len(mres_f['nodes']) == facts['counts']['files'],
                      'F8 --files granularity: one node per file')
        _mf3, _x, _s, mres_d, _n, _mt3 = cmd_map(facts, 1, 'langs', False)
        langs_n = sum(1 for r in facts['files']
                      if r['path'].startswith('langs/'))
        checker.check(sum(n['files'] for n in mres_d['nodes']) == langs_n,
                      'AC-43 --dir restricts the file sum to the subtree')

        # --- entry（AC-44）---
        _ef, _x, _s, erows2, _n, _et = cmd_entry(facts, None)
        set_a = set((e['kind'], e['file'], e['line'])
                    for e in facts['entry_points'])
        set_b = set((e['kind'], e['file'], e['line']) for e in erows2)
        checker.check(set_a == set_b and bool(set_a),
                      'AC-44 entry set equals facts.entry_points')
        k0 = sorted(set_a)[0][0]
        _efk, _x, _s, erowsk, _n, _etk = cmd_entry(facts, k0)
        checker.check(erowsk and all(e['kind'] == k0 for e in erowsk),
                      'AC-44 --kind filters to a subset')
        checker.check(all(set(e) >= set(ENTRY_KEYS) for e in erows2),
                      'F9 entry rows carry the frozen five keys')

        # --- search（AC-45）---
        sf, _m, _s, sres, _n, _st = cmd_search(facts, callee_n, 'all', 200)
        checker.check(sf is True and sorted(sres)
                      == ['calls', 'files', 'symbols'],
                      'F9 search results carry exactly the three domains')
        facts_symbols = [dict(s) for s in facts['symbols']]
        checker.check(sf is True and sres['symbols']
                      and all(any(s == o for o in facts_symbols)
                              for s in sres['symbols'])
                      and all(callee_n in s['qualname'].lower()
                              for s in sres['symbols']),
                      'AC-45 search rows are facts entries (no invented rows)')
        sf2, _m, _s, sres2, _n, _st2 = cmd_search(facts, callee_n.upper(),
                                                  'symbol', 200)
        checker.check(sf2 is True and bool(sres2['symbols']),
                      'AC-45 search is case-insensitive')
        sf3, _m, _s, sres3, _n, _st3 = cmd_search(facts, callee_n, 'symbol',
                                                  200)
        checker.check(sres3['calls'] == [] and sres3['files'] == []
                      and bool(sres3['symbols']),
                      'AC-45 --in symbol excludes the other domains')
        snf, _m, _s, snres, _n, _snt = cmd_search(facts, 'zzz_no_hit_zzz',
                                                  'all', 200)
        checker.check(snf is False
                      and not any(snres[k] for k in snres),
                      'AC-45 fake keyword -> found:false, empty domains')
        _sl, _m, _s, sres_l, _n, _stl = cmd_search(facts, 'e', 'symbol', 3)
        checker.check(len(sres_l['symbols']) <= 3,
                      'F8 --limit caps result count')

        # --- 退出码与只读（AC-47/48，CLI 端到端）---
        code, out = _quiet_main([prog, 'callers', '--facts', facts_path])
        checker.check(code == 2, 'AC-48 missing <symbol> exits 2')
        code, _out = _quiet_main([prog, 'map', '--facts',
                                  os.path.join(outdir_w, 'nope.json')])
        checker.check(code == 1, 'AC-48 missing facts file exits 1 (loud)')
        bad_json = os.path.join(outdir_w, 'bad.json')
        with open(bad_json, 'w', encoding='utf-8') as bh:
            bh.write('{oops')
        code, _out = _quiet_main([prog, 'map', '--facts', bad_json])
        checker.check(code == 1, 'AC-48 invalid JSON exits 1 (loud)')
        mutant_schema = json.loads(dumps_facts(facts))
        mutant_schema['schema_version'] = SCHEMA_VERSION + 1
        bad_schema = os.path.join(outdir_w, 'bad-schema.json')
        with open(bad_schema, 'w', encoding='utf-8') as sh:
            sh.write(dumps_facts(mutant_schema))
        code, _out = _quiet_main([prog, 'map', '--facts', bad_schema])
        checker.check(code == 1,
                      'AC-48 schema_version mismatch exits 1 (loud)')
        code, _out = _quiet_main([prog, 'search', 'kw', '--facts', facts_path,
                                  '--in', 'bogus'])
        checker.check(code == 2, 'AC-48 invalid --in exits 2')
        code, _out = _quiet_main([prog, 'entry', '--facts', facts_path,
                                  '--kind', 'nope'])
        checker.check(code == 2, 'AC-48 invalid --kind exits 2')
        code, out = _quiet_main([prog, 'callers', callee_n, '--facts',
                                 facts_path, '--format', 'md'])
        checker.check(code == 0 and callee_n in out
                      and '%s:%d' % (vcall['file'], vcall['line']) in out,
                      'AC-46 md form carries symbol and file:line')
        checker.check('实锤' in out,
                      'AC-46 md marks verified rows (实锤/推断 labels)')
        code, out = _quiet_main([prog, 'search', callee_n, '--facts', facts_path,
                                 '--format', 'md'])
        checker.check(code == 0
                      and re.search(r'matched: \d+ symbols, \d+ calls, \d+ files',
                                    out) is not None,
                      'P2-a search header counts symbols/calls/files')
        checker.check(dumps_facts(facts) == snapshot,
                      'AC-47 query functions never mutate facts (byte-identical)')

        # --- B3 输出契约机检（C-P0-2/P1-1/P1-2/P1-6/P1-7，门禁先行批次）---
        tc = None
        n_sites = 0
        for k in sorted(index['by_callee'],
                        key=lambda k: (-len(index['by_callee'][k]), k)):
            if resolve_symbols(index, k, False):
                tc = k
                n_sites = len(index['by_callee'][k])
                break
        checker.check(tc is not None and n_sites >= 2,
                      'B3 fixture provides a resolvable multi-site callee')
        # B3(1) 恰好截断：limit = 全量-1 → 表头数=保留数 + 触发点截断标记
        cf1, _m1, _s1, kept1, notes1, tot1 = cmd_callers(facts, index, tc,
                                                         False, n_sites - 1)
        checker.check(cf1 is True and len(kept1) == n_sites - 1
                      and tot1 == n_sites
                      and notes1 == [_cap_note('', n_sites - 1, n_sites)],
                      'B3(1) callers limit probe reports exact truncation '
                      'with retained-count header data')
        # B3(2) 恰好不截断：limit = 全量 → 无截断标记（多取一条探测为空）
        cf2, _m2, _s2, kept2, notes2, tot2 = cmd_callers(facts, index, tc,
                                                         False, n_sites)
        checker.check(len(kept2) == n_sites and tot2 == n_sites
                      and notes2 == [],
                      'B3(2) exactly-at-limit fetch is not flagged truncated')
        # B3(3) md 出口：listed 表头 = 保留数 + 就地截断行（触发点，非末尾通用句）
        code, out = _quiet_main([prog, 'callers', tc, '--facts', facts_path,
                                 '--limit', str(n_sites - 1), '--format', 'md'])
        checker.check(code == 0
                      and ('listed: %d call site(s)' % (n_sites - 1)) in out
                      and _cap_note('', n_sites - 1, n_sites) in out,
                      'B3(3) md lists retained count with in-place truncation '
                      'marker')
        # B3(4) json 出口：truncated/total/limit 三字段
        code, out = _quiet_main([prog, 'callers', tc, '--facts', facts_path,
                                 '--limit', str(n_sites - 1), '--format',
                                 'json'])
        sh3 = json.loads(out)
        checker.check(code == 0 and sh3['truncated'] is True
                      and sh3['total'] == n_sites
                      and sh3['limit'] == n_sites - 1
                      and len(sh3['results']) == n_sites - 1,
                      'B3(4) json shell carries truncated/total/limit triple')
        # B3(5) search 域级截断：标记带域前缀、就地放在该域块旁
        _sf, _sm, _ss, _srt, snotes_t, _stt = cmd_search(facts, tc, 'all', 1)
        call_note = next((n for n in snotes_t
                          if n.startswith('calls ') and _is_trunc_note(n)),
                         None)
        checker.check(call_note is not None
                      and ('显示 1 / 共 ' in call_note),
                      'B3(5) search truncation note is domain-prefixed')
        code, out = _quiet_main([prog, 'search', tc, '--facts', facts_path,
                                 '--limit', '1', '--format', 'md'])
        hdr = re.search(r'matched: (\d+) symbols, (\d+) calls, (\d+) files',
                        out)
        rows_n = (len([l for l in out.splitlines()
                       if l.startswith('- symbol ')]),
                  len([l for l in out.splitlines()
                       if l.startswith('- call ')]),
                  len([l for l in out.splitlines()
                       if l.startswith('- file ')]))
        checker.check(code == 0 and call_note is not None
                      and call_note in out and hdr is not None
                      and (int(hdr.group(1)), int(hdr.group(2)),
                           int(hdr.group(3))) == rows_n,
                      'B3(6) search header counts equal rendered rows; '
                      'domain note in place')
        # B3(7) SUCCESS 形状三件套（C-P1-1）：exit 0 + [OK] no matches + stderr 空
        code, out, err = _quiet_main2([prog, 'callers', '__no_such_sym__',
                                       '--facts', facts_path])
        checker.check(code == 0 and '[OK] no matches' in out and err == '',
                      'B3(7) no-match SUCCESS shape: exit 0 + [OK] + clean '
                      'stderr')
        # B3(8) 两出口形状一致：json 无结果同为 exit 0 + found:false + stderr 空
        code, out, err = _quiet_main2([prog, 'callers', '__no_such_sym__',
                                       '--facts', facts_path, '--format',
                                       'json'])
        sh8 = json.loads(out)
        checker.check(code == 0 and sh8['found'] is False and err == '',
                      'B3(8) json no-match shape matches the md outlet '
                      '(classify shared)')
        # B3(9) json 通道纯净（C-P1-7）：全部子命令 stdout 一次 json.loads 成功
        json_ok = True
        for sc, sc_args in (('map', []), ('entry', []), ('search', [tc]),
                            ('callers', [tc]), ('callees', [tc]),
                            ('impact', [tc]),
                            ('path', [tc, 'compute_total'])):
            c2, o2, e2 = _quiet_main2([prog, sc] + sc_args
                                      + ['--facts', facts_path,
                                         '--format', 'json'])
            try:
                json.loads(o2)
            except ValueError:
                json_ok = False
            json_ok = json_ok and c2 == 0 and e2 == ''
        checker.check(json_ok,
                      'B3(9) every subcommand: --format json stdout parses '
                      'in one json.loads with clean stderr')
        # B3(10) 全序 + 去重键单点 + 确定性（C-P1-2）
        ca, _ma, _sa, rows_a, _na, ta = cmd_callers(facts, index, tc, False, 0)
        cb, _mb, _sb, rows_b, _nb, tb = cmd_callers(facts, index, tc, False, 0)
        keys_a = [_list_sort_key(r['caller'], r['file'], r['line'], r['symbol'])
                  for r in rows_a]
        site_keys = set(_call_site_key({'file': r['file'], 'line': r['line'],
                                        'callee': r['symbol']})
                        for r in rows_a)
        checker.check(ca is True and ta == tb
                      and json.dumps(rows_a, sort_keys=True)
                      == json.dumps(rows_b, sort_keys=True)
                      and keys_a == sorted(keys_a)
                      and len(site_keys) == len(rows_a),
                      'B3(10) callers rows deterministic, total-ordered, '
                      'tuple-key deduped')
        # B3(11) impact 层内符号序 = 末级（符号名字典序）
        imp_lv = cmd_impact(facts, index, tc, False, 2, False)[3]['levels']
        checker.check(all(l['symbols'] == sorted(l['symbols'])
                          for l in imp_lv),
                      'B3(11) impact level symbols follow lexicographic order')
        # B3(12) 无上限子命令外壳：limit=0、truncated=false、total=保留数
        code, out = _quiet_main([prog, 'impact', tc, '--facts', facts_path,
                                 '--format', 'json'])
        sh12 = json.loads(out)
        imp_total = sum(len(l['symbols']) for l in sh12['results']['levels'])
        checker.check(code == 0 and sh12['limit'] == 0
                      and sh12['truncated'] is False
                      and sh12['total'] == imp_total,
                      'B3(12) uncapped subcommand shell: limit 0, not '
                      'truncated, total honest')

        # --- AC-56 注入必红：verified 边翻推断 + 删除目标符号 ---
        mutant = json.loads(dumps_facts(facts))
        mcall = None
        for c in mutant['calls']:
            if c['confidence'] == CONF_VERIFIED and c.get('caller') \
                    and c['candidates'] == 1:
                mcall = c
                break
        checker.check(mcall is not None,
                      'AC-56 fixture has an unambiguous verified edge to mutate')
        t_name = mcall['callee']
        u_name = _lastseg(mcall['caller'])
        mcall['confidence'] = CONF_INFERRED
        mutant['symbols'] = [s for s in mutant['symbols']
                             if _lastseg(s['qualname']) != t_name]
        mindex = build_query_index(mutant)
        m_imp_f, _m, _s, m_imp, _n, _mt4 = cmd_impact(mutant, mindex, t_name,
                                                      False, 2, False)
        checker.check(m_imp_f is False and m_imp['levels'] == [],
                      'AC-56(1) default impact does not traverse the flipped '
                      'edge')
        w_imp_f, _m, _s, w_imp, _n, _mt5 = cmd_impact(mutant, mindex, t_name,
                                                      False, 2, True)
        checker.check(w_imp_f is True
                      and u_name in w_imp['levels'][0]['symbols']
                      and w_imp['levels'][0]['confidences'][u_name]
                      == CONF_INFERRED,
                      'AC-56(1b) --include-inferred impact reaches the caller '
                      'with an inferred label')
        p56f, _m, _s, p56, p56notes, _pt4 = cmd_path(mutant, mindex,
                                                     mcall['caller'], t_name,
                                                     False, False)
        checker.check(p56f is False and p56['hops'] == []
                      and any('实锤' in n for n in p56notes),
                      'AC-56(2) default path reports found:false + hops:[] '
                      '+ note')
        p56bf, _m, _s, p56b, _n, _pt5 = cmd_path(mutant, mindex,
                                                 mcall['caller'],
                                                 t_name, False, True)
        checker.check(p56bf is True and p56b['hops']
                      and all('confidence' in h for h in p56b['hops'])
                      and any(h['confidence'] == CONF_INFERRED
                              for h in p56b['hops']),
                      'AC-56(3) --include-inferred path appears with '
                      'confidence labels (inferred hop present)')
        ctrl_f, _m, _s, _ctrl, _n, _pt6 = cmd_path(facts, index,
                                                   mcall['caller'],
                                                   t_name, False, False)
        checker.check(ctrl_f is True,
                      'AC-56 control: the same path exists on unmutated facts')
    finally:
        for _pd in probe_dirs:
            _rmtree(_pd)
        _rmtree(root)
        _rmtree(tmp)
    print('selftest: %d passed / %d failed' % (checker.passed, checker.failed))
    for label in checker.failures:
        print('  FAIL %s' % label)
    return 0 if checker.failed == 0 else 1

if __name__ == '__main__':
    sys.exit(run_selftest())
