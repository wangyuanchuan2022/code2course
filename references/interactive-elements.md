# interactive-elements.md — code2course 可复用交互组件模板

组装课程 HTML 时，直接复制各节的 **HTML 模板**到最终文件，替换 `{{占位符}}` 内容。**类名与结构保持稳定，不得推翻重新发明**。所有模板假定已内联 `resources/base.css` 与 `resources/app.js`。

> ⚠️ §1/§2/§5/§7 各节附带的 CSS/JS 代码块**仅供理解组件原理，禁止粘贴进成品**——它们已内置于 `resources/base.css` 与 `resources/app.js`（含懒播放与防重复初始化）。照抄这里的旧版 JS 会导致双重绑定、动画失去"滚入才播"行为。§3–§6、§10–§12 的控件为**声明式引擎组件**：只写 HTML + JSON 数据，渲染与交互全部由 app.js 自动完成，不写任何 JS。

零依赖铁律：所有模板只用原生 HTML + CSS + 原生 JS + 内联 SVG，禁止任何外部资源。

> 🎬 外壳已内建封面景深：`.hero-stage` 的开场渐入与 `.hero-glow` 指针光晕由 `resources/app.js` §1.5 与 `base.css` §14 在"精细指针 + 非减少动效"设备上自动启用。课程作者只需按 course-template.html 使用 `.hero-stage`/`.hero-glow` 结构，**禁止手写光晕/渐入代码**。（v1.9 起卡片 3D 悬停倾斜控件已移除，不得恢复；v1.10 起全部可交互控件的"适量 3D 触感"——凸起面/悬停抬升/按压内凹——已内建于 `base.css`，纯 CSS、零依赖，课程作者无需手写。）

---

## 1. 代码 ↔ 大白话对照翻译块

左侧真实代码（逐字复制），右侧逐段解释。**悬停任一侧，对应另一侧同步高亮**。

```html
<div class="translate-pair" data-file="src/api/orders.js · L42-L58">
  <div class="tp-head">
    <span class="t-tag">📄 真实代码</span>
    <span class="t-muted tp-file">{{文件路径 · 行号}}</span>
  </div>
  <div class="tp-body">
    <div class="tp-code t-code">
      <!-- ⚠️ 代码逐字复制，但嵌入前必须做 HTML 实体转义：& → &amp;、< → &lt;、> → &gt;
           （转义不是改写——渲染后的 DOM 文本与源文件逐字一致，见 workflow.md §4 转义铁律） -->
      <pre class="tp-line" data-i="0"><code>{{原始代码第 1 段，逐字（已转义）}}</code></pre>
      <pre class="tp-line" data-i="1"><code>{{原始代码第 2 段，逐字（已转义）}}</code></pre>
      <!-- 每段代码一个 .tp-line，data-i 与右侧解释配对 -->
    </div>
    <div class="tp-plain">
      <div class="tp-note t-body" data-i="0">{{第 1 段的大白话解释，1–2 句}}</div>
      <div class="tp-note t-body" data-i="1">{{第 2 段的大白话解释，1–2 句}}</div>
    </div>
  </div>
</div>
```

要点：

- 悬停/聚焦 `data-i` 相同的两侧同时点亮（`.is-hot`，橙色）；探照灯（§3）给 `.tp-line` 加 `.is-spot`（绿色行级点亮）、因果赌注（§6）揭晓加 `.is-spot-bet`（同为绿色但独立存在，探照灯清不掉它），三者颜色语义不同、可共存。
- 需要被探照灯/赌注点亮的翻译块必须带 `id`（如 `id="pair-m2-chain"`），供 `data-sp-pair` / `data-bet-pair` 引用。
- 「复制代码」按钮由 app.js 自动注入到 `.tp-head` 末尾，模板里无需书写。`.tp-head` 仅限在 `.translate-pair` 内使用（翻译块头），封面/模块头的标签行不要挪用它——用 `.t-tag` 直排或自定义容器，避免审计脚本误计翻译块。
- **模板类名分两类**：样式类（base.css 有规则，动了就变样）与结构钩子（workflow.md §8「无样式语义钩子」清单：`.tp-plain`、`.quiz-q`、`.bet-opts`、`*-title` 等——无样式，仅供选择器/审计，可改名）。写模板时对号入座，别把钩子当样式依赖。
- **全部 `data-*` 属性值（含 `data-why`/`data-bet-why`/`data-sp-file`）是纯文本**：运行时经 textContent 渲染，不要在属性值里写 HTML 标签；含 `"` 时写作 `&quot;`。同理，`data-why` 建议长度 ≤3 句——超长拆成"结论 + 指路"（结论给为什么错/对，指路给"去看哪个模块哪块"）。

<details>
<summary>组件原理（仅供理解，禁止粘贴进成品）</summary>

```css
.translate-pair { margin: var(--space-4) 0; }
.tp-body { display: grid; grid-template-columns: 1.1fr 1fr; gap: var(--space-3); }
.tp-line { margin: 0 0 var(--space-2); position: relative; padding-left: 2.4em; }
.tp-line::before {  /* 编辑器式行号槽（CSS counter，不进入复制文本） */
  counter-increment: tp-line; content: counter(tp-line);
  position: absolute; left: 0; width: 1.6em; text-align: right;
  color: color-mix(in srgb, var(--code-fg) 40%, transparent);
  font-size: 0.78em; user-select: none;
}
.tp-line.is-hot, .tp-note.is-hot {
  background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent);
}
```

```js
document.querySelectorAll('.translate-pair').forEach(pair => {
  pair.querySelectorAll('[data-i]').forEach(el => {
    el.addEventListener('mouseenter', () => {
      const i = el.dataset.i;
      pair.querySelectorAll(`[data-i="${i}"]`).forEach(x => x.classList.add('is-hot'));
    });
    el.addEventListener('mouseleave', () =>
      pair.querySelectorAll('.is-hot').forEach(x => x.classList.remove('is-hot')));
  });
});
```
</details>

