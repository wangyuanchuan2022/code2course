# design-system.md — code2course 课程设计系统

本文件仅供理解设计理念与变量含义，**不进入成品**。课程的全部样式以 `resources/base.css` 为唯一来源（原样复制进 `<style>`）；微调强调色时参考这里的变量语义即可，布局骨架、间距、字体层级不得推翻。

## 设计基调

**"温暖的工作台"**：像一间木质书桌上的手工笔记本，而不是冷冰冰的 IDE 或 AI 生成的紫色渐变页。

- 主色调：暖奶油底 + 深炭棕文字 + 蜜橘/陶土强调色
- 字体：系统字体栈（零依赖，无网络字体）
- 质感：圆角大、阴影软、留白足、细虚线分隔（像笔记本格线）

## 1. CSS 变量

> 📌 本节是 `resources/base.css` §1 的**快照**（v1.11.0），仅供理解变量语义；
> 两处如有出入，**一律以 base.css 为准**。本文件不进入成品。

```css
:root {
  /* 颜色 —— 亮色模式（默认） */
  --bg:            #FAF6EF;   /* 暖奶油底 */
  --bg-card:       #FFFDF8;   /* 卡片面 */
  --bg-code:       #2D2A26;   /* 代码块深底（亮色模式下代码仍用深底） */
  --bg-sidebar:    #F3EDE2;   /* 侧边栏底 */
  --text:          #33302B;   /* 正文深炭棕 */
  --text-muted:    #7A7367;   /* 次要文字 */
  --accent:        #E07A3F;   /* 蜜橘 —— 主强调：当前模块、高亮、进度 */
  --accent-soft:   #F5D5BC;   /* 蜜橘浅底 —— 悬停高亮背景 */
  --accent-2:      #4E7A6A;   /* 松绿 —— 次强调：正确答案、"数据"相关 */
  --accent-3:      #B04A3E;   /* 陶土红 —— 错误答案、警告（v1.11 由 #C25B4E 加深至白字 4.5:1+） */
  --border:        #E5DCCB;   /* 边框/分隔线 */
  --grid-line:     #E9E1D2;   /* 笔记本格线（细虚线） */
  --code-fg:       #EDE6D9;   /* 代码块前景（配 --bg-code 深底，两种模式都浅字） */

  /* 强调底上的文字（v1.11 对比度 token，亮/暗各取所需值，实测 ≥4.5:1） */
  --on-accent:     #2A2723;   /* 蜜橘底上的深炭字（4.9:1） */
  --on-accent-2:   #FFFDF8;   /* 松绿底上的奶白字（5.1:1） */
  --on-accent-3:   #FFFDF8;   /* 陶土红底上的奶白字（5.4:1） */
  --accent-text:   #8F451C;   /* 亮底上的"文字版强调色"（卡片 6.8:1）——小号文字禁用裸 --accent */
  --code-hot-fg:   #33302B;   /* is-hot 行点亮后的文字（浅橘底上 7:1） */

  /* 暗色模式（见第 5 节） */

  /* 间距 —— 8 的倍数体系 */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 16px;
  --space-4: 24px;
  --space-5: 32px;
  --space-6: 48px;
  --space-7: 64px;

  /* 圆角 */
  --radius-s: 6px;
  --radius-m: 12px;
  --radius-l: 20px;
  --radius-pill: 999px;

  /* 阴影 */
  --shadow-soft: 0 2px 8px rgba(60, 50, 35, 0.08);
  --shadow-lift: 0 8px 24px rgba(60, 50, 35, 0.14);
  --shadow-deep: 0 24px 60px -18px rgba(60, 50, 35, 0.30);   /* 悬浮深影：场景卡 hover、沙盘令牌拖动 */

  /* 3D 触感深度（v1.10）：可交互控件的"实体按键"立体感，自动适配亮/暗主题 */
  --depth-hi: color-mix(in srgb, var(--bg-card) 78%, #FFFFFF);   /* 顶高光 */
  --depth-lo: color-mix(in srgb, var(--bg-card) 86%, #2D2A26);   /* 底压暗 */
  --bevel: inset 0 1px 0 var(--depth-hi), inset 0 -2px 0 var(--depth-lo);
  --press: inset 0 2px 6px rgba(0, 0, 0, 0.20), inset 0 1px 0 rgba(0, 0, 0, 0.05);

  /* 字体 */
  --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
               "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas,
               "Cupertino Mono", monospace;

  /* 动效 */
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  --ease-spring: cubic-bezier(0.34, 1.45, 0.64, 1);
  --dur-fast: 0.18s;
  --dur-mid: 0.45s;
  --dur-slow: 0.8s;
}

/* 暗色模式：base.css 实际选择器是 :root:not([data-theme="light"])（跟随系统，
   但手动选了亮色则豁免）+ [data-theme="dark"]（手动选暗色，显式双态）两个块，
   各写一份相同的变量覆盖——此处快照只示意变量值 */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg:          #2A2723;
    --bg-card:     #34302B;
    --bg-sidebar:  #26231F;
    --text:        #EDE6D9;
    --text-muted:  #A89F8E;
    --accent:      #E8935B;
    --accent-soft: #4A3A2C;
    --accent-2:    #7BAE9A;
    --accent-3:    #D97E72;
    --border:      #453F36;
    --grid-line:   #3E382F;
    /* v1.11：暗色下强调底普遍变浅，三个 on-accent 统一换深炭字（4.9–5.8:1）；
       accent-text/code-hot-fg 反转为浅字 */
    --on-accent:   #2A2723;
    --on-accent-2: #2A2723;
    --on-accent-3: #2A2723;
    --accent-text: #E8935B;
    --code-hot-fg: #FFE8D6;
    --shadow-soft: 0 2px 8px rgba(0,0,0,0.30);
    --shadow-lift: 0 8px 24px rgba(0,0,0,0.42);
    --shadow-deep: 0 24px 60px -18px rgba(0,0,0,0.60);
  }
}
```

