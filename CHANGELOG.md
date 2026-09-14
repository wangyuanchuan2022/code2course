# Changelog

本文件记录 code2course 技能包的版本变更（[Keep-a-Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式）。
版本号唯一事实来源：SKILL.md frontmatter `version`；resources 三件套头部 `@version` 与此同步。

## [1.13.0] — 2026-09-14

本版本把"结构事实"从调研落地为随技能分发的工具：新增 `analyze_structure.py`（零依赖单文件：16 门语言结构提取 + 项目地图查询层），并把查询能力作为可选辅助接入 workflow §3。

### Added

- **`analyze_structure.py` 结构事实底稿 + 项目地图查询**（技能根目录新文件）：analyze 产出底稿（文件清单/符号表/import 边/调用边/入口点五件套 + 断点清单 + 诚实性声明，schema_version=2，连跑两次字节一致）；查询层 7 子命令 `map` / `callers` / `callees` / `impact` / `path` / `entry` / `search`（统一 JSON 输出外壳，`impact`/`path` 缺省只走实锤边、`--include-inferred` 才纳且逐跳标注；无结果不是错误）
- **16 门 Tier-1 语言三引擎**：python 走 ast 确定性提取，其余 15 门走表驱动启发式（brace/end 双引擎）；token 模式校准自 Pygments 2.21.0（BSD-2-Clause）lexer，出处注记见脚本 docstring（https://pygments.org/docs/lexers/）
- **kind / 语言闭集契约**：符号类型、extractor、入口点 kind 等枚举闭集随 schema_version=2 冻结，只增不改名
- **MD 断点清单**：底稿新增「断点清单（Where the graph stops）」小节，逐条列出推断边及其调用点
- **自测 ≥60 断言**：`--selftest` 内联多语言 fixture 自证，当前 216 条（语言矩阵/查询层/确定性/边诚实性/负例含注入必红）
- **workflow §3 可选辅助段落**（只增不改）：底稿 + 查询用法，明确「可选的加速器，不是替代品——手工读码仍完全合法；底稿与源码冲突时以源码为准」
- **README 文件结构表**新增 `analyze_structure.py` 条目
- 示例课件重拼（随安装副本同步后执行，见发布检查项）

### 已知限制

- Python 3.8 地板为逼近口径：以 3.8 语法子集静态判定（禁用表 + 白名单机检），未在 3.8 解释器实测
- `--selftest` 需物化多语言 fixture，耗时为秒级
- 多语言启发式精度落差：brace/end 引擎为启发式，已知盲区逐语言列于底稿末尾诚实性声明

## [1.12.0] — 2026-09-14

本版本来自外部项目调研（colbymchenry/codegraph 借鉴分析，报告在仓库外 codegraph-analysis/）：把"结构事实的诚实性"从数字溯源扩展到调用链溯源。

### Added

- **调用边溯源与"推断"标注**（workflow §3a 新增两条 + quality-gates 陷阱 37/38 + 新验收项 + SKILL.md constraints）：跨文件调用边锚定「文件 + 行号」；凭命名/导入推测、未核实的调用关系显式标"推断"，禁止画成实锤
- **半流程禁令**（workflow §3a + quality-gates 陷阱 38）：流程链开讲必闭环到数据落点；静态追不到的环节（动态分派/回调注册/事件总线）如实讲断点断因，禁止只演前半段让读者脑补或硬编不存在的边
- **调用链走读设计基准**（interactive-elements §3 新增小节）：源码行即坐标系（禁力导向/随机布点）、边从调用行长出来（站点标注到行号粒度）、诚实边（线型=置信度）、长函数窗口化（&gt;80 行折叠为"调用点 ±4 行"窗口并注明省略位置）

## [1.11.2] — 2025-12-21

本版本来自第二轮评审（六角度审视成品课件 `example/course/`，报告在仓库外 review2/，交叉汇总见其 00 号文档）：17 条改进项全部落地。

### 工作流/机制（workflow.md）

- **§2.5 隐喻分配表加"喻体关键词"列**：查重单位改为喻体词而非概念（实证："身份证"×11 跨模板匹配与 MD5 记忆化两概念撞车）；同模块展开/结业回顾复述/data-why 回指为合法
- **§2.5 术语表扩展"领域资产语义"登记**：编码值/模板行/配置字段一行一义（实证：格子值 10 在两个模块得到互斥物理解释）
- **§8.0 拼接清单新增"承上启下"与"源快照"两列**：承接句/主线锚点落盘即填；源仓库 commit hash 留基线（实证：交付两天后源仓库演进，84 块中 38 块行号漂移）
- **§2.5 新增 2.5b 并行/分工生成的一致性对账**：三张表唯一事实源、组件变更回报、终检以成品反向重建三张表双向 diff——"数量核对"查不出"事实错误"（实证：steps 把取点画成格子中心，照做校准必失败）
- **档位核对前置**：达标列落盘即回填，交付前只复核（上一版已有文字无机制，本轮实证仍 6/13 模块返工）
- **§8 课程结构新增"结业收束段"**（独立导航项：主线回顾 + 跨模块综合题 + 行动指引；mN 引用逐一核对）；课程首页新增"规模与受众预期行"
- **§5 主线锚点**（流程族首模块 header 回连用户视角）与"设计取舍段 ≤6 句"豁免；§2 模块排序指引；§7 题干形态轮换 + data-why 长度/前向指引规则
- **§9 体积参考线按档位分层**：L1/L2 维持 350/500KB，L3 上调 550/700KB + 超线减重清单（实证：460KB 的 L3 单文件课不拆是对的，350KB 线失去预警价值）
- **§8.0 脚本组装工程约束**：外壳随任务快照固定（禁止读技能安装目录活动拷贝）、组装后 diff 校验、写盘换行符一致

### 机检增强（validate_course.py）

- **`--source <dir>`**：逐字一致强校验——解析 data-file 标注（含"路径 · L区间"与多源"与"连接），转义后文本必须命中源文件，且行号落点在标注区间容差内（实测立即抓出 38 块行号漂移）
- **`--tier L1|L2|L3`**：档位数量下限机检（阈值内置为唯一事实源；setProperty 注入变量视为已定义）
- **CSS 变量审计**：var() 引用未定义变量 → ERROR（实证：工人初稿 7 处未定义变量全靠人工抓回）；color/background/fill/stroke 裸 #FFFDF8/#FFFFFF → WARNING
- **溯源 id 存在性**：data-why 引用的 pair-* id 不存在 → ERROR（实证：pair-m8-route 死链曾靠人工勘误）
- **版本自证核对**：generator meta 缺失 WARNING（旧产物兼容）、与外壳 @version 不一致 ERROR
- 体积读数改 `newline=''` 按磁盘字节计（CRLF 不再折叠 1.5%）；脱敏正则扩为全盘符路径（`…` 截断豁免）；JSON 值内 HTML 实体字面 WARNING

### 规则文档（quality-gates / interactive-elements / design-system / SKILL.md）

- 隐喻口径全文统一为"喻体不跨概念复用"；陷阱 6 加设计取舍段豁免；陷阱 9 加"删掉测试"判定法；陷阱 21 加合计守恒校验；新增陷阱 35（同一资产两种物理解释）/36（补组件引入矛盾表述）
- 验收标准：role 检查范围扩至 `.flow-svg` 宿主；结业收束段 mN 映射核对；代码卫生项（孤儿类白名单/.tp-head 语义单一/内联 style ≤5）；体积分层口径；脱敏清单补全盘符路径行
- interactive-elements：§2/§3 模板宿主 SVG 修正为 `role="group"`（原模板会教出生成器写出无障碍退化版）；§10d 注明 JSON 字段纯文本禁实体；§11 沙盘兜底措辞修正 + 反例库；§1 类名分型标注 + data-why 长度
- design-system：动画属性分级成文（一次性入场允许布局属性，viz-bar 为显式例外）；新增 `.tag-row`/`.hero-meta`/`.course-footer` 小件
- SKILL.md：constraints 与设计哲学同步隐喻/体积新口径

### 外壳（resources，一次到位）

- course-template.html：generator 版本自证 meta、noscript 图表降级提示、hero 规模行占位、封面标签行改用 `.tag-row`（终结 .tp-head 挪用）、默认结业收束段、出品信息页脚
- base.css：`.tag-row` / `.hero-meta` / `.course-footer` 三个通用小件

## [1.11.1] — 2025-12-20

### 新增：纯 HTML 铁律（写入 HTML 的内容禁止一切 Markdown 语法）

- **动机**：智能体写入 HTML 时会混入 Markdown（代码围栏、行内反引号、`#` 标题等），产出非合法 HTML，浏览器无法正确解析
- **SKILL.md**：frontmatter constraints 与正文硬性约束各增一条——写入 HTML 的内容必须是纯 HTML；禁令清单（```/~~~ 围栏、行内反引号对、行首 # 标题、行首 -/* 列表、** 加粗、* 斜体、> 引用、[文字](地址) 链接、|---| 表格）；结构用对应 HTML 标签（h1–h6 / ul-ol-li / strong-em / blockquote / a / table），留说明用 `<!-- -->` 注释；完整文档以 `<!DOCTYPE html>` 开头，片段以合法标签开头结尾；其他输出场景的 Markdown 绝不带入写入的 HTML
- **workflow.md §4**：新增「纯 HTML 铁律」子节（禁令清单 / 正确写法 / pre·code·script·style 内逐字代码样例属数据不是标记的边界条款 / 判定方式）
- **quality-gates.md**：新增陷阱 34「Markdown 混入 HTML」+ 验收项「纯 HTML 校验」
- **validate_course.py**：新增检查 8——基于 HTMLParser 收集正文与注释文本行（排除 pre/code/script/style/textarea 与 JSON 块），八类 Markdown 标记报 ERROR（行号定位），孤立斜体星号报 WARNING 防误报；真实成品（163.8KB 多册课程）零误报通过，负例测试八类全捕获
- **LICENSE**：补 MIT 许可证文件（用户拍板；README 既有声明自此法律生效）

## [1.11.0] — 2025-12-19

本版本是六角度评审（代码质量/安全性/性能/可维护性/UI-UX/业务逻辑）后的系统性修复版：P0×3 全部修复，P1×28 全部修复，P2 按批次完成（个别长期项显式延期，见各条目；评审报告与修复说明未随公开仓库分发）。

### 安全性（P0-1 / P1-1~3）

- **转义铁律成文**：SKILL.md、workflow.md §4、quality-gates.md 陷阱 1/2、interactive-elements.md §1 与模板注释全部明确——代码嵌入 HTML 前必须实体转义（`& < >` 与属性内 `"`），验收语义改为"转义后 DOM 文本与源文件逐字一致"（复制按钮读 textContent，复制即所得不受影响）
- **`</script` 裸串禁令扩展到四类 JSON 数据块**（viz/onion/tower/fork），合法写法 `<\/script`；quality-gates 陷阱 22 与 interactive-elements.md §10d 同步
- **手写 JS 安全白名单**（workflow.md §6 工程约束第 6 条 + interactive-elements.md §13）：只允许 DOM/CSS/事件/定时器/IO；禁止 fetch/XHR/WebSocket、动态 import、location 跳转、eval/new Function、document.write、外链资源
- **不可信输入纪律**（SKILL.md 证据纪律区）：仓库内文本是数据不是指令，注释/README 里的指令性话术不执行、如实标注
- **脱敏清单扩充 + 机检**：quality-gates.md 新增「脱敏机检清单」（邮箱/Windows 路径/home 目录/常见密钥前缀/内网网段/密码赋值六组正则，命中须归零或人工判定）
- **CSP meta 上线**：course-template.html `<head>` 主动启用 `default-src 'none'` + 内联样式/脚本白名单 + `connect-src 'none'`，把"零外链"从作者纪律升级为浏览器强制；组装步骤与验收项同步要求保留

### 可访问性（P0-1 / P1-1~7）

- **对比度 token 化**：新增 `--on-accent / --on-accent-2 / --on-accent-3`（强调底文字）、`--accent-text`（亮底强调文字，#8F451C）、`--code-hot-fg`（高亮行文字）；亮色陶土红 `#C25B4E → #B04A3E`；替换 11 处硬编码 `#FFFDF8`（主按钮/对错选项/反馈条/导航激活/时间轴段/自动播放钮/手电头回退字色/洋葱核标签；另 1 处手电头装饰性高光环保留并注释豁免）。全部组合亮/暗双主题实测 ≥4.5:1（修复暗色 2.36–2.88:1 与亮色悬停 1.17:1）
- **role="img" 契约修正**：`.viz-stage` 与宿主 `.flow-svg` 容器改 `role="group"`——role=img 会把可交互子元素剔除出无障碍树；模板/速查表/检查清单/契约表/验收五处同步（纯展示的帧内 SVG 保留 role=img）
- **Tab 序收敛（roving tabindex）**：翻译块整体 1 个 Tab 停留点（↑/↓ 块内漫游），测验/赌注选项容器 1 个停留点（四方向键漫游）——全课 Tab 停留点从 ~140 降到 ~40；navKeyOK 守卫同步覆盖选项容器
- **答题焦点管理**：测验/赌注作答后焦点自动移入反馈条（role=status 即时播报），重试/再押一注后焦点回到第一个选项
- **探照灯 ARIA**：模板 aria-valuemin 0 与初值一致；引擎接管即 syncAria；Esc 熄灭并清空点亮
- **移动端 SVG 文字**：≤640px 时 flow 站点/标签字号放大（原 13px 经 viewBox 缩放后仅 ~6px）
- **触摸目标**：复制按钮 32→44px；沙盘滑块拇指 20→24px
- **验收可操作化**："达 WCAG AA" 改为三项可抽检动作（键盘走查/对比度抽查/375px 可读性），并注明 base.css 出厂已校准

### 性能（P1-1~5 / P2）

- **高频路径 rAF 化**：探照灯与沙盘令牌拖拽改为 rect 缓存 + requestAnimationFrame 合帧（消除逐 move 读布局+写样式的强制同步布局）；沙盘 aria-valuenow 整百分比节流
- **`content-visibility: auto`**：`.module` 声明 + `contain-intrinsic-size: auto 90vh`，大课件初始渲染成本从 O(全课) 降为 O(视口附近)
- **封面光晕去 blur**：删除 `filter: blur(18px)`，改多层收紧色标的 radial-gradient（视觉近似，纯绘制无滤镜重栅格化）
- **场景卡 hover 阴影合成化**：`--shadow-deep` 移入 `::after` 伪元素只过渡 opacity（box-shadow 450ms 逐帧重绘整卡含网格底纹的问题消除）
- **探照灯清扫增量化**：clearSpot 只清理记录在册的行/翻译块，不再逐站跑 3 次 document 级 querySelectorAll
- **体积护栏量化**：单册 >350KB 建议评估 §9 拆分、>500KB 红线；SKILL.md constraints、workflow.md §9、quality-gates 验收/陷阱三处同步
- `.tp-note`/`.vol-hint` 的 `transition: all` 改显式属性；`.t-h2` 650→600

### 代码质量（P1-1~4 / P2）

- **状态类作用域化**：赌注揭晓行改用 `.is-spot-bet`、翻译块标 `.is-betted`（base.css 同款绿色样式）——探照灯 clearSpot 不再误灭赌注答案；workflow.md §8 新增**状态类名契约一览表**与**无样式语义钩子**清单
- **洋葱层数上限校验**：>6 层走 ctrlError 错误卡（原会静默渲染 "undefined 第 7 层"）
- **两代引擎辅助函数合并**：vizEl/ctrlEl/vizParseData/ctrlParse 成为共享实现 c2cEl/c2cParse 的别名，reduceMotion()/lazyStage() 提炼——约 50 行重复消除，调用点零改动
- **赌注支持"↻ 再押一注"**（与测验重试对齐：押错也能重开的预测-验证练习）
- **栈塔弹空恢复空栈提示**；resetTower 防重复；flow data-step 与 DOM 序不一致时 console.warn；IO 兜底注释改为诚实版本；复制按钮去掉覆盖文本的 aria-label（文本自朗读）
- **README 文件树补全**（references 7 文件 + example/ + CHANGELOG/validate），app.js 职责描述与加载表对齐实物

### 业务逻辑 / 流程（P0-1 / P1-1~5 / P2）

- **档位冲突裁决规则**（workflow.md §0 规则 5）：通用内容下限与档位参数表冲突时以参数表为准；零依赖/逐字/隐喻唯一/可溯源等完整性约束不接受档位豁免——消除 SKILL.md"≥2 交互"与 L1 参数表"1 种交互"打架且无优先级的矛盾
- **隐式触发判据化**：三条可观察判据（具体代码库 + 讲解式期望 + 范围大于单函数）替代"教学价值明显"的循环论证；examples.md 示例 4 补正反判例
- **大纲轻确认**（workflow.md §2）：L2/L3 动工前把模块清单发用户过目（非阻塞），方向性返工前移
- **修订协议**（workflow.md §10 新增）：交付后修改按 A/B/C/D 四类走对应动作 + 六项全局不变量复跑清单
- **档位核对双层化**：拼接清单新增"档位达标"列逐段核对 + 交付前总复核（实证：只做交付前核对导致 6/9 模块返工）
- **http:// 豁免澄清**：SVG 命名空间字符串不算资源引用；"50% 视觉"改可抽检口径（纯文字块不连续超 2 个）
- 选档快速通道（档位词+开始指令同现时复述即开跑）、切档重写代价确认（≥3 段先报价）、audience.md 角色→档位建议表（建议不代选）、零隐喻合法、脚本化组装可选条款

### 可维护性（P1-1~4 / P2）

- **CHANGELOG.md 建立**（本文件）+ SKILL.md/resources 三件套 `@version 1.11.0` 单一来源标记
- **acceptance 数字解耦**：SKILL.md 与 references/README.md 不再写死"陷阱 30 条/验收 25 条"（实际 33 条/29 条），以 quality-gates.md 为准
- **validate_course.py**（新增）：零依赖成品机械校验——{{ 残留 / 外部资源引用（xmlns 豁免）/ 四类 JSON 可解析且无裸 `</script` / data-i 配对等长 / data-correct 与 data-bet-correct 恰好一个 / 模块锚点一一对应 / `--mask` 脱敏正则扫描
- **发布检查项成文**（README.md）：修三件套 → 重新生成 example → validate 全绿 → grep 无残留 → CHANGELOG 同步
- design-system.md 标明"快照"性质并同步 v1.11 token；暗色块补 `:not([data-theme="light"])` 守卫说明；主题切换机制描述修正为显式双态
- interactive-elements.md 头注声明式引擎清单补 §10；§13 补四条运行时纪律；SKILL.md 参与式控件改"名称(§N)"成对书写（修复 §11/§12 错位）；examples.md 示例 1 补第 0 步选档、示例 4/6 更新

### 明确延期（未做，附理由）

- **E3 机器可读参数渲染管线**（业务逻辑 P2 长期项）：把档位参数表做成 JSON/CSV 供渲染管线消费——收益集中在"未来多前端"，当前唯一消费者是 AI 执行者本身，引入双格式反而增加漂移面；待出现第二个消费者再上
- **interactive-elements.md 物理拆分**（可维护性 P2-7 二选一）：采用方案②（速查表引导分段读取 + 头注明示 §10–§12 声明式），不拆文件——避免 10+ 文件的交叉引用重写
- **事件委托改造**（性能 P2-5）：bars/timeline 逐行监听在契约规模（3–8 条）下无感知收益，仅补引擎软上限告警由 quality-gates 陷阱 33 承接

## [1.10.0] — 2025（历史版本，未发布 changelog）

- 全部可交互控件加"适量 3D 触感"：凸起面 + 悬停抬升 + 按压内凹（`--depth-hi/--depth-lo/--bevel/--press` token，纯 CSS 零依赖，颜色随主题派生）
- 课程外壳统一升级：按钮/选项/卡片/滑块获得实体按键立体感

## [1.9.0] — 2025（历史版本，未发布 changelog）

- 移除 5 个低参与度控件：卡片 3D 悬停倾斜（.tilt）、架构图悬停、术语气泡、donut 占比环、群聊动画
- 新增 5 个参与式控件引擎：执行探照灯（§7）/ 洋葱剥层（§8）/ 因果赌注（§9）/ 栈塔（§10）/ 分叉沙盘（§11）

## [1.0.0] — 2025

- 首个版本：单文件零依赖课程生成、翻译块对照、数据流动画、测验、进度导航、多文件拆分