---

## 2. 数据流动画（SVG）

一个"能量点"沿路径流动，途经站点依次点亮，展示数据逐步变形。

```html
<div class="flow-scene scene">
  <svg class="flow-svg" viewBox="0 0 720 140" width="100%" role="group"
       aria-label="{{流程名，如：一次点击从按钮到数据库的旅程}}">
    <!-- 3–5 个站点：节点圆 + 名称 -->
    <g class="flow-node" data-step="0"><circle cx="60"  cy="70" r="26"/>
      <text x="60"  y="112" text-anchor="middle">🖱️ 点击</text></g>
    <g class="flow-node" data-step="1"><circle cx="280" cy="70" r="26"/>
      <text x="280" y="112" text-anchor="middle">⚙️ {{处理器}}</text></g>
    <g class="flow-node" data-step="2"><circle cx="520" cy="70" r="26"/>
      <text x="520" y="112" text-anchor="middle">🗄️ {{落点}}</text></g>
    <!-- 连接线 -->
    <path class="flow-path" d="M86,70 L254,70"/>
    <path class="flow-path" d="M306,70 L494,70"/>
    <!-- 流动能量点 -->
    <circle class="flow-dot" r="7"/>
    <!-- 节点下方数据形态标签 -->
    <text class="flow-label" data-step="0" x="60"  y="24" text-anchor="middle">{{点击事件}}</text>
    <text class="flow-label" data-step="1" x="280" y="24" text-anchor="middle">{{变形后}}</text>
    <text class="flow-label" data-step="2" x="520" y="24" text-anchor="middle">{{最终形态}}</text>
  </svg>
  <div class="flow-caption t-muted">▶ 点击任意站点或让动画自动播放，看数据如何一步步变形</div>
</div>
```

要点：站点 3–5 个；Tab 可聚焦站点、Enter/Space 跳步（app.js 内建）；动画滚入视口才播。要在同一条流程上叠加"跨文件代码走读"，给场景加 `.spotlight` 类并配探照灯（见 §3）。

<details>
<summary>组件原理（仅供理解，禁止粘贴进成品）</summary>

```css
.flow-svg .flow-node circle {
  fill: var(--bg-card); stroke: var(--accent); stroke-width: 2;
  transition: fill var(--dur-mid) var(--ease-out); cursor: pointer;
}
.flow-svg .flow-node.is-on circle { fill: var(--accent); }
.flow-svg .flow-path { stroke: var(--border); stroke-width: 2; stroke-dasharray: 6 6; fill: none; }
.flow-svg .flow-path.is-on { stroke: var(--accent); stroke-dasharray: none; }
```

```js
/* 能量点循环：step 从 0 递增取模，paint() 把 ≤step 的节点/连线/标签点亮 */
```
</details>

---

## 3. 执行探照灯 —— 跨文件同步走读（Cross-file Spotlight）

**部署位置**：第 3a 步"事件链追踪"类内容——一条调用链穿过多个文件（如 `controller.js → service.js → db.js`）时，让"谁调用了谁"变成可亲手扫描的代码路径。

机制：在数据流动画（§2）的流程图里**拖动探照灯**🔦，探照灯扫过哪个站点，多个 `.translate-pair` 里的对应代码行**同时点亮**——即使这些行分布在不同文件/不同翻译块里。等于一个不会报错的调试器逐步执行：把"流程位置"映射到"真实代码位置"。

与 §2 的关系：探照灯是 `.flow-scene` 的**叠加层**（站点能量点动画照常跑），范式完全不同——§2 是"看既定路径的自动播放"，探照灯是"学习者亲手拖动、跨文件行级同步点亮"。

```html
<!-- ① 流程图宿主：普通 flow-scene 加 .spotlight 类，结构再包一层 .spot-wrap -->
<div class="flow-scene scene spotlight">
  <div class="spot-wrap">
    <svg class="flow-svg" viewBox="0 0 720 140" width="100%" role="group"
         aria-label="{{流程名}}（可拖动探照灯跨文件走读）">
      <!-- 站点映射表：data-sp-pair = 目标翻译块 id（逗号分隔可多个）
           data-sp-line = 与之一一对应的 .tp-line[data-i]（逗号分隔）
           data-sp-file = 字幕里展示的文件·行号说明 -->
      <g class="flow-node" data-step="0"
         data-sp-pair="pair-ctl" data-sp-line="1" data-sp-file="controller.js · L18-L24">
        <circle cx="60" cy="70" r="26"/>
        <text x="60" y="112" text-anchor="middle">🖱️ {{站点}}</text></g>
      <g class="flow-node" data-step="1"
         data-sp-pair="pair-ctl,pair-svc" data-sp-line="2,0"
         data-sp-file="controller.js · L30 / service.js · L8">
        <circle cx="225" cy="70" r="26"/>
        <text x="225" y="112" text-anchor="middle">⚙️ {{站点}}</text></g>
      <g class="flow-node" data-step="2"
         data-sp-pair="pair-db" data-sp-line="0" data-sp-file="db.js · L5-L12">
        <circle cx="390" cy="70" r="26"/>
        <text x="390" y="112" text-anchor="middle">🗄️ {{站点}}</text></g>
      <path class="flow-path" d="M86,70 L199,70"/>
      <path class="flow-path" d="M251,70 L364,70"/>
      <circle class="flow-dot" r="7"/>
      <text class="flow-label" data-step="0" x="60" y="24" text-anchor="middle">{{数据形态}}</text>
      <text class="flow-label" data-step="1" x="225" y="24" text-anchor="middle">{{变形后}}</text>
      <text class="flow-label" data-step="2" x="390" y="24" text-anchor="middle">{{落点形态}}</text>
    </svg>
    <!-- ② 探照灯手电筒（可拖动 / 聚焦后 ←/→ 逐站移动） -->
    <button class="spot-lamp" type="button" role="slider"
            aria-label="执行探照灯：用左右方向键逐站移动，点亮对应文件里的真实代码行"
            aria-orientation="horizontal" aria-valuemin="0" aria-valuemax="{{站点数}}"
            aria-valuenow="0" aria-valuetext="未点亮">🔦</button>
  </div>
  <div class="flow-caption t-muted">▶ 点击站点，看数据在每一步的形态</div>
  <!-- ③ 走读字幕（aria-live，引擎自动更新） -->
  <div class="spot-caption t-muted" aria-live="polite">🔦 拖动探照灯（或聚焦后按 ←/→）：扫过哪个站点，对应翻译块里的真实代码行就跨文件同时点亮</div>
</div>
```