## 2. 排版层级

| 层级 | 类名 | 规格 |
|---|---|---|
| 页面主标题（封面） | `.t-hero` | `clamp(2.2rem, 5vw, 3.4rem)`，700，`--text` |
| 模块标题 | `.t-h1` | `1.8rem`，700，左侧 8px 橘色竖条装饰 |
| 小节标题 | `.t-h2` | `1.25rem`，600 |
| 卡片标题 | `.t-h3` | `1rem`，600，`--text` |
| 正文 | `.t-body` | `1rem / 1.7`，最多 2–3 句一段 |
| 辅助说明 | `.t-muted` | `0.875rem`，`--text-muted` |
| 代码 | `.t-code` | `0.85rem`，`--font-mono`，行高 1.6 |
| 标签/徽章 | `.t-tag` | `0.75rem`，大写间距 0.05em，pill 底 |

```css
.t-hero { font-size: clamp(2.2rem, 5vw, 3.4rem); font-weight: 700; }
.t-h1 {
  font-size: 1.8rem; font-weight: 700;
  padding-left: var(--space-3);
  border-left: 8px solid var(--accent);
}
.t-h2   { font-size: 1.25rem; font-weight: 600; margin-top: var(--space-5); }
.t-h3   { font-size: 1rem; font-weight: 600; }
.t-body { font-size: 1rem; line-height: 1.7; max-width: 62ch; }
.t-muted{ font-size: 0.875rem; color: var(--text-muted); }
.t-code { font-family: var(--font-mono); font-size: 0.85rem; line-height: 1.6; }
.t-tag {
  font-size: 0.75rem; letter-spacing: 0.05em; text-transform: uppercase;
  padding: 2px 10px; border-radius: var(--radius-pill);
  background: var(--accent-soft); color: var(--text);
}
```

## 3. 颜色语义（全局统一，不得混用）

