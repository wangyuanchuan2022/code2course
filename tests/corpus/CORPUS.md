# tests/corpus · 真实代码语料

`analyze_structure.py` 的真实仓库测试语料。合成 fixture 覆盖语法分支，本语料覆盖
「真实工程结构」（多文件多目录、真实 import/调用关系、混合语言仓库噪声），替代每次
临时拼装 fixture。

## 使用方法

```bash
# 首次获取（或语料缺失时）：下载 + 解压 + 对每仓跑 analyze 冒烟
python tests/corpus/fetch_corpus.py

# 只处理部分语言 / 强制重下 / 只下载不冒烟
python tests/corpus/fetch_corpus.py --only python,go --force --skip-smoke
```

- 下载走本地代理 `http://127.0.0.1:7897`（codeload.github.com tarball），零依赖纯标准库。
- 幂等：目标目录 `tests/corpus/<lang>/<repo>-<ref>/` 已存在且非空即跳过；`--force` 重下。
- 单仓失败打印 `[WARN]` 继续下一个；全部失败才 exit 1；每仓失败重试上限 2 次。
- 冒烟：对解压目录跑 `analyze_structure.py analyze --outdir <tmp>`，断言 exit 0、
  facts JSON 可解析、symbols > 0；通过后清理临时产物。
- **语料本体不入 git**（.gitignore 排除 `tests/corpus/*`，本脚本与本清单豁免），
  任意机器执行上面一条命令即可一键还原。

### 常驻测试层：tests/test_corpus.py

fetch 内置的一次性冒烟仅作下载自检；常规回归以 `python tests/test_corpus.py` 为准：
对盘上 14 仓全量各跑 analyze 两次，断言 8 项/仓（exit 0、facts 可解析、schema/engine
版本钉值、symbols >= 5、主语言检出、files 语言闭集、**双跑 structure-facts.json
逐字节一致**）。零依赖直跑、全 ASCII 输出；语料缺失时响亮 skip 并提示 fetch 命令，
`--require-corpus` 把 skip 升级为 fail，`--only/--repo` 支持子集。基线：112 断言 /
约 16s（仓库根自动定位，脚本摆放位置无关）。

## 语料清单（2026-09-15 实测）

| 语言 | 仓库 | 钉 ref | 子目录 | 许可证 | 源码体积 | 文件数 | 冒烟 symbols | 选取理由 |
|---|---|---|---|---|---|---|---|---|
| python | pallets/click | 6.7 | click/ | BSD-3-Clause | 230KB | 17 | 460 | CLI 库标杆，包结构 + 多模块 import 关系典型 |
| javascript | expressjs/express | 4.0.0 | 全仓 | MIT | 252KB | 134 | 45 | Web 框架标杆；注意其 exports 赋值形态使符号数偏少（冒烟门只断 >0） |
| typescript | TypeStrong/ts-node | v9.1.1 | 全仓 | MIT | 110KB | 70 | 165（ts 87 / js 78） | TS 占主导且天然混 js，覆盖混合仓形态 |
| go | gin-gonic/gin | v1.1 | 全仓 | MIT | 224KB | 63 | 611（go 568） | Go Web 框架，方法集 + 包内调用密集 |
| rust | dtolnay/anyhow | 1.0.20 | 全仓 | MIT OR Apache-2.0 | 64KB | 18 | 162 | 小 crate、模块划分清晰，双许可宽松 |
| java | square/javapoet | javapoet-1.0.0 | 全仓 | Apache-2.0 | 170KB | 21 | 275 | 单包多类、接口/继承关系典型 |
| c | jqlang/jq | jq-1.4 | 全仓 | MIT（COPYING） | 270KB | 29 | 627（c 594） | 小型 C 工具，多 .c/.h 对应关系典型 |
| cpp | fmtlib/fmt | 3.0.2 | fmt/ | MIT | 166KB | 7 | 438（cpp 91 / c 347） | 只取 fmt/ 子目录避开 test/ 内 vendored gtest/gmock（约 2MB）；.h 被工具归 c 属已知口径 |
| csharp | Humanizr/Humanizer | v1.0.0 | src/Humanizer/ | Apache-2.0 | 113KB | 34 | 278 | 只取主工程子目录，排除测试与样例 |
| ruby | sinatra/sinatra | v1.2.0 | 全仓 | MIT | 185KB | 39 | 232 | DSL 风格 Ruby，全仓含测试（185KB 达标） |
| lua | leafo/lapis | v1.0.0 | 全仓 | MIT（README 内声明，无独立 LICENSE 文件） | 165KB | 48 | 833 | 纯 Lua Web 框架，模块多、点号命名空间多 |
| php | Seldaek/monolog | 1.10.0 | src/Monolog/ | MIT | 198KB | 71 | 456 | 只取 src/Monolog 主源码；PSR 风格类继承体系典型 |
| kotlin | mockito/mockito-kotlin | 2.0.0 | 全仓 | MIT | 94KB | 29 | 289 | 小而真实的 Kotlin DSL 库 |
| swift | Alamofire/Alamofire | 4.7.3 | Source/ | MIT | 297KB | 17 | 583 | 只取 Source/ 排除 Tests/Example；协议 + extension 密集 |

合计 14 门语言，全部冒烟通过（symbols > 0），全部许可证属 MIT/BSD/Apache 宽松系。

## 选取准则（新增/替换语料时遵循）

1. 许可证宽松：MIT / BSD / Apache-2.0 之一，且仓库内存在许可证文件（lapis 例外，
   MIT 声明在 README）。CORPUS.md 必须写明许可证与来源 URL。
2. 体积小：解压后该语言源码 < 300KB；超限则换仓、换更早 tag，或只保留子目录
   （CORPUS 表的「子目录」列）——宁小勿大。
3. 真实工程结构：多文件多目录、有真实 import/调用关系；单文件 demo 不合格。
4. 语言纯度：该语言源码占主导；天然混合仓（ts-node）在表中标注主/次符号数。
5. 钉 ref：钉具体 tag 或 commit，不追 main，保证可复现。

## 已知事项

- codeload 偶发 SSL 抖动（`UNEXPECTED_EOF_WHILE_READING`）：重试机制（上限 2 次）实测
  可自动恢复，无需人工干预。
- 下载配方受沙箱约束：不要用 PowerShell 5 的 Invoke-WebRequest（现代 TLS 握手失败）；
  脚本内使用 `urllib.request + ProxyHandler`。
- 冒烟临时产物写在 `tests/corpus/_smoke/`（同样被 .gitignore 排除），每次冒烟前重建、
  通过后删除。