约定与自查：

- 被引用的翻译块必须带 `id`（`pair-ctl` 等），且页面中真实存在；`data-sp-pair` 与 `data-sp-line` 是**逗号分隔的平行列表**，数量须一致。
- 一个站点可同时点亮多个翻译块（跨文件调用链的行级同步）；没有 `data-sp-pair` 的站点只点亮自己。
- 交互全部由 app.js §7 内建：指针拖拽 + 松手吸附站点 + 键盘 ←/→；点亮的行用绿色 `.is-spot`，与悬停联动的橙色 `.is-hot` 可共存。
- **放在讲解调用链的正文中间**，翻译块紧跟其后（或之前）——探照灯的价值就在"流程图与代码同屏对照"。

### 调用链走读的设计基准（源码行坐标系）

凡"调用链类"可视化（探照灯 §3、数据流动画 §2、步骤回放 §10c 等）遵循四条设计基准——源自成熟代码导航工具的共识，只约束"怎么画"，不改变各组件的声明式用法与零依赖约束：

1. **源码行即坐标系**：布局由源码顺序或调用先后决定（从上到下、从左到右），确定性、可预期——禁止力导向/随机布点；读者每次打开应看到同一张图
2. **边从调用行长出来**：每条调用边要能指回发起调用的那一行——站点 `data-sp-file` 尽量写到「文件 · 行号」粒度，让"谁调用了谁"与"在哪一行调的"同屏可见
3. **诚实边**：实锤调用边正常画；推断边（第 3a 步未核实的）用虚线或"推断"旁注区分——线型就是置信度，读者一眼能分
4. **长函数窗口化**：展示超过约 80 行的函数体时，给"开头 + 每个调用点前后约 4 行"的窗口，中间折叠为"⋯ N 行"并注明省略行数；≤260 行可整段展示。折叠处必须写明省略位置，保住"学习者能在仓库里对上行号"

---

## 4. 洋葱剥层 —— 数据时间机器（Data Onion）

**部署位置**：第 3b 步"数据变形追踪"——挑一条数据的一生（`JSON 响应 → diff → 数组 → 写库`），把每一步形态变化做成层层嵌套的洋葱。

机制：**外层是最终形态**，向内逐层剥，每剥一层揭示"上一步是谁改的、字段从哪来、丢了什么"；被丢弃的字段（截断、默认值、过滤）在剥开的瞬间以"碎屑"掉进碎屑盘——把隐蔽 bug 的藏身处做成可亲手翻找的考古现场。数据流动画（§2）表达"经过哪里"（空间），洋葱表达"每一层长什么样、是谁动的手"（时间/层次）。

声明式组件：只写 JSON（引擎自动画同心圆 SVG + 事实面板 + 碎屑盘），零 JS。

```html
<div class="onion-scene scene">
  <div class="onion-title t-h3">🧅 {{标题，如：剥一颗数据洋葱：一次订单的一生}}</div>
  <p class="t-body">{{1–2 句引子：最外层是什么、为什么要剥}}</p>
  <script type="application/json" class="onion-data">
  {
    "layers": [
      { "name": "{{第 1 层·最外=最终形态}}", "shape": "{{此刻的数据形态，如：32 位十六进制字符串}}",
        "who": "{{谁动的手：函数名 · 文件 · 行号}}", "use": "{{这一层用来干嘛}}",
        "crumbs": ["{{剥开这层丢掉的：字段/形状/精度}}", "{{…可多条}}"] },
      { "name": "{{第 2 层}}", "shape": "…", "who": "…", "use": "…", "crumbs": ["…"] },
      { "name": "{{第 n 层=核·原始形态}}", "shape": "…", "who": "…", "use": "…" }
    ]
  }
  </script>
  <div class="onion-board"></div><!-- 引擎自动填充：同心圆 SVG + 事实面板 -->
</div>
```

约定与自查：

- `layers` **从最外层（最终形态）排到核（原始输入）**，3–6 层；最后一层就是核（白字深底）。
- 每层 `shape/who/use` 必须落到真实代码（函数名 + 文件 + 行号）；`crumbs` 写这层向下剥时**被丢弃**的东西（只有会掉碎屑的层才写）。
- 交互由 app.js §8 内建：点外圈剥一层（塌缩飞散）、点核、`↺ 重新包上` 复位；键盘 ←/→ 在未剥的圈间移动、Enter/Space 剥层；碎屑掉落动画尊重 `prefers-reduced-motion`。
- JSON 铁律：双引号、无尾逗号、不含 `</script>`；解析失败时场景会显示红色错误提示。

---

## 5. 交互式测验组件（应用型问题）

选后**立即**反馈：正确绿、错误红，每个选项带解释，解释要指向真实代码依据。

> 🔍 **溯源契约（workflow.md §7）**：出题前先在"测验溯源对照表"登记考点与讲解位置。每个选项 `data-why` 解释的机制（含干扰项指认的文件/函数）都必须在课程的某个翻译块/动画/控件中讲过——读者做错时能顺着解释回查到讲解。考了没讲的知识点 = 不合格测验。

> ♻️ **答后可重试**：app.js 在用户作答后自动注入"↻ 重试"按钮（复用 `.btn-ghost` 样式），点击清空选项与反馈。模板无需书写。