| 用途 | 颜色 |
|---|---|
| 当前模块、进度、悬停同步高亮 | `--accent`（蜜橘）+ `--accent-soft` 底 |
| 正确答案、成功反馈、"数据"角色 | `--accent-2`（松绿） |
| 错误答案、危险、警告 | `--accent-3`（陶土红） |
| **强调底上的文字**（按钮、对错反馈、导航激活项、时间轴段） | `--on-accent` / `--on-accent-2` / `--on-accent-3`（v1.11：按底色配对，勿再写裸白字） |
| **亮底上的强调文字**（链接式按钮、悬停复制按钮） | `--accent-text`（v1.11：小号文字禁用裸 `--accent`，亮底上只有 2.9:1） |
| 代码块背景 | 恒用 `--bg-code` 深底（两种模式下都深底，代码永远像"终端窗口"）；前景 `--code-fg`，点亮行 `--code-hot-fg` |
| 参与式控件的"当前位置/命中" | 探照灯站点与被点亮 `.tp-line.is-spot` 用 `--accent-2` 系（绿=数据在此）；赌注揭晓行 `.is-spot-bet` 同款绿但独立类（v1.11）；探照灯手电与聚焦描边用 `--accent-3`（醒目）；洋葱层由外向内从 `--bg-sidebar` 渐进到 `--accent-soft` 再到 `--accent` 混色、核用 `--bg-code`；栈塔帧左边条 depth 1 用 `--accent`、更深层用 `--accent-2`；沙盘命中滑道/结果卡用 `--accent`、命中芯片用 `--accent-2` |

## 4. 响应式布局规则

- **断点**：`960px`（桌面 → 平板）、`640px`（平板 → 手机）
- **桌面（>960px）**：左侧固定 260px 侧边导航（模块列表 + 进度），右侧内容列最大 `880px` 居中
- **≤960px**：侧边栏折叠为顶部横向进度条（模块圆点），内容列全宽
- **≤640px**：代码翻译块从左右并排改为上下堆叠（代码在上、解释在下，仍保留悬停联动）；字号降一档（`.t-body` → `0.9375rem`）
- 所有交互目标最小点击区 44×44px（手指友好）
- 动画元素容器加 `min-width: 0` 防溢出；SVG 一律 `viewBox` + `width:100%` 自适应

```css
.layout { display: flex; min-height: 100vh; }
.sidebar {
  width: 260px; flex-shrink: 0; position: sticky; top: 0;
  height: 100vh; overflow-y: auto;
  background: var(--bg-sidebar); border-right: 1px solid var(--border);
}
.content { flex: 1; max-width: 880px; margin: 0 auto; padding: var(--space-6) var(--space-4); }
@media (max-width: 960px) {
  .layout { flex-direction: column; }
  .sidebar { width: 100%; height: auto; position: static; }
}
```

## 5. 暗色 / 亮色模式

主题切换机制由 `resources/app.js` 与 `resources/base.css` 内建（v1.11 快照，细节以源码为准）：

- 跟随系统：`@media (prefers-color-scheme: dark)` 覆盖变量，选择器带 `:not([data-theme="light"])` 守卫——手动选了亮色的用户即使系统是暗色也保持亮色
- 课程右上角提供手动切换按钮 🌙/☀️（纯 emoji 图标，零依赖）。切换是**显式双态**：`<html data-theme>` 一律写明 `'dark'` 或 `'light'`（不是"加/去 dark 类"的单态翻转），支持"系统暗 + 手动亮"组合；选择持久化到 `localStorage`（key `c2c-theme`），刷新后由 app.js 起始段恢复
- 代码块在两种模式下都保持深底，只微调前景 token 颜色

```css
[data-theme="dark"] { /* 与 prefers-color-scheme: dark 相同的一组变量（显式手动态） */ }
```

## 6. 可复用布局骨架

### 6.1 课程整体骨架

```html
<body>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">📦 code2course</div>
      <nav class="module-nav"> <!-- 模块列表，当前项 .is-active --> </nav>
      <div class="progress-track"> <!-- 进度条 --> </div>
    </aside>
    <main class="content">
      <section class="module" id="m0">…</section>
      <section class="module" id="m1">…</section>
      <!-- … -->
    </main>
  </div>
</body>
```

### 6.2 单个模块（module）内部结构约定

```html
<section class="module" id="m1">
  <header>               <!-- 模块标题 + 一句话导语（≤2 句） -->
  <div class="scene">    <!-- 主视觉：动画/图表，占该屏 ≥50% -->
  <div class="translate-pair">  <!-- 代码 ↔ 大白话对照块 -->
  <div class="quiz">     <!-- 本模块的应用型测验 -->
</section>
```