> 🔁 **`.quiz-opt` 样式双租户**：测验（本节）与因果赌注（§6）共用 `.quiz-opt` 按钮样式，但数据属性不同名（`data-correct/data-why` vs `data-bet-correct/data-bet-why`），两套引擎互不干扰。

```html
<div class="quiz" data-quiz="m1-q1">
  <div class="quiz-q t-h3">🧪 {{应用型问题，如：用户反馈切换页面后数据过期，你会先查哪里？}}</div>
  <div class="quiz-opts">
    <!-- data-correct 标记正确项；每个选项必须带 data-why 解释；一律 type="button" -->
    <button class="quiz-opt" type="button" data-correct="false"
            data-why="{{选错的解释：为什么不是这里，正确思路指向哪个文件}}">
      A. {{选项}}
    </button>
    <button class="quiz-opt" type="button" data-correct="true"
            data-why="{{选对的解释：依据是 xxx.js 里的哪段代码，它做了什么}}">
      B. {{选项}}
    </button>
    <button class="quiz-opt" type="button" data-correct="false" data-why="{{解释}}">C. {{选项}}</button>
  </div>
  <div class="quiz-fb t-body" hidden></div>
</div>
```

要点：测验放**模块收尾**做总结性检查；需要"讲解中途、代码亮出之前"的前置式预测，用 §6 因果赌注——两者分工不同，不要互相替代。选项容器内可用 ↑/↓/←/→ 在选项间移动焦点（不触发模块翻页）；作答后焦点自动移入反馈条，"↻ 重试"后回到第一个选项。

<details>
<summary>组件原理（仅供理解，禁止粘贴进成品）</summary>

```css
.quiz-opt { text-align: left; background: var(--bg); border: 1.5px solid var(--border);
  border-radius: var(--radius-m); padding: var(--space-2) var(--space-3);
  min-height: 44px; cursor: pointer; }
.quiz-opt.is-right { border-color: var(--accent-2); background: var(--accent-2); color: #FFFDF8; }
.quiz-opt.is-wrong { border-color: var(--accent-3); background: var(--accent-3); color: #FFFDF8; }
```

```js
/* 点击选项：正确项 .is-right、误选项 .is-wrong，全部锁定，反馈条显示 data-why */
```
</details>

---

## 6. 因果赌注 —— 预测式探针（Predict-then-Reveal）

**部署位置**：第 3c 步"错误边界与容错"，以及一切关键转折点——**讲解中途、答案代码还没展示之前**。"这个异常是静默吞掉还是冒泡？""下一步会调用哪个函数？""这个变量此刻是什么值？"——先下注，再揭晓。

机制：学习者在代码揭晓**之前**押一注（复用 `.quiz-opt` 样式的下注条），点"运行"后真实代码行点亮、按命中与否给出"为什么"。与 §5 测验的范式差异：测验是模块收尾的总结性选择题；赌注是**嵌入式、前置式、连续式**的——把"被动读代码"变成"主动押注"，放在最需要动脑的转折点，而非章节结尾。

```html
<!-- data-bet-pair 指向揭晓时要点亮的翻译块 id（建议：赌注放在翻译块上方） -->
<div class="bet-scene scene" data-bet-pair="pair-m10-loop">
  <div class="bet-title t-h3">🎯 {{下注场景，如：先押一注，再往下看代码}}</div>
  <div class="quiz-opts bet-opts" aria-label="押注：{{这一注的问题，如：这个 ValueError 会怎么收场}}">
    <button class="quiz-opt" type="button" data-bet-correct="false"
            data-bet-why="{{押错的解释：为什么不是这条路径，依据哪个文件哪段}}">
      A. {{预测项}}
    </button>
    <button class="quiz-opt" type="button" data-bet-correct="true"
            data-bet-why="{{押中的解释：依据 xxx.js L@@ 的 try/except，它做了什么}}">
      B. {{预测项}}
    </button>
    <button class="quiz-opt" type="button" data-bet-correct="false" data-bet-why="{{解释}}">C. {{预测项}}</button>
  </div>
  <div class="bet-actions">
    <button class="viz-btn bet-run" type="button" disabled>▶ 运行揭晓</button>
  </div>
  <div class="quiz-fb t-body bet-fb" hidden></div>
</div>
```

约定与自查：

- 用 `data-bet-correct` / `data-bet-why`（**不是**测验的 `data-correct/data-why`）；正确项恰好一个。
- `data-bet-pair` 指向的翻译块紧跟其后——揭晓时其中**全部 `.tp-line` 点亮**（绿色）并平滑滚入视野，"答案在真实代码里"。
- 押注问题必须是"接下来会发生什么"式的前置预测，且答案可在后续代码里验证；交互由 app.js §9 内建（选中 `.is-sel` → 运行揭晓 → 锁定 + 反馈）。
- 每模块 1–2 注即可，放在转折点密度处；章节收尾的知识检查仍用 §5 测验。

---

## 7. 进度条 + 键盘导航（←/→ 切换模块，当前模块高亮）

```html
<!-- 侧边栏内：模块导航 + 进度 -->
<nav class="module-nav">
  <a class="nav-item" href="#m0">0 · 封面</a>
  <a class="nav-item" href="#m1">1 · {{模块名}}</a>
  <!-- … -->
</nav>
<div class="progress-track"><div class="progress-fill"></div></div>
<div class="progress-label t-muted"><span id="prog-text">模块 1 / N</span> · 用 ←/→ 键翻页</div>
```

要点：每门课恰好一份，勿重复初始化；app.js §5 内建键盘守卫——焦点在输入控件（沙盘滑块/单选钮）、测验/赌注选项容器内，或带修饰键的方向键不翻页；各控件内部的 ←/→ 已 stopPropagation。

<details>
<summary>组件原理（仅供理解，禁止粘贴进成品）</summary>

```js
/* go(i)：切换 .is-active 高亮 + 进度条宽度 + scrollIntoView；
   IntersectionObserver 滚动联动当前模块；navKeyOK 守卫修饰键与输入控件。 */
```
</details>

---

## 8. 组件选择速查表

| 需求 | 用本文件第几节 | 关键注意 |
|---|---|---|
| 代码 ↔ 大白话对照 | §1 | 代码逐字复制，data-i 两侧配对数量一致 |
| 数据逐步变形（看它经过哪里） | §2 | 站点 3–5 个，每个标注数据形态 |
| 调用链跨文件逐步走读（事件链 3a） | §3 | 站点带 data-sp-pair/data-sp-line/data-sp-file，翻译块带 id |
| 同一条数据的纵向演化 + 被丢弃字段（数据变形 3b） | §4 | layers 从最终形态排到核；crumbs 只写真被丢的 |
| 关键转折点先预测再揭晓（错误边界 3c） | §6 | data-bet-* 属性；紧跟要揭晓的翻译块 |
| 递归 / 回调 / 中间件链的调用与返回 | §12 | script 按 push/pop 预排好；帧字段落到真实函数 |
| 分支条件：不同输入走不同路（配置扩展面 3d / 设计取舍） | §11 | 只用预标注 when 映射驱动，禁止执行真实代码 |
| 真实数据对比（文件数/行数/耗时） | §10a / §10b | 每个数字标 anchor 出处，禁止编造 |
| 状态机 / 算法步骤 / 队列逐帧演化 | §10c | 帧数 3–6，同坐标系逐帧对比 |
| 模块收尾测验 | §5 | 每个选项必须有 data-why |
| 进度 + 键盘导航 | §7 | 每门课恰好一份，勿重复初始化 |
| 全新形态自定义可视化 | §13 | 引擎与模板覆盖不了再手写 |

选型口诀：**先问"学习者要动手做什么"**——扫路径用探照灯、挖变形用洋葱、押转折用赌注、推调用用栈塔、试分支用沙盘；纯观赏的动画只在数据确实"自己会动"时用（§2 数据流、§10 图表）。

## 9. 使用这些模板的检查清单

- [ ] 所有 `{{占位符}}` 已替换为当前代码库的真实内容
- [ ] `.tp-code` 中的代码与源文件**渲染后逐字一致**（转义后 DOM 文本 = 源码；含缩进与空行）
- [ ] 探照灯：`data-sp-pair` 引用的翻译块 id 真实存在，pair/line 平行列表等长；`.spot-lamp`/`.spot-caption` 齐全
- [ ] 洋葱：layers 3–6 层、从最终形态排到核；每层 who 落到函数 + 文件 + 行号；crumbs 只写真被丢弃的字段
- [ ] 赌注：正确项恰好一个，全部选项 data-bet-why 非空；data-bet-pair 指向的翻译块在附近
- [ ] 栈塔：script 按 push/pop 如实镜像真实调用结构（同帧内顺序试值可画成"弹出再压入"，但须在旁注说明）
- [ ] 沙盘：branches 的 when 与真实分支条件一一对应；不出现任何执行真实代码的逻辑（无 eval/Function）
- [ ] 测验正确项恰好一个，所有选项 data-why 非空，且每个考点（含干扰项机制）都能回查到课程内的具体讲解位置
- [ ] 页面上不存在任何 `http://` / `https://` **资源引用**（src/href/url()；app.js 内联源码里的 SVG 命名空间字符串豁免）
- [ ] 键盘导航与 IntersectionObserver 只初始化一次
- [ ] 每个 data-viz 图表的数字都来自仓库真实可查数据，`anchor` 已标注出处，无编造
- [ ] 四类 JSON 数据块（`.viz-data`/`.onion-data`/`.tower-data`/`.fork-data`）均可被 `JSON.parse` 解析（双引号、无尾逗号、数字不带引号），且字符串值不含裸 `</script`（需要时写作 `<\/script`）
- [ ] bars/timeline 的 `.viz-stage` 为空容器且带 `role="group"` + `aria-label`（不用 role="img"——交互子元素必须留在无障碍树内）；steps 的帧数 3–6、每帧有 `data-caption`
- [ ] data-viz 图表滚入视口才动（app.js 内建）；timeline 段上、steps 场景内、探照灯/洋葱/栈塔/沙盘、测验/赌注选项容器上的方向键不触发模块翻页
- [ ] 封面内容包在 .hero-stage 内且 .hero-glow 保留；未手写光晕 / 渐入（外壳自动）

---

## 10. 项目数据可视化引擎（data-viz：真实数据驱动的交互式动态图表）

当概念背后有**仓库真实数据**要展示时——各目录文件数/行数、依赖数量、事件链的先后与耗时——用本节的声明式引擎。它内置于 `resources/app.js` 第 4 节与 `resources/base.css` §13：课程作者只写 HTML + JSON 数据，**渲染、懒播放、键盘交互全部自动完成，不需要写任何 JS**。

与 §2 的分工：§2 是"形状固定、往里填名字"的通用模板；本节是"**数据来自本项目、图表为数据量身生长**"的项目专属动态图——这正是"贴合项目的交互式动态图像展示"的标准做法。

三种类型，由 `.viz-scene` 的 `data-kind` 指定：

| data-kind | 适用 | 数据来源 |
|---|---|---|
| `bars` | 真实指标对比（目录文件数、行数、依赖数、错误分布、各目录职责导览） | `<script type="application/json" class="viz-data">` |
| `timeline` | 一条事件链的时间先后与耗时（第 3a 步产物） | 同上 |
| `steps` | 状态机 / 算法步骤 / 队列逐帧演化 | `.viz-stepdeck` 内的 `.viz-step` 帧（任意内联 SVG/HTML） |