### 6.3 场景卡（scene）—— 一切视觉元素的容器

```css
.scene {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-l);
  box-shadow: var(--shadow-soft);
  padding: var(--space-4);
  margin: var(--space-4) 0;
  background-image: repeating-linear-gradient(
    transparent 0 31px, var(--grid-line) 31px 32px);  /* 笔记本格线质感 */
}
```

### 6.4 模块间距与滚动锚点

```css
.module { min-height: 90vh; padding: var(--space-6) 0; scroll-margin-top: var(--space-4); }
.module + .module { border-top: 2px dashed var(--border); }
.module.is-active .t-h1 { color: var(--accent); }  /* 当前模块标题强调 */
```

## 7. 图标规范（零依赖）

- 一律使用 Unicode emoji（📦 🔍 🗄️ 🔐 🛒 💬 →）或内联 SVG
- 禁止引用任何图标库 CDN 或 base64 大图
- emoji 在节点/按钮中统一 `font-size: 1.1em`，起"快速识别"作用，不堆砌

## 8. 项目数据可视化配色约定（data-viz 组件，base.css §13）

课程特有图表（`.viz-scene` 引擎渲染）沿用第 3 节的语义色，不引入新色：

| 元素 | 颜色 | 说明 |
|---|---|---|
| 条形图主条 / 时间轴奇数段 | `--accent`（蜜橘） | "主数据"语义 |
| 选中栏、时间轴偶数段 | `--accent-2`（松绿） | "数据/正确"语义，交替与选中态 |
| 选中描边 / 数据错误提示 | `--accent-3`（陶土红） | 醒目但不整块铺红 |
| 条形轨道、时间轴底 | `--bg-sidebar` | 弱化背景 |
| 数值、时间刻度 | `--text-muted` + `--font-mono` | 数据标签一律等宽字体 |
| 详情行（解读 + 出处） | `--accent-soft` 底 + `--text` | 与悬停高亮同族 |

约定：

- 同一张图里同一语义只用一种颜色；条/段交替配色仅用于"区分相邻项"，不承载语义
- 图表数字与出处（anchor）放在详情行，不用图例复述
- 步骤回放（steps）的控制按钮复用表单按钮样式（`--bg-card`/`--border`，激活态 `--accent-2`），点击区 ≥44px

## 9. 动效与封面景深（零依赖，克制原则）

全部用 CSS 过渡/动画 + 少量指针/键盘事件实现，**不引入任何依赖、不引入新颜色**（阴影与强调色全部复用既有变量）：

- **封面景深**：`.hero-stage` 内放 `.hero-glow`（暖色光晕跟随指针，更新 `--mx/--my`）+ 开场渐入 `c2c-hero-rise`（纯 CSS，无 JS 也退化为静态光晕）。
- **参与式控件动效**：探照灯拖动/吸附、洋葱剥层飞散（`scale(1.16)` + 淡出）与碎屑掉落、栈塔压帧弹簧入场/弹帧淡出、沙盘令牌拖拽与滑入——全部是"状态变化的反馈"，不是装饰。
- **代码块终端质感**：`.tp-code` 内顶高光 + 深阴影 + 细描边。
- **主按钮按压反馈**：`:active` 时轻微下沉 + 缩放。
- **可交互控件的 3D 触感（v1.10）**：全部按钮/选项/卡片/滑块的"凸起面 + 悬停抬升 + 按压内凹"由 base.css 统一实现，复用第 1 节的 `--depth-hi/--depth-lo/--bevel/--press` token（纯 CSS、零依赖、颜色随主题自动派生）。这是"实体按键"的立体触感，**不是**已移除的卡片指针倾斜（.tilt）。

纪律（与 UX 指南一致）：每屏最多动 1–2 个关键元素；动效只做状态反馈、不承载关键信息（关键信息同时用颜色/文字双编码）；所有动效尊重 `prefers-reduced-motion`（base.css 全局覆盖 + app.js 关键处主动判断）。（v1.9 起卡片 3D 悬停倾斜控件已移除；v1.10 起交互控件改为"触感 3D"——只做凸起/按压的深度反馈，不做指针跟随倾斜。）