> 🔒 **数字证据纪律**：图表里每个数字都必须来自仓库真实可查数据——目录/文件数来自实际清点，行数来自实际读取统计，耗时来自代码里的超时常量或注释数值。**禁止编造**；每一项用 `anchor` 标注出处（如"清点自 src/ 目录"、"来自 package.json"、"src/queue.js L34 的 timeout"）。估测值必须注明"估"。

### 10a. bars — 条形对比

真实指标并排对比：滚入视口后条形从 0 生长到目标宽度；点击、Tab 聚焦或 ↑/↓ 选中一栏，`.viz-detail` 显示它的解读与数字出处；选中栏变松绿。

```html
<div class="viz-scene scene" data-kind="bars">
  <div class="viz-title t-h3">📊 {{图表标题}}</div>
  <script type="application/json" class="viz-data">
  {
    "unit": "个",
    "items": [
      { "label": "src/", "value": 12, "note": "业务逻辑全在这一层", "anchor": "清点自仓库目录结构" },
      { "label": "tests/", "value": 4, "note": "覆盖三个核心流程", "anchor": "清点自仓库目录结构" },
      { "label": "config/", "value": 2, "note": "环境配置，见第 3d 步结论", "anchor": "清点自仓库目录结构" }
    ]
  }
  </script>
  <div class="viz-stage" role="group" aria-label="{{图表标题}}"></div>
  <div class="viz-detail t-muted" hidden></div>
</div>
```

注意：条数 3–7；label 短（≤12 字）；value 为正整数；条形长度自动归一化（按最大值 100%），无需自己算百分比。**封面/总览册的"目录结构导览图"也用它**：每目录一栏，`note` 写一句话职责。

### 10b. timeline — 事件时间轴

把第 3a 步追踪到的真实事件链按起止时间铺开：段长度 ∝ `dur`，段起点 ∝ `t`，滚入后各段按时间顺序依次浮现；点击/聚焦某段 → 详情行显示「谁 · 函数：做了什么（出处）」；段上按 ←/→ 移动选中（已阻止冒泡，不翻模块）。

```html
<div class="viz-scene scene" data-kind="timeline">
  <div class="viz-title t-h3">🕐 {{标题：一次请求的各环节先后}}</div>
  <script type="application/json" class="viz-data">
  {
    "unit": "ms",
    "events": [
      { "t": 0,   "dur": 20, "label": "解析请求体", "who": "server.js", "fn": "express.json()", "note": "字节流变成 JS 对象", "anchor": "中间件注册顺序" },
      { "t": 20,  "dur": 45, "label": "JWT 鉴权", "who": "middleware/auth.js", "fn": "verify()", "note": "保安查身份证", "anchor": "timeout 常量 45ms" },
      { "t": 65,  "dur": 80, "label": "写库", "who": "models/Order.js", "fn": ".save()", "note": "真正落盘", "anchor": "MongoDB 驱动默认超时" },
      { "t": 145, "dur": 10, "label": "返回 201", "who": "controllers/orders.js", "fn": "res.json()", "note": "原路返回", "anchor": "" }
    ]
  }
  </script>
  <div class="viz-stage" role="group" aria-label="{{标题}}"></div>
  <div class="viz-detail t-muted" hidden></div>
</div>
```

注意：事件数 3–8 条，label ≤6 字（空间有限）；`t` 与 `dur` 同一单位（写进 `unit`），数值来自代码常量/注释；只表示先后顺序时所有 `dur` 写 1、`t` 递增，`unit` 写"步"。

### 10c. steps — 步骤回放

状态机 / 算法步骤 / 队列演化，逐帧展示：初始显示第 1 帧；◀/▶ 手动步进（手动步进会停掉自动播放）；"自动播放"每 1.6s 循环、只在滚入视口时运行；焦点在场景内时 ←/→ 步进且不翻模块；每帧的 `data-caption` 自动显示在控制条下方。

```html
<div class="viz-scene scene" data-kind="steps">
  <div class="viz-title t-h3">🕹️ {{标题：队列如何演化}}</div>
  <div class="viz-stage" role="group" aria-label="{{标题}}">
    <div class="viz-stepdeck">
      <div class="viz-step" data-caption="{{第 1 帧说明：初始队列为空}}">
        <svg viewBox="0 0 400 90" width="100%" role="img" aria-label="{{帧说明}}">…</svg>
      </div>
      <div class="viz-step" data-caption="{{第 2 帧说明：enqueue('a') 之后}}">
        <svg viewBox="0 0 400 90" width="100%" aria-label="{{帧说明}}">…</svg>
      </div>
      <!-- 3–6 帧构成一次完整演化 -->
    </div>
    <div class="viz-controls">
      <button class="viz-btn viz-prev" type="button" aria-label="上一帧">◀</button>
      <span class="viz-pos">1 / 3</span>
      <button class="viz-btn viz-next" type="button" aria-label="下一帧">▶</button>
      <button class="viz-btn viz-auto" type="button" aria-pressed="false">▶ 自动播放</button>
    </div>
    <div class="viz-caption t-muted">{{当前帧说明自动显示在这里}}</div>
  </div>
</div>
```

注意：

- 帧数 3–6；每帧一张 SVG，**同一坐标系**（改状态不改布局，逐帧对比才成立）
- 帧内 SVG 可复用 §2 的节点画法，但必须画出"状态变化"（高亮移动、元素进出）
- 算法类（排序/查找/递归）先在纸上用真实输入跑一遍，把每一步中间状态逐帧画出——帧内容必须与该代码库算法的真实行为一致

### 10d. 通用契约与自查

- **结构契约**：`.viz-scene[data-kind]`；bars/timeline 内含 `<script type="application/json" class="viz-data">` + 空 `.viz-stage` + 可选 `.viz-detail[hidden]`；steps 的 `.viz-stage` 内含 `.viz-stepdeck` 帧组 + `.viz-controls`（`.viz-prev` / `.viz-pos` / `.viz-next` / `.viz-auto`）+ `.viz-caption`
- **懒播放内建**：滚入视口才动画/步进、滚出复位——app.js 已接入 `c2cLazyPlay`，**不要再手写绑定**
- **键盘**：bars/timeline 可 Tab 聚焦 + Enter/Space 选中；timeline 段上、steps 场景内的 ←/→ 已阻止冒泡，不会触发模块翻页
- **无障碍**：`.viz-stage` 带 `role="group"` + `aria-label`（**不用 role="img"**——stage 内有可交互子元素，role="img" 会把它们从无障碍树剔除；纯展示的帧内 SVG 才用 role="img"）；选中态有可见高亮；动画尊重 `prefers-reduced-motion`（base.css 全局规则覆盖）
- **JSON 字段是纯文本**：`items[].note`/`anchor`（含 onion/tower/fork 的 note）由引擎以 textContent 渲染，**禁止写 HTML 实体**（`&gt;` 会显示成字面 "&gt;"）——需要 `>` `<` `&` 时直接写字符；转义铁律只适用于 HTML 标记层，不适用于 JSON 数据层
- **JSON 转义**：字符串用双引号、无尾逗号、数字不带引号、**绝不允许出现裸 `</script`**（需要时写作 `<\/script`）——本铁律同样适用于 `.onion-data`/`.tower-data`/`.fork-data`（fork 的 `code` 数组是逐字复制的真实代码，最容易踩中）
- **出错提示**：JSON 无法解析时 `.viz-stage` 显示红色错误提示——交付前自查应看到完整图表而非该提示

---

## 11. 分叉沙盘 —— 分支决策实验室（Branch Fork Sandbox）

**部署位置**：第 3d 步"配置与扩展面"，以及"为什么这里用策略模式/多态而不是 if 堆叠"这类设计取舍——凡是有真实分支点（`if / switch / 中间件条件`）的地方。

机制：学习者拖动一个"输入令牌"（请求对象、订单金额、用户角色）穿过岔路口，实时看到它落入哪个分支、沿途哪个字段被改写、最终变成什么；改一改令牌参数（滑块/预设），走另一条路。**不考"哪个对"**——是可重复试验的因果模拟，让学习者亲手"喂"不同输入观察代码的分岔行为，形成对条件逻辑的直觉。

声明式组件：只写 JSON（引擎自动生成参数区、岔路 SVG、分支结果卡、预标注代码行与投放按钮）。**沙盘不执行真实代码，仅用预标注分支结果驱动**——路由是"参数值 → 分支"的字符串匹配表。

```html
<div class="fork-scene scene">
  <div class="fork-title t-h3">🛤️ {{标题，如：把一个「进度事件」拖过节流闸门}}</div>
  <p class="t-body">{{1–2 句：岔路口在哪个函数、为什么值得亲手试}}</p>
  <script type="application/json" class="fork-data">
  {
    "gate": "{{岔路口标签，如：闸门：value 到了}}",
    "entryTag": "{{入口标签，如：📦 进度事件令牌}}",
    "tokenPrefix": "📊",
    "goLabel": "▶ 投放令牌",
    "params": [
      { "id": "value", "label": "进度值 value", "type": "range",
        "min": 0, "max": 100, "step": 1, "value": 37, "fmt": "%" },
      { "id": "ms", "label": "距上次发射", "type": "radio",
        "options": [ { "value": "30", "label": "30ms（刚发过）" },
                     { "value": "150", "label": "150ms（到点了）" } ] }
    ],
    "branches": [
      { "id": "b1", "title": "🟢 {{分支一}}", "cond": "{{真实条件，如：value == 0 / 100}}",
        "when": { "value": "0|100" },
        "fx": ["{{沿途被改写的字段/调用}}", "{{…}}"],
        "note": "{{这条分支的取舍说明}}",
        "code": ["if value == 0 or value == 100:", "    self.pv_signal.emit(value)"] },
      { "id": "b2", "title": "🟠 {{分支二}}", "cond": "…", "when": { "ms": "150" },
        "fx": ["…"], "note": "…", "code": ["…"] },
      { "id": "b3", "title": "⚪ {{兜底分支}}", "cond": "{{其余情况}}", "when": {},
        "fx": ["无任何写入"], "note": "…", "code": ["…"] }
    ]
  }
  </script>
  <div class="fork-board"></div><!-- 引擎自动填充：参数区 + 岔路图 + 结果卡 + 代码 + 字幕 -->
</div>
```

约定与自查：

- 分支 2–4 条，`branches` **按真实代码的分支顺序排列**；`when` 是"参数 id → 值集合"的匹配表（`"0|100"` 表示命中 0 或 100，`"*"` 任意），从上到下第一个全命中者胜出；三分支及以上最后一条写空 `when` 作兜底，穷举式双分支（if/else 两态）允许两条都写显式 `when`。
- 反例（不是沙盘场景）：两个并列调用点/双模式对照——没有参数组合空间，用翻译块并排或对照表即可；纯公式展开（y=k/x 类连续关系）不是 bars 场景，公式在翻译块里讲清即可。部署前过"删掉测试"：删掉该组件后模块正文一字不用改 = 凑数，删或换。
- `cond` 展示真实条件表达式；`code` 逐字复制自真实分支代码（预标注）；`fx` 芯片写沿途被改写的字段/调用——三者必须与真实代码一致。
- 参数用滑块（`type:"range"`）或离散预设（`type:"radio"`）；令牌文字显示第一个 range 参数的当前值。
- 交互由 app.js §11 内建：拖令牌 / 键盘 ←/→ 推移 / 「投放令牌」滑入；命中分支的滑道、结果卡、代码行同步点亮；改参数即重路由。全程零 eval、零真实执行。

---

## 12. 栈塔 —— 调用/返回推演器（Call-Stack Tower）

**部署位置**：递归、异步回调、中间件链、状态机嵌套——凡是"调用会再回来"的地方。尤其擅长表达"同一个函数在栈里出现两次"的递归本质。

机制：把调用链画成一座纵向的塔，每层是一个栈帧卡片（函数名 + 参数 + 局部变量）。点"调用"往塔顶压一层、点"返回"弹一层；点某一层展开看它的局部变量此刻的值、它下一步会调谁、返回给谁。数据流动画（§2）讲单线站点、探照灯（§3）讲跨文件路径，栈塔讲**可推演的运行时纵深**——让"递归""回调""深层调用链"变成可以亲手 push/pop 的机械，尤其擅长表达"同一个函数在栈里出现两次"的递归本质。

声明式组件：只写 JSON（引擎自动生成塔、结果收集盘与控制按钮）。push/pop 序列**预标注**，不执行真实代码。

```html
<div class="tower-scene scene">
  <div class="tower-title t-h3">🗼 {{标题，如：把这段回溯亲手压进栈里}}</div>
  <p class="t-body">{{1–2 句：推演哪段调用；与真实代码结构的关系}}</p>
  <script type="application/json" class="tower-data">
  {
    "base": "▮ {{地基说明，如：主循环 xxx 的调用栈（塔顶 = 当前帧）}}",
    "collect": { "title": "📦 {{返回值收集盘，如：方案收集盘 res_list}}", "empty": "（还没有合法方案）" },
    "pushLabel": "调用",
    "popLabel": "返回",
    "script": [
      { "act": "push", "fn": "{{函数名}}", "depth": 1, "badge": "第 1 次进栈",
        "hyp": "{{本帧假设/参数摘要}}", "args": "{{参数此刻的值}}",
        "locals": "{{局部变量此刻的值}}", "check": "{{约束检查结果}}",
        "next": "{{它下一步调谁}}", "ret": "{{返回给谁}}", "note": "{{这一步的解说}}" },
      { "act": "push", "fn": "…", "depth": 2, "…": "…" },
      { "act": "pop", "res": "{{返回值，如：[0, 0]}}", "note": "{{弹栈解说}}" },
      { "act": "pop", "res": null, "note": "{{栈清空、控制权回到哪}}" }
    ]
  }
  </script>
  <div class="tower-board">
    <div class="tower-col">
      <div class="tower-stack" aria-label="调用栈（塔顶是当前帧）"></div>
    </div>
    <div class="tower-col tower-side"></div>
  </div>
  <div class="tower-controls">
    <button class="viz-btn tower-push" type="button">▶ 调用</button>
    <button class="viz-btn tower-pop" type="button" disabled>◀ 返回</button>
    <button class="viz-btn tower-reset" type="button">↺ 重来</button>
  </div>
</div>
```

约定与自查：

- `script` **按真实代码的调用结构预排**（act 只能是 `push`/`pop`）；`depth` 表示栈深度；`badge` 可省（自动计"第 N 次进栈"）；`args/locals/check/next/ret` 按需填写，值必须来自对真实代码的推演。
- 真实代码若在同一帧内顺序试多种取值，可画成"弹出再压入"让栈的涨落可见，但**必须在 note 或旁注里说明**这是为了可视化。
- `collect` 可省（没有返回值收集的场景）；`res` 为 null 表示该次返回不收集值。
- 交互由 app.js §10 内建：▶ 调用压帧（帧卡片带弹簧入场）、◀ 返回弹帧；帧间 ←/→/↑/↓ 移动焦点、Enter 展开局部变量；返回值掉进收集盘。按钮会根据 script 的下一步自动启用/禁用并提示"该调用还是该返回"。

---

## 13. 自定义可视化（引擎覆盖不了时的逃生口）

§1–§7、§10–§12 是保底方案，不是上限。当概念的实际形态连引擎都表达不贴切（如并发竞态、限流排队、自定义布局的中间件漏斗），为概念量身设计新形式——判断标准：**这个形式是不是为这个概念而生**。示例方向与工程约束见 workflow.md §6"不拘泥于既有形式"。

> 先查引擎：概念本质是数据对比/时序/状态步骤时用 §10，是跨文件走读/数据演化/押注/调用栈/分支试验时用 §3/§4/§6/§12/§11，**不要手写**；只有都覆盖不了的全新形态才手写 JS。

手写 JS 的运行时纪律（v1.11 起为验收项）：

1. **必须接入懒播放**：新场景一律接 `window.c2cLazyPlay(scene, play, stop)`（app.js 预留的对外扩展点）——禁止自建 IntersectionObserver 之外的播放控制
2. **禁止 scroll/resize 高频监听**：滚动联动一律用 IntersectionObserver；指针跟随时先缓存 rect、rAF 合帧后再写样式（参照封面光晕的做法）
3. **只动 transform / opacity**：自定义动效优先改这两个合成器友好属性，避免逐帧改布局属性（left/top/width）
4. **安全白名单**：只允许 DOM/CSS/事件/定时器/IntersectionObserver；禁止 fetch/XHR/WebSocket、动态 import、location 跳转、eval/new Function、document.write、外链资源（见 workflow.md §6 工程约束第 6 条）

自定义动画的最小骨架（复用全局懒播放调度器，保证"滚入才播"体验一致）：

```html
<div class="my-viz scene"><!-- 你的自定义动画结构，样式基于 base.css 变量 --></div>
```

```js
/* 课程内联脚本（app.js 之后）：接入懒播放 */
var viz = document.querySelector('.my-viz');
window.c2cLazyPlay(viz, function () {
  /* play：开始表演，例如加类名触发 CSS animation 或启动 setInterval */
}, function () {
  /* stop：停止并复位到初始静止态 */
});
```

```css
/* 自定义样式追加在 <style> 末尾，只用既有变量保持视觉统一 */
.my-viz .part { fill: var(--bg-card); stroke: var(--accent); }
.my-viz.is-running .part { animation: my-move 2s var(--ease-out) infinite; }
```

自查三条：零外部资源；初始静止、滚入才播；样式只依赖 base.css 变量。做出来不如模板直观就回退模板——宁可用对形式，不用新形式。
