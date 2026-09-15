/* ===================================================================
   code2course · app.js — 课程通用交互脚本
   -------------------------------------------------------------------
   用法：生成课程时把本文件内容原样复制进每个 HTML 尾部的 script 标签内（多文件
   模式下每册都要内联一份）。无需配置：脚本自动扫描页面上的组件结构
   并绑定行为。课程内容只需按约定类名/属性写 HTML。
   约定的结构见 references/interactive-elements.md 各节模板（项目数据
   可视化组件见本文件第 4 节引擎；参与式控件见第 7–11 节引擎）。

   v1.9 变更：移除 5 个低参与度控件（卡片 3D 悬停倾斜、架构图悬停、
   术语气泡、donut 占比环、群聊动画）的脚本；新增 5 个参与式控件引擎：
   执行探照灯(§7) / 洋葱剥层(§8) / 因果赌注(§9) / 栈塔(§10) / 分叉沙盘(§11)。
   v1.11 变更：赌注揭晓行改用独立类 .is-spot-bet（探照灯清不掉，修复
   跨引擎串扰）；探照灯/沙盘拖拽 rect 缓存 + rAF 合帧（消除强制同步
   布局）；翻译块/测验选项改为 roving tabindex（Tab 停留点从 ~140 降到
   ~40）；答题后焦点自动移入反馈条；洋葱层数上限校验；两代引擎的重复
   辅助函数合并（vizEl/ctrlEl 等成为共享实现的别名）；栈塔弹空恢复
   空栈提示；赌注支持"再押一注"。
   ===================================================================
   @version 1.17.0 */
(function () {
  'use strict';

  /* ---------- 主题切换（手动优先于系统，localStorage 持久化） ---------- */
  var toggle = document.querySelector('.theme-toggle');
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem('c2c-theme'); } catch (e) {}
  if (saved === 'dark' || saved === 'light') root.dataset.theme = saved;
  function syncIcon() {
    if (!toggle) return;
    var dark = root.dataset.theme === 'dark';
    toggle.textContent = dark ? '☀️' : '🌙';
    toggle.setAttribute('aria-pressed', dark ? 'true' : 'false');
    toggle.setAttribute('aria-label', dark ? '切换日间模式' : '切换夜间模式');
  }
  syncIcon();
  if (toggle) toggle.addEventListener('click', function () {
    var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    try { localStorage.setItem('c2c-theme', next); } catch (e) {}
    syncIcon();
  });

  /* ---------- 1. 代码 ↔ 大白话：悬停/聚焦同步高亮 + 复制代码 ----------
     键盘模型（v1.11 roving tabindex）：翻译块整体是一个 Tab 停留点
     （tabindex=0），块内 ↑/↓ 在代码行/解释段之间移动焦点——全课 Tab
     停留点从每行一个收敛为每块一个，键盘用户不再逐行 Tab。 */
  document.querySelectorAll('.translate-pair').forEach(function (pair) {
    function hot(i, on) {
      pair.querySelectorAll('[data-i="' + i + '"]')
        .forEach(function (x) { x.classList.toggle('is-hot', on); });
    }
    var seq = [];   /* 块内全部可聚焦片段（行 + 解释段），按 DOM 序 */
    pair.querySelectorAll('[data-i]').forEach(function (el) {
      el.setAttribute('tabindex', '-1');   /* 焦点由 ↑/↓ 漫游 */
      seq.push(el);
      el.addEventListener('mouseenter', function () { hot(el.dataset.i, true); });
      el.addEventListener('mouseleave', function () { hot(el.dataset.i, false); });
      el.addEventListener('focus', function () { hot(el.dataset.i, true); });
      el.addEventListener('blur', function () { hot(el.dataset.i, false); });
    });
    pair.setAttribute('tabindex', '0');
    pair.setAttribute('role', 'group');
    var fileTag = pair.querySelector('.tp-file');
    if (fileTag) pair.setAttribute('aria-label', '代码对照：' + fileTag.textContent.trim());
    pair.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
      var i = seq.indexOf(document.activeElement);
      var j = i + (e.key === 'ArrowDown' ? 1 : -1);
      if (j < 0 || j >= seq.length) return;   /* 首尾不循环，退出靠 Tab */
      e.preventDefault();
      e.stopPropagation();                     /* 块内漫游，不触发滚动 */
      seq[j].focus();
    });

    /* 复制按钮：自动注入到每个翻译块头部，复制左侧逐字代码（不含行号） */
    var head = pair.querySelector('.tp-head');
    var code = pair.querySelector('.tp-code');
    if (!head || !code) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tp-copy';
    btn.textContent = '⧉ 复制';   /* 文本自说明，无需 aria-label 覆盖 */
    var copyTimer = null;
    btn.addEventListener('click', function () {
      var text = Array.prototype.map.call(code.querySelectorAll('.tp-line'),
        function (p) { return p.textContent.replace(/\n+$/, ''); }).join('\n');
      function done() {
        btn.textContent = '✓ 已复制';
        btn.classList.add('is-copied');
        if (copyTimer) clearTimeout(copyTimer);   /* 连续复制时避免计时器竞争 */
        copyTimer = setTimeout(function () {
          btn.textContent = '⧉ 复制';
          btn.classList.remove('is-copied');
        }, 1600);
      }
      function fallback() {
        var ta = document.createElement('textarea');
        ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.focus(); ta.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
        document.body.removeChild(ta);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, fallback);
      } else { fallback(); }
    });
    head.appendChild(btn);
  });

  /* ---------- 懒播放调度器 ----------
     页面加载时所有动画保持静止（首帧/隐藏态），直到所属场景滚入视口
     才开始播放；滚出视口即暂停，再次滚入自动重播；标签页隐藏时也暂停、
     重新可见后仅恢复仍在视口内的场景（避免后台空转）。

     ★ 课程自定义动画请复用本函数：它挂在 window.c2cLazyPlay 上，
       课程内联脚本中调用 window.c2cLazyPlay(el, playFn, stopFn)，
       el 为动画容器（.scene 级元素），playFn 开始表演，stopFn 停止并复位。
     实现：所有场景共享一个 IntersectionObserver（单例），条目用 WeakMap 关联；
     可见性变化通过全局 visibilitychange 统一暂停/恢复。 */
  var lazyIO = null;
  var lazyMap = new WeakMap();
  var lazyEntries = [];   /* 普通数组即可：只存 entry 对象，生命周期与页面一致 */

  /* prefers-reduced-motion 统一探针（v1.11 合并两处重复的 matchMedia+try/catch） */
  function reduceMotion() {
    try {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { return false; }
  }

  function lazyPlay(el, play, stop) {
    var entry = { play: play, stop: stop, playing: false, visible: false, hidden: false };
    lazyMap.set(el, entry);
    lazyEntries.push(entry);
    /* 注：本脚本整体要求现代浏览器（NodeList.forEach / closest / dataset /
       color-mix 同代特性），不支持 IntersectionObserver 的更老浏览器在更早
       的语句就会抛错——此分支只保证"IO 存在但被禁用"等边缘场景直接播放 */
    if (!('IntersectionObserver' in window)) { play(); return; }
    if (!lazyIO) {
      lazyIO = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          var e = lazyMap.get(en.target);
          if (!e) return;
          e.visible = en.isIntersecting;
          if (en.isIntersecting && !e.playing && !e.hidden) {
            e.playing = true; e.play();
          } else if (!en.isIntersecting && e.playing) {
            e.playing = false; if (e.stop) e.stop();
          }
        });
      }, { threshold: 0.15 });  /* 露出 15% 即开播：过高会让高于视口约 3 倍的场景
                                   永远达不到比例而静默失活 */
    }
    lazyIO.observe(el);
  }
  window.c2cLazyPlay = lazyPlay;   /* 暴露给课程自定义动画复用 */

  /* 标签页切到后台：暂停所有正在播放的场景；切回且仍在视口内则恢复 */
  document.addEventListener('visibilitychange', function () {
    lazyEntries.forEach(function (e) {
      if (document.hidden) {
        if (e.playing) { e.playing = false; if (e.stop) e.stop(); e.hidden = true; }
      } else if (e.hidden) {
        e.hidden = false;
        if (e.visible) { e.playing = true; e.play(); }
      }
    });
  });

  /* ---------- 1.5 封面光晕（指针跟随景深） ----------
     仅「精细指针 + 非减少动效」设备启用：封面 .hero-stage 的
     .hero-glow 跟随指针（更新 --mx/--my），营造景深。
     v1.9：卡片 3D 悬停倾斜（.tilt）控件已移除，本节只剩封面光晕。 */
  (function initHeroGlow() {
    var fine = false, noMotion = false;
    try {
      fine = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
      noMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { return; }
    if (!fine || noMotion) return;

    var hero = document.querySelector('.hero-stage');
    if (!hero) return;
    var heroRect = null, heroRaf = null;
    hero.addEventListener('pointerenter', function () {
      heroRect = hero.getBoundingClientRect();
    });
    hero.addEventListener('pointermove', function (e) {
      if (!heroRect) heroRect = hero.getBoundingClientRect();
      var r = heroRect;
      var mx = ((e.clientX - r.left) / r.width * 100).toFixed(1) + '%';
      var my = ((e.clientY - r.top) / r.height * 100).toFixed(1) + '%';
      if (heroRaf) cancelAnimationFrame(heroRaf);
      heroRaf = requestAnimationFrame(function () {
        hero.style.setProperty('--mx', mx);
        hero.style.setProperty('--my', my);
      });
    });
    hero.addEventListener('pointerleave', function () { heroRect = null; });
  })();

  /* ---------- 2. 数据流动画：能量点循环 + 站点可点击（滚入才播） ---------- */
  document.querySelectorAll('.flow-scene').forEach(function (scene) {
    var nodes = scene.querySelectorAll('.flow-node');
    var paths = scene.querySelectorAll('.flow-path');
    var labels = scene.querySelectorAll('.flow-label');
    var dot = scene.querySelector('.flow-dot');
    if (!nodes.length || !dot) return;
    var step = 0, timer = null;

    function paint() {
      /* 契约防御：节点缺 circle 或 step 越界时静默跳过，不让整场景崩溃 */
      var node = nodes[step];
      var c = node && node.querySelector('circle');
      if (!c) return;
      nodes.forEach(function (n, i) {
        var on = i <= step;
        n.classList.toggle('is-on', on);
        if (paths[i - 1]) paths[i - 1].classList.toggle('is-on', on);
        if (labels[i]) labels[i].classList.toggle('is-on', on);
      });
      dot.style.opacity = 1;
      dot.setAttribute('cx', c.getAttribute('cx') || '0');
      dot.setAttribute('cy', c.getAttribute('cy') || '0');
    }
    function play() {
      if (timer) clearInterval(timer);
      step = 0; paint();
      if (reduceMotion()) return;   /* 减少动效：静态展示首站，不自动循环 */
      timer = setInterval(function () {
        step = (step + 1) % nodes.length;  /* 循环播放 */
        paint();
      }, 1400);
    }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    /* 供点击/键盘共用的安全跳步：data-step 非法（缺属性/越界）时忽略 */
    function jumpTo(g) {
      var s = +g.dataset.step;
      if (isNaN(s) || s < 0 || s >= nodes.length) return;
      stop(); step = s; paint();
    }
    scene.addEventListener('click', function (e) {
      var g = e.target.closest('.flow-node');
      if (g) jumpTo(g);
    });
    /* 键盘可访问：Tab 聚焦站点，Enter/Space 与点击等价 */
    nodes.forEach(function (g, i) {
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      /* 契约防御：data-step 必须严格等于 DOM 序号，否则自动播放（按序）
         与点击/键盘跳步（按属性）两条路径分叉（v1.11 增校验） */
      if (+g.dataset.step !== i) {
        console.warn('[code2course] .flow-node data-step 与 DOM 顺序不一致（第 ' +
          (i + 1) + ' 个站点应为 data-step="' + i + '"），点击跳步可能错位');
      }
      var t = g.querySelector('text');
      if (t) g.setAttribute('aria-label', t.textContent);
      g.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault(); jumpTo(g);
        }
      });
    });
    lazyPlay(scene, play, stop);   /* 滚入视口才开始流动 */
  });

  /* ---------- 3. 测验：选择后立即反馈并锁定 + 重试 ----------
     （.quiz-opt 样式同时被第 9 节「因果赌注」复用，两处契约都在
     interactive-elements.md：§5 测验 / §6 赌注。）
     键盘模型（v1.11）：选项容器为一个 Tab 停留点，↑/↓/←/→ 在选项间
     漫游（stopPropagation 不翻模块）；作答后焦点自动移入反馈条，
     "↻ 重试"后焦点回到第一个选项。 */
  function optsKeyboard(box) {
    var opts = Array.prototype.slice.call(box.querySelectorAll('.quiz-opt'));
    if (!opts.length) return;
    box.setAttribute('role', 'group');
    box.setAttribute('tabindex', '0');
    opts.forEach(function (b) { b.tabIndex = -1; });
    box.addEventListener('focusin', function () {
      /* Tab 落在容器本身（而非某个选项）时，直接把焦点交给第一个可用项 */
      if (document.activeElement === box) {
        var first = opts.filter(function (b) { return !b.disabled; })[0];
        if (first) first.focus();
      }
    });
    box.addEventListener('keydown', function (e) {
      var k = e.key;
      if (k !== 'ArrowUp' && k !== 'ArrowDown' &&
          k !== 'ArrowLeft' && k !== 'ArrowRight') return;
      var avail = opts.filter(function (b) { return !b.disabled; });
      if (!avail.length) return;
      e.preventDefault();
      e.stopPropagation();   /* 选项间漫游，不翻模块 */
      var i = avail.indexOf(document.activeElement);
      var d = (k === 'ArrowDown' || k === 'ArrowRight') ? 1 : -1;
      avail[(i + d + avail.length) % avail.length].focus();
    });
  }
  function focusFb(fb) {
    if (!fb) return;
    fb.setAttribute('tabindex', '-1');
    fb.focus();   /* 答题后焦点移入反馈条，屏幕阅读器立即播报对错与解释 */
  }
  document.querySelectorAll('.quiz').forEach(function (quiz) {
    var fb = quiz.querySelector('.quiz-fb');
    if (fb) fb.setAttribute('role', 'status');   /* 反馈可被屏幕阅读器播报 */
    var optsBox = quiz.querySelector('.quiz-opts');
    if (optsBox) optsKeyboard(optsBox);
    quiz.querySelectorAll('.quiz-opt').forEach(function (btn) {
      btn.type = 'button';                       /* 防御：模板漏写 type 也不误提交 */
      btn.addEventListener('click', function () {
        var ok = btn.dataset.correct === 'true';
        quiz.querySelectorAll('.quiz-opt').forEach(function (b) {
          if (b.dataset.correct === 'true') b.classList.add('is-right');
          else if (b === btn) b.classList.add('is-wrong');
          b.disabled = true;
        });
        if (fb) {
          fb.textContent = (ok ? '✅ 对了！' : '❌ 再想想 — ') + (btn.dataset.why || '');
          fb.classList.toggle('is-right', ok);
          fb.classList.toggle('is-wrong', !ok);
          fb.hidden = false;
        }
        focusFb(fb);   /* 焦点先移入反馈，再由重试恢复 */
        /* 答后注入一次"重试"按钮，允许清空重做（app.js 注入，模板无需书写） */
        if (!quiz.querySelector('.quiz-retry')) {
          var retry = document.createElement('button');
          retry.type = 'button';
          retry.className = 'quiz-retry btn-ghost';
          retry.textContent = '↻ 重试';
          retry.addEventListener('click', function () {
            quiz.querySelectorAll('.quiz-opt').forEach(function (b) {
              b.classList.remove('is-right', 'is-wrong');
              b.disabled = false;
            });
            if (fb) {
              fb.hidden = true;
              fb.textContent = '';
              fb.classList.remove('is-right', 'is-wrong');
            }
            retry.remove();
            var first = quiz.querySelector('.quiz-opt');
            if (first) first.focus();   /* 焦点回到第一个选项，重做闭环 */
          });
          quiz.appendChild(retry);
        }
      });
    });
  });

  /* ---------- 4. 项目数据可视化引擎（data-viz） ----------
     .viz-scene 声明式组件：用仓库真实数据渲染贴合项目的交互式动态图表。
     三种类型（scene 的 data-kind 指定）：
       bars     条形对比 —— 数据在 .viz-data（script type="application/json"）JSON 块
       timeline 事件时间轴 —— 同上 JSON，按起止时间与时长铺开
       steps    步骤回放 —— 不用 JSON：.viz-stepdeck 内若干 .viz-step 帧
                （每帧任意内联 SVG/HTML + data-caption 一句说明）
     全部用 createElement / textContent 构建（不拼 innerHTML），零依赖；
     动画自动接入全局懒播放（滚入视口才动、滚出复位，再滚入重播）。 */
  /* 两代引擎共用的底层辅助（v1.11 合并重复实现——vizEl/ctrlEl 等成为别名，
     行为与 v1.10 完全一致，调用点零改动） */
  function c2cEl(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  }
  var vizEl = c2cEl;                          /* §4 引擎沿用旧名 */
  var ctrlEl = c2cEl;                         /* §7–§11 引擎沿用旧名 */
  function vizFmt(n) {
    /* 千分位只加在整数部分，小数（如 timeline 的 t/dur=0.5）原样保留 */
    var s = String(n).split('.');
    s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return s.join('.');
  }
  function c2cParse(scene, selector) {
    var el = scene.querySelector(selector);
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }
  function vizParseData(scene) { return c2cParse(scene, '.viz-data'); }
  function ctrlParse(scene, cls) { return c2cParse(scene, 'script.' + cls); }
  function vizError(stage) {
    stage.classList.add('is-error');
    stage.textContent = '⚠️ 可视化数据无法解析——请检查 .viz-data 内的 JSON 是否合法。';
  }
  function ctrlError(scene, what) {
    var d = c2cEl('div', 'viz-stage is-error');
    d.textContent = '⚠️ ' + what + '数据无法解析——请检查场景内 JSON 是否合法。';
    scene.appendChild(d);
  }
  /* bars/timeline 的"滚入才生长/浮现"接线（v1.11 从两处三连复制提炼） */
  function lazyStage(scene, stage) {
    lazyPlay(scene,
      function () { stage.classList.add('is-playing'); },
      function () { stage.classList.remove('is-playing'); });
  }
  function vizNote(item) {
    return ((item.note ? item.note + ' · ' : '') + (item.anchor || '')) || '';
  }
  function vizShowDetail(scene, text) {
    var d = scene.querySelector('.viz-detail');
    if (!d) return;
    if (text) { d.textContent = text; d.hidden = false; }
    else d.hidden = true;
  }

  /* 4a. 条形对比：滚入才生长；点击/聚焦任一栏 → 详情行显示解读与数字出处 */
  function vizBars(scene, stage, data) {
    var items = data.items || [];
    if (!items.length) { vizError(stage); return; }
    var max = 1;
    items.forEach(function (it) { max = Math.max(max, Number(it.value) || 0); });
    var rows = [];
    items.forEach(function (it) {
      var row = vizEl('div', 'viz-row');
      row.setAttribute('tabindex', '0');
      row.setAttribute('role', 'button');
      var label = vizEl('div', 'viz-label');
      label.textContent = it.label;
      var track = vizEl('div', 'viz-track');
      var bar = vizEl('div', 'viz-bar');
      bar.style.setProperty('--viz-w',
        Math.max(2, Math.round((Number(it.value) || 0) / max * 100)) + '%');
      var val = vizEl('div', 'viz-value');
      val.textContent = vizFmt(it.value) + (data.unit ? ' ' + data.unit : '');
      row.appendChild(label);
      row.appendChild(track);
      track.appendChild(bar);
      row.appendChild(val);
      row.setAttribute('aria-label',
        it.label + '：' + vizFmt(it.value) + (data.unit || ''));
      function select() {
        rows.forEach(function (r) { r.classList.remove('is-sel'); });
        row.classList.add('is-sel');
        vizShowDetail(scene, vizNote(it) || it.label);
      }
      row.addEventListener('click', select);
      row.addEventListener('focus', select);   /* Tab 聚焦即选中，与 timeline 一致 */
      row.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(); }
        /* ↑/↓ 在条形列表内移动选中；阻止冒泡，不与模块翻页（←/→）冲突 */
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          e.stopPropagation();
          var k = rows.indexOf(row) + (e.key === 'ArrowDown' ? 1 : -1);
          rows[Math.max(0, Math.min(rows.length - 1, k))].focus();
        }
      });
      rows.push(row);
      stage.appendChild(row);
    });
    lazyPlay(scene,
      function () { stage.classList.add('is-playing'); },
      function () { stage.classList.remove('is-playing'); });
  }

  /* 4b. 事件时间轴：真实事件链按起止时间铺开；点击/聚焦段 → 详情；
     段上按 ←/→ 移动选中（阻止冒泡，不与模块翻页冲突） */
  function vizTimeline(scene, stage, data) {
    var evs = (data.events || []).slice().sort(function (a, b) {
      return (Number(a.t) || 0) - (Number(b.t) || 0);
    });
    if (!evs.length) { vizError(stage); return; }
    var total = 1;
    evs.forEach(function (e) {
      total = Math.max(total, (Number(e.t) || 0) + (Number(e.dur) || 1));
    });
    var track = vizEl('div', 'viz-tl');
    var axis = vizEl('div', 'viz-tl-axis');
    var segs = [];
    evs.forEach(function (e, i) {
      var seg = vizEl('div', 'viz-seg');
      var left = (Number(e.t) || 0) / total * 100;
      var w = Math.max(2, (Number(e.dur) || 1) / total * 100);
      seg.style.left = left + '%';
      seg.style.width = w + '%';
      seg.style.setProperty('--viz-delay', (i * 140) + 'ms');
      if (i % 2 === 1) seg.classList.add('viz-seg-alt');
      seg.textContent = e.label;
      seg.setAttribute('tabindex', '0');
      seg.setAttribute('role', 'button');
      seg.setAttribute('aria-label', e.label +
        '（' + vizFmt(e.t) + '–' + vizFmt((Number(e.t) || 0) + (Number(e.dur) || 0)) +
        (data.unit ? ' ' + data.unit : '') + '）');
      function select() {
        segs.forEach(function (s) { s.classList.remove('is-sel'); });
        seg.classList.add('is-sel');
        var who = (e.who || '') + (e.fn ? ' · ' + e.fn : '');
        vizShowDetail(scene, (who ? who + '：' : '') +
          (e.note || '') + (e.anchor ? '（' + e.anchor + '）' : ''));
      }
      seg.addEventListener('click', select);
      seg.addEventListener('focus', select);
      seg.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); select(); }
        if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft') {
          ev.preventDefault();
          ev.stopPropagation();   /* 段内移动选中，不翻模块 */
          var k = Math.max(0, Math.min(segs.length - 1,
            segs.indexOf(seg) + (ev.key === 'ArrowRight' ? 1 : -1)));
          segs[k].focus();
        }
      });
      segs.push(seg);
      track.appendChild(seg);
      var tick = vizEl('span', 'viz-tl-tick');
      tick.style.left = left + '%';
      tick.textContent = vizFmt(e.t);
      axis.appendChild(tick);
    });
    stage.appendChild(track);
    stage.appendChild(axis);
    lazyPlay(scene,
      function () { stage.classList.add('is-playing'); },
      function () { stage.classList.remove('is-playing'); });
  }

  /* 4c. 步骤回放：逐帧展示状态演化（帧 = 任意内联 SVG/HTML）。
     ◀/▶ 手动步进；"自动播放"循环（滚出视口自动暂停）；帧容器内 ←/→
     步进且阻止冒泡，不与模块翻页冲突。 */
  function vizSteps(scene, stage) {
    var deck = stage.querySelector('.viz-stepdeck');
    var frames = deck ? deck.children : [];
    if (!frames.length) return;
    stage.classList.add('is-js');          /* 有 JS 才隐藏非当前帧 */
    var pos = stage.querySelector('.viz-pos');
    var cap = stage.querySelector('.viz-caption');
    var prevBtn = stage.querySelector('.viz-prev');
    var nextBtn = stage.querySelector('.viz-next');
    var autoBtn = stage.querySelector('.viz-auto');
    var cur = 0, timer = null, auto = false;
    /* 让 stage 可聚焦：点击场景任意处聚焦后，空白处也能用 ←/→ 步进 */
    stage.setAttribute('tabindex', '-1');
    stage.addEventListener('pointerdown', function () { stage.focus(); });

    function show(i) {
      cur = Math.max(0, Math.min(frames.length - 1, i));
      Array.prototype.forEach.call(frames, function (f, k) {
        f.classList.toggle('is-on', k === cur);
      });
      if (cap) cap.textContent = frames[cur].getAttribute('data-caption') || '';
      if (pos) pos.textContent = (cur + 1) + ' / ' + frames.length;
    }
    function play() {
      if (!auto) return;
      if (timer) clearInterval(timer);
      timer = setInterval(function () { show((cur + 1) % frames.length); }, 1600);
    }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    function setAuto(on) {
      auto = on;
      if (autoBtn) {
        autoBtn.textContent = on ? '⏸ 暂停自动' : '▶ 自动播放';
        autoBtn.classList.toggle('is-auto-on', on);
        autoBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
      }
      if (on) play(); else stop();
    }
    function step(d) {
      setAuto(false);
      show(cur + d);
    }
    if (prevBtn) prevBtn.addEventListener('click', function () { step(-1); });
    if (nextBtn) nextBtn.addEventListener('click', function () { step(1); });
    if (autoBtn) autoBtn.addEventListener('click', function () { setAuto(!auto); });
    stage.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault();
        e.stopPropagation();               /* 步进回放，不翻模块 */
        step(e.key === 'ArrowRight' ? 1 : -1);
      }
    });
    show(0);
    lazyPlay(scene, play, stop);           /* 自动播放只在视口内运行 */
  }

  /* 主扫描：自动渲染页面上所有 data-viz 场景 */
  document.querySelectorAll('.viz-scene').forEach(function (scene) {
    var stage = scene.querySelector('.viz-stage');
    if (!stage) return;
    var kind = scene.getAttribute('data-kind') || 'bars';
    if (kind === 'steps') { vizSteps(scene, stage); return; }
    var data = vizParseData(scene);
    if (!data) { vizError(stage); return; }
    if (kind === 'bars') vizBars(scene, stage, data);
    else if (kind === 'timeline') vizTimeline(scene, stage, data);
    else vizError(stage);
  });

  /* ---------- 5. 进度条 + 键盘 ←/→ + 滚动联动 ---------- */
  var modules = Array.prototype.slice.call(document.querySelectorAll('.module'));
  var items = Array.prototype.slice.call(document.querySelectorAll('.nav-item'));
  var fill = document.querySelector('.progress-fill');
  var text = document.getElementById('prog-text');
  var cur = 0;
  var scrolling = false, scrollTimer = null;   /* 程序化滚动期间的 IO 抑制标志 */

  /* 首次打开强制回到顶部：浏览器会恢复上次滚动位置（history.scrollRestoration）
     并自动滚动到 URL 锚点（#m2 之类），两者都会让打开时停在中部/底部。
     在 DOMContentLoaded 之前执行本脚本可避免视觉跳动；同时清掉地址栏锚点，
     避免刷新时再次跳转。注意：本段在无 .module 的页面（如目录页变体）也要执行，
     故不放在任何早退之后。 */
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  window.scrollTo(0, 0);

  /* 键盘守卫：带修饰键的方向键让位浏览器/系统快捷键（Alt+←=后退等）；
     焦点在输入控件或测验/赌注选项容器内时不翻页（v1.11 增选项容器） */
  function navKeyOK(e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return false;
    var t = e.target;
    if (t && t.closest && t.closest(
        'input, textarea, select, [contenteditable], .quiz-opts')) {
      return false;
    }
    return true;
  }

  function go(i, scroll) {
    if (!modules.length) return;
    cur = Math.max(0, Math.min(modules.length - 1, i));
    modules.forEach(function (m, k) { m.classList.toggle('is-active', k === cur); });
    items.forEach(function (a, k) { a.classList.toggle('is-active', k === cur); });
    if (fill) fill.style.width = ((cur + 1) / modules.length * 100) + '%';
    if (text) text.textContent = '模块 ' + (cur + 1) + ' / ' + modules.length;
    if (scroll) {
      /* 程序化平滑滚动期间抑制 IO 联动，避免途经模块被短暂高亮（闪烁） */
      scrolling = true;
      if (scrollTimer) clearTimeout(scrollTimer);
      scrollTimer = setTimeout(function () { scrolling = false; }, 600);
      modules[cur].scrollIntoView({ behavior: 'smooth' });
    }
    /* 长课程：让侧边导航的当前项始终滚入可视区（仅主动跳转时跟随，
       滚动联动 go(...,false) 不触发，避免与主滚动打架） */
    if (scroll && items[cur]) {
      items[cur].scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
    }
  }

  document.addEventListener('keydown', function (e) {
    if (!navKeyOK(e)) return;
    if (e.key === 'ArrowRight') go(cur + 1, true);
    if (e.key === 'ArrowLeft') go(cur - 1, true);
  });
  items.forEach(function (a, k) {
    a.addEventListener('click', function (e) { e.preventDefault(); go(k, true); });
  });

  /* 打开时停在第一页：初始 go(0) 只设置高亮状态，不滚动。
     IntersectionObserver 的首帧回调可能带着浏览器恢复的旧滚动位置，
     因此推迟到下一帧再开始观察，确保刚打开时 cur 锁定为 0。 */
  go(0, false);

  if (modules.length && 'IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      if (scrolling) return;   /* 平滑滚动途中忽略 IO，避免中间模块高亮闪烁 */
      entries.forEach(function (en) {
        if (en.isIntersecting) go(modules.indexOf(en.target), false);
      });
    }, { rootMargin: '-40% 0px -50% 0px' });
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        modules.forEach(function (m) { io.observe(m); });
      });
    });
  }

  /* ---------- 6. 多文件模式：册间跳转（非阻断提示条） ---------- */
  var pager = document.querySelector('.pager');
  if (pager) {
    var prev = pager.querySelector('a[rel="prev"]');
    var next = pager.querySelector('a[rel="next"]');
    var hint = null, hintTimer = null;

    function showHint(target, label) {
      if (!target) return;
      if (!hint) {
        /* 用 DOM API 构建（不用 innerHTML），链接地址走属性赋值，无拼接注入 */
        hint = document.createElement('div');
        hint.className = 'vol-hint';
        hint.setAttribute('role', 'status');   /* 屏幕阅读器可播报提示条出现 */
        hint._label = document.createElement('span');
        hint._label.className = 't-muted';
        hint._go = document.createElement('a');
        hint._go.textContent = '前往 →';
        var idx = document.createElement('a');
        idx.href = 'index.html';
        idx.textContent = '📖 目录';
        hint.appendChild(hint._label);
        hint.appendChild(hint._go);
        hint.appendChild(idx);
        document.body.appendChild(hint);
      }
      hint._label.textContent = label;
      var href = target.getAttribute('href') || '';
      hint._go.href = href;
      hint._go.style.display = href ? '' : 'none';  /* 目标为空时不渲染死链 */
      hint.classList.add('is-shown');
      clearTimeout(hintTimer);
      hintTimer = setTimeout(function () {
        hint.classList.remove('is-shown');   /* 数秒自动消失，不打断学习流 */
      }, 4000);
    }

    document.addEventListener('keydown', function (e) {
      if (!navKeyOK(e)) return;
      /* 翻到本册边界再按 ←/→：只提示，不自动跳转 */
      if (e.key === 'ArrowRight' && next && modules.length &&
          cur === modules.length - 1) {
        showHint(next, '已到本册末尾，下一册：');
      }
      if (e.key === 'ArrowLeft' && prev && modules.length && cur === 0) {
        showHint(prev, '已到本册开头，上一册：');
      }
    });
  }

  /* ===================================================================
     参与式控件引擎（v1.9 新增，全部零依赖、声明式、鼠标 + 键盘可操作）
     -------------------------------------------------------------------
     · §7  执行探照灯 —— 跨文件同步走读：宿主 .flow-scene.spotlight
     · §8  洋葱剥层   —— 数据时间机器：.onion-scene + .onion-data JSON
     · §9  因果赌注   —— 预测式探针：.bet-scene（复用 .quiz-opt）
     · §10 栈塔       —— 调用/返回推演器：.tower-scene + .tower-data JSON
     · §11 分叉沙盘   —— 分支决策实验室：.fork-scene + .fork-data JSON
     共同纪律：不用 innerHTML 拼接；方向键处理器 stopPropagation 不翻模块；
     不执行任何真实代码（沙盘/栈塔只回放预标注数据）；尊重
     prefers-reduced-motion（base.css 全局覆盖 + 关键处主动判断）。
     =================================================================== */

  /* （vizEl/ctrlEl/vizParseData/ctrlParse/vizError/ctrlError 已在 §4 前的
     共享工具区定义——v1.11 合并两代引擎的重复实现，本节不再重复声明） */

  /* ---------- 7. 执行探照灯：把流程图站点映射到跨文件的真实代码行 ----------
     宿主：.flow-scene.spotlight（仍是普通数据流动画，探照灯是叠加层）。
     站点映射属性（写在 .flow-node 上，构成"流程位置 → 代码位置"映射表）：
       data-sp-pair="id1,id2"  目标 .translate-pair 的 id（逗号分隔可多个）
       data-sp-line="2,0"      与上并列的 .tp-line[data-i]（一一对应）
       data-sp-file="a.js · L1-L8 / b.js · L3"  站点说明（用于字幕）
     拖动/键盘 ←/→ 移动探照灯 → 站点 .is-spot + 对应 .tp-line.is-spot
     （可与悬停联动的 is-hot 共存，颜色不同）。 */
  document.querySelectorAll('.flow-scene.spotlight').forEach(function (scene) {
    var svg = scene.querySelector('.flow-svg');
    var lamp = scene.querySelector('.spot-lamp');
    var cap = scene.querySelector('.spot-caption');
    if (!svg || !lamp || !cap) return;
    var nodes = Array.prototype.slice.call(scene.querySelectorAll('.flow-node'));
    if (!nodes.length) return;
    var vb = (svg.getAttribute('viewBox') || '').split(' ');
    var VBW = parseFloat(vb[2]) || 720;
    var cur = -1;

    function nodeCx(n) {
      var c = n.querySelector('circle');
      return c ? (parseFloat(c.getAttribute('cx')) || 0) : 0;
    }
    function nodeLabel(n) {
      var t = n.querySelector('text');
      return t ? t.textContent.trim() : ('站点 ' + (nodes.indexOf(n) + 1));
    }
    /* v1.11：点亮的行/翻译块记在数组里，清除只碰这些元素——不再对整个
       document 跑 3 次 querySelectorAll（拖拽扫过站点时逐站触发，大课件
       上逐次全文档扫描）；赌注的 .is-spot-bet 不在本清单，天然不受影响 */
    var litLines = [], litPairs = [];
    function clearSpot() {
      nodes.forEach(function (n) { n.classList.remove('is-spot'); });
      litLines.forEach(function (p) { p.classList.remove('is-spot'); });
      litPairs.forEach(function (p) { p.classList.remove('is-spotted'); });
      litLines = []; litPairs = [];
    }
    function applySpot(n) {
      clearSpot();
      n.classList.add('is-spot');
      var pairIds = (n.getAttribute('data-sp-pair') || '').split(',');
      var lines = (n.getAttribute('data-sp-line') || '').split(',');
      var file = n.getAttribute('data-sp-file') || '';
      var hit = 0;
      pairIds.forEach(function (pid, k) {
        pid = pid.trim();
        if (!pid) return;
        var pair = document.getElementById(pid);
        if (!pair) return;
        var li = (lines[k] !== undefined ? lines[k] : lines[0]);
        li = (li || '0').trim();
        pair.querySelectorAll('.tp-line[data-i="' + li + '"]')
          .forEach(function (p) { p.classList.add('is-spot'); hit++; litLines.push(p); });
        pair.classList.add('is-spotted');
        litPairs.push(pair);
      });
      cap.textContent = '🔦 站点 ' + (nodes.indexOf(n) + 1) + '/' + nodes.length +
        ' · ' + nodeLabel(n) +
        (hit ? ' → 跨文件点亮 ' + file + ' 的代码行' : '');
    }
    function setLampX(x) { lamp.style.left = (x / VBW * 100) + '%'; }
    function syncAria() {
      lamp.setAttribute('aria-valuenow', String(cur + 1));
      lamp.setAttribute('aria-valuetext',
        cur >= 0 ? nodeLabel(nodes[cur]) + ' · ' +
          (nodes[cur].getAttribute('data-sp-file') || '') : '未点亮');
    }
    /* v1.11 性能：拖拽高频路径 rect 缓存 + rAF 合帧——pointerdown 时读一次
       getBoundingClientRect，pointermove 只记录坐标、每帧至多一次 DOM 写，
       消除"逐 move 读布局 + 写样式"的强制同步布局（与封面光晕同范式） */
    var svgRect = null, dragRaf = null, dragX = null;
    function dragTo(clientX) {
      var r = svgRect || svg.getBoundingClientRect();
      if (!r.width) return;
      var x = (clientX - r.left) / r.width * VBW;
      x = Math.max(0, Math.min(VBW, x));
      var best = nodes[0], bd = Infinity;
      nodes.forEach(function (n) {
        var d = Math.abs(nodeCx(n) - x);
        if (d < bd) { bd = d; best = n; }
      });
      setLampX(x);
      var idx = nodes.indexOf(best);
      if (idx !== cur) { cur = idx; applySpot(best); syncAria(); }
    }
    function dragFrame() {
      dragRaf = null;
      if (dragX !== null) dragTo(dragX);
    }
    lamp.addEventListener('pointerdown', function (e) {
      e.preventDefault();
      try { lamp.setPointerCapture(e.pointerId); } catch (err) {}
      lamp.classList.add('is-drag');
      svgRect = svg.getBoundingClientRect();   /* 拖拽期间缓存布局信息 */
    });
    lamp.addEventListener('pointermove', function (e) {
      if (!lamp.classList.contains('is-drag')) return;
      dragX = e.clientX;
      if (!dragRaf) dragRaf = requestAnimationFrame(dragFrame);
    });
    function endDrag() {
      if (!lamp.classList.contains('is-drag')) return;
      lamp.classList.remove('is-drag');
      if (dragRaf) { cancelAnimationFrame(dragRaf); dragRaf = null; }
      dragX = null; svgRect = null;
      if (cur >= 0) setLampX(nodeCx(nodes[cur]));   /* 松手吸附到站点 */
    }
    lamp.addEventListener('pointerup', endDrag);
    lamp.addEventListener('pointercancel', endDrag);
    lamp.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {   /* v1.11：Esc 熄灭探照灯并清掉全部点亮 */
        e.preventDefault();
        cur = -1;
        clearSpot();
        setLampX(0);
        syncAria();
        cap.textContent = '🔦 探照灯已熄灭——聚焦后按 ←/→ 重新逐站点亮。';
        return;
      }
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      e.preventDefault(); e.stopPropagation();      /* 探照灯步进，不翻模块 */
      var next = cur < 0 ? 0
        : Math.max(0, Math.min(nodes.length - 1,
            cur + (e.key === 'ArrowRight' ? 1 : -1)));
      cur = next;
      setLampX(nodeCx(nodes[cur]));
      applySpot(nodes[cur]);
      syncAria();
    });
    syncAria();   /* v1.11：引擎接管即同步一次 ARIA 状态 */
  });

  /* ---------- 8. 洋葱剥层：同一份数据的纵向演化，剥层掉碎屑 ----------
     契约：.onion-scene 内含 class="onion-data" 的 JSON 数据块（layers
     数组从最外层排到核，每层 name/shape/who/use/crumbs[]）+ 空 .onion-board。
     引擎自动生成同心圆 SVG 与事实面板；点外圈剥一层，被丢弃字段以
     "碎屑"掉进碎屑盘；←/→ 在未剥的圈间移动焦点，Enter/Space 剥层。 */
  document.querySelectorAll('.onion-scene').forEach(function (scene) {
    var data = ctrlParse(scene, 'onion-data');
    var board = scene.querySelector('.onion-board');
    if (!board) return;
    if (!data || !Array.isArray(data.layers) || data.layers.length < 3 ||
        data.layers.length > 6) {
      /* v1.11：补上 >6 上限校验——契约承诺 3–6 层（圈层序号符号也只有
         6 个），超上限此前会静默渲染出 "undefined 第 7 层" 脏文案 */
      ctrlError(scene, '洋葱（层数须为 3–6 层）');
      return;
    }
    var NS = 'http://www.w3.org/2000/svg';
    var CX = 180, CY = 180, OUTR = 158, CORER = 44;
    var n = data.layers.length;
    var step = (OUTR - CORER) / (n - 1);
    var circled = ['①', '②', '③', '④', '⑤', '⑥'];

    function layerFill(k) {   /* k：1（最外）… n（核）——越往里越"生" */
      if (k === 1) return { fill: 'var(--bg-sidebar)', stroke: 'var(--border)' };
      if (k === n) return { fill: 'var(--bg-code)', stroke: 'var(--accent-2)' };
      var deep = k / n;   /* 0..1，越接近核越大 */
      if (deep > 0.75) return { fill: 'color-mix(in srgb, var(--accent) 40%, var(--bg-card))', stroke: 'var(--accent)' };
      return { fill: 'var(--accent-soft)',
               stroke: 'color-mix(in srgb, var(--accent) 45%, transparent)' };
    }

    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'onion-svg');
    svg.setAttribute('viewBox', '0 0 360 360');
    svg.setAttribute('role', 'group');
    svg.setAttribute('aria-label', '数据洋葱：' + n + ' 层同心圆，从外到内依次是 ' +
      data.layers.map(function (L) { return L.name; }).join('、'));

    var rings = [];
    data.layers.forEach(function (L, i) {
      var k = i + 1;
      var r = Math.round(OUTR - (k - 1) * step);
      var g = document.createElementNS(NS, 'g');
      g.setAttribute('class', 'onion-ring');
      g.setAttribute('data-k', String(k));
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      g.setAttribute('aria-label', '第 ' + k + ' 层' +
        (k === 1 ? '（最外）' : k === n ? '（核）' : '') + '：' + L.name +
        '。点它剥到这一层');
      var c = document.createElementNS(NS, 'circle');
      c.setAttribute('cx', CX); c.setAttribute('cy', CY);
      c.setAttribute('r', String(r));
      var fs = layerFill(k);
      c.setAttribute('fill', fs.fill);
      c.setAttribute('stroke', fs.stroke);
      c.setAttribute('stroke-width', '2');
      g.appendChild(c);
      if (k === n) {   /* 核：白字，名字长则拆两行 */
        var name = String(L.name || '');
        if (name.length > 4) {
          [name.slice(0, Math.ceil(name.length / 2)),
           name.slice(Math.ceil(name.length / 2))].forEach(function (part, j) {
            var t = document.createElementNS(NS, 'text');
            t.setAttribute('x', CX); t.setAttribute('y', CY - 4 + j * 16);
            t.setAttribute('text-anchor', 'middle');
            t.setAttribute('class', 'onion-core-tag');
            t.textContent = part;
            g.appendChild(t);
          });
        } else {
          var t1 = document.createElementNS(NS, 'text');
          t1.setAttribute('x', CX); t1.setAttribute('y', CY + 4);
          t1.setAttribute('text-anchor', 'middle');
          t1.setAttribute('class', 'onion-core-tag');
          t1.textContent = name;
          g.appendChild(t1);
        }
      } else {
        var t2 = document.createElementNS(NS, 'text');
        t2.setAttribute('x', CX);
        t2.setAttribute('y', CY - r + 20);
        t2.setAttribute('text-anchor', 'middle');
        t2.setAttribute('class', 'onion-ring-tag');
        t2.textContent = circled[k - 1] + ' ' + L.name + (k === 1 ? '（最终形态）' : '');
        g.appendChild(t2);
      }
      rings.push(g);
      svg.appendChild(g);
    });

    /* 事实面板 */
    var panel = ctrlEl('div', 'onion-panel');
    var countEl = ctrlEl('div', 'onion-count t-muted', '已剥 0 / ' + (n - 1) + ' 层');
    countEl.setAttribute('aria-live', 'polite');
    var layerEl = ctrlEl('div', 'onion-layer t-h3', '');
    var facts = document.createElement('dl');
    facts.className = 'onion-facts';
    var shapeEl = ctrlEl('dd', 't-code', '');
    var whoEl = ctrlEl('dd', '', '');
    var useEl = ctrlEl('dd', '', '');
    [['形态', shapeEl], ['谁动的手', whoEl], ['用来干嘛', useEl]].forEach(function (kv) {
      var dt = ctrlEl('dt', '', kv[0]);
      facts.appendChild(dt); facts.appendChild(kv[1]);
    });
    var tray = ctrlEl('div', 'onion-tray');
    tray.appendChild(ctrlEl('div', 'onion-tray-title t-muted',
      '🥀 碎屑盘（剥层时被丢弃的字段）'));
    var crumbBox = ctrlEl('div', 'onion-crumbs');
    crumbBox.appendChild(ctrlEl('span', 't-muted', '— 还没剥 —'));
    tray.appendChild(crumbBox);
    var resetBtn = ctrlEl('button', 'viz-btn onion-reset', '↺ 重新包上');
    resetBtn.type = 'button';
    panel.appendChild(countEl);
    panel.appendChild(layerEl);
    panel.appendChild(facts);
    panel.appendChild(tray);
    panel.appendChild(resetBtn);
    board.appendChild(svg);
    board.appendChild(panel);

    var peeled = 0;   /* 已剥掉的层数（外层圈数） */
    function render() {
      rings.forEach(function (g, i) {
        var k = i + 1;
        var off = k <= peeled;
        g.classList.toggle('is-peeled', off);
        g.setAttribute('tabindex', off ? '-1' : '0');
      });
      var vis = Math.min(peeled, n - 1);   /* 当前裸露在外的层 */
      var L = data.layers[vis];
      countEl.textContent = '已剥 ' + peeled + ' / ' + (n - 1) + ' 层';
      layerEl.textContent = '现在看到：第 ' + (vis + 1) + ' 层 · ' + L.name;
      shapeEl.textContent = L.shape || '';
      whoEl.textContent = L.who || '';
      useEl.textContent = L.use || '';
    }
    function dropCrumbs(from, to) {
      var ph = crumbBox.querySelector('.t-muted');
      if (ph) ph.remove();
      for (var p = from + 1; p <= to; p++) {
        (data.layers[p - 1].crumbs || []).forEach(function (c) {
          crumbBox.appendChild(ctrlEl('span', 'onion-crumb', c));
        });
      }
    }
    function peelTo(k) {
      var target = Math.max(peeled, Math.min(k, n - 1));
      if (target === peeled) return;
      dropCrumbs(peeled, target);
      peeled = target;
      render();
    }
    rings.forEach(function (g) {
      g.addEventListener('click', function () {
        peelTo(+g.getAttribute('data-k'));
      });
      g.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          peelTo(+g.getAttribute('data-k'));
        }
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
          e.preventDefault(); e.stopPropagation();  /* 换圈，不翻模块 */
          var d = e.key === 'ArrowRight' ? 1 : -1;
          var k = +g.getAttribute('data-k');
          for (var m = k + d; m >= 1 && m <= rings.length; m += d) {
            var t = rings[m - 1];
            if (t.getAttribute('tabindex') !== '-1') { t.focus(); break; }
          }
        }
      });
    });
    resetBtn.addEventListener('click', function () {
      peeled = 0;
      crumbBox.textContent = '';
      crumbBox.appendChild(ctrlEl('span', 't-muted', '— 还没剥 —'));
      render();
    });
    render();
  });

  /* ---------- 9. 因果赌注：先押注、再运行揭晓并点亮真实代码 ----------
     契约：.bet-scene 内含 .quiz-opts 容器 + 若干 .quiz-opt（带
     data-bet-correct / data-bet-why，注意与测验的 data-correct 不同名，
     互不干扰）+ .bet-run 按钮 + .quiz-fb.bet-fb 反馈条。
     可选 data-bet-pair="翻译块id"：揭晓后点亮该翻译块全部代码行并滚过去（v1.11 起用独立类 .is-spot-bet/.is-betted，与探照灯分离；揭晓后焦点移入反馈条；支持"↻ 再押一注"重开）。 */
  document.querySelectorAll('.bet-scene').forEach(function (bet) {
    var opts = Array.prototype.slice.call(bet.querySelectorAll('.quiz-opt'));
    var run = bet.querySelector('.bet-run');
    var fb = bet.querySelector('.bet-fb');
    if (!opts.length || !run) return;
    if (fb) fb.setAttribute('role', 'status');
    var optsBox = bet.querySelector('.quiz-opts');
    if (optsBox) optsKeyboard(optsBox);
    var picked = null, done = false;
    var litPair = null;   /* 揭晓点亮的翻译块，重押时清理（v1.11） */
    /* 重开赌局：清选项状态、清 .is-spot-bet/.is-betted 点亮、焦点回第一项 */
    function resetBet() {
      done = false; picked = null;
      opts.forEach(function (b) {
        b.disabled = false;
        b.classList.remove('is-sel', 'is-right', 'is-wrong');
        b.tabIndex = -1;
      });
      run.disabled = true;
      if (litPair) {
        litPair.querySelectorAll('.tp-line.is-spot-bet')
          .forEach(function (p) { p.classList.remove('is-spot-bet'); });
        litPair.classList.remove('is-betted');
        litPair = null;
      }
      if (fb) {
        fb.hidden = true;
        fb.textContent = '';
        fb.classList.remove('is-right', 'is-wrong');
      }
      var old = bet.querySelector('.bet-retry');
      if (old) old.remove();
      var first = bet.querySelector('.quiz-opt');
      if (first) first.focus();
    }
    opts.forEach(function (b) {
      b.type = 'button';
      b.addEventListener('click', function () {
        if (done) return;
        picked = b;
        opts.forEach(function (x) { x.classList.toggle('is-sel', x === b); });
        run.disabled = false;
        if (fb) fb.hidden = true;
      });
    });
    run.addEventListener('click', function () {
      if (!picked || done) return;
      done = true;
      var ok = picked.getAttribute('data-bet-correct') === 'true';
      opts.forEach(function (b) {
        b.disabled = true;
        if (b.getAttribute('data-bet-correct') === 'true') b.classList.add('is-right');
        else if (b === picked) b.classList.add('is-wrong');
      });
      run.disabled = true;
      var pairId = bet.getAttribute('data-bet-pair');
      var pair = pairId ? document.getElementById(pairId) : null;
      if (pair) {
        litPair = pair;
        /* v1.11：独立类 .is-spot-bet/.is-betted——探照灯的 clearSpot()
           只清自己的 .is-spot/.is-spotted，赌注答案不再被扫灭 */
        pair.querySelectorAll('.tp-line')
          .forEach(function (p) { p.classList.add('is-spot-bet'); });
        pair.classList.add('is-betted');
        var smooth = true;
        try {
          smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        } catch (e) {}
        setTimeout(function () {
          pair.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto',
                                block: 'nearest' });
        }, 80);
      }
      if (fb) {
        fb.textContent = (ok ? '🎯 押中了！' : '🧐 押错了 — ') +
          (picked.getAttribute('data-bet-why') || '') +
          (pair ? ' 👇 答案已在真实代码里点亮。' : '');
        fb.classList.toggle('is-right', ok);
        fb.classList.toggle('is-wrong', !ok);
        fb.hidden = false;
      }
      focusFb(fb);   /* 焦点移入反馈条：对错与解释立即可读（v1.11） */
      /* 再押一注（v1.11）：赌注是"预测-验证"练习，押错也能重开，
         与测验的"↻ 重试"对齐 */
      if (!bet.querySelector('.bet-retry')) {
        var retry = document.createElement('button');
        retry.type = 'button';
        retry.className = 'bet-retry btn-ghost';
        retry.textContent = '↻ 再押一注';
        retry.addEventListener('click', resetBet);
        bet.appendChild(retry);
      }
    });
  });

  /* ---------- 10. 栈塔：调用/返回推演器（预标注脚本驱动的 push/pop） ----------
     契约：.tower-scene 内含 class="tower-data" 的 JSON 数据块 + 空
     .tower-stack + 空 .tower-side + .tower-controls（.tower-push /
     .tower-pop / .tower-reset 按钮）。JSON：
       base（地基说明）/ collect{title,empty}（返回值收集盘，可省）/
       pushLabel、popLabel（按钮动词，默认"调用/返回"）/ script[]
     script 条目：act:"push" 时 fn/depth/badge?/hyp?/args?/locals?/
     check?/next?/ret?/note；act:"pop" 时 res?（收到的返回值）/note。
     学习者亲手 push/pop；帧间 ←/→/↑/↓ 移动焦点，Enter 展开局部变量。 */
  document.querySelectorAll('.tower-scene').forEach(function (scene) {
    var data = ctrlParse(scene, 'tower-data');
    var stack = scene.querySelector('.tower-stack');
    var side = scene.querySelector('.tower-side');
    var pushBtn = scene.querySelector('.tower-push');
    var popBtn = scene.querySelector('.tower-pop');
    var resetBtn = scene.querySelector('.tower-reset');
    if (!stack || !pushBtn || !popBtn) return;
    if (!data || !Array.isArray(data.script) || !data.script.length) {
      ctrlError(scene, '栈塔');
      return;
    }
    var SCRIPT = data.script;
    var chipsBox = null, note = null;
    if (side) {
      if (data.collect) {
        var res = ctrlEl('div', 'tower-res');
        res.appendChild(ctrlEl('div', 't-h3', data.collect.title || '返回值收集盘'));
        chipsBox = ctrlEl('div', 'tower-res-chips');
        chipsBox.appendChild(ctrlEl('span', 't-muted',
          data.collect.empty || '（还没有收集到返回值）'));
        res.appendChild(chipsBox);
        side.appendChild(res);
      }
      note = ctrlEl('p', 'tower-note t-muted', '每一步会发生什么，在这里说明。');
      note.setAttribute('aria-live', 'polite');
      side.appendChild(note);
    }
    if (data.base) stack.setAttribute('data-base', data.base);

    var idx = 0, frames = [], pushCount = 0;
    var PUSH = data.pushLabel || '调用';
    var POP = data.popLabel || '返回';
    var FIELD_LABELS = [['args', '参数'], ['locals', '局部变量'],
                        ['check', '约束检查'], ['next', '下一步调谁'],
                        ['ret', '返回给谁']];
    function say(t) { if (note) note.textContent = t; }
    function clearEmpty() {
      var e = stack.querySelector('.tower-empty');
      if (e) e.remove();
    }
    function addResChip(v) {
      if (!chipsBox) return;
      var ph = chipsBox.querySelector('.t-muted');
      if (ph) ph.remove();
      chipsBox.appendChild(ctrlEl('span', 'tower-res-chip', v));
    }
    function updateControls() {
      var ev = SCRIPT[idx];
      if (ev && ev.act === 'push') {
        pushBtn.disabled = false;
        pushBtn.textContent = '▶ ' + PUSH + (ev.fn ? ' ' + ev.fn : '') +
          (ev.hyp ? ' · ' + ev.hyp : '');
        popBtn.disabled = frames.length === 0;
        popBtn.textContent = '◀ ' + POP;
      } else if (ev && ev.act === 'pop') {
        pushBtn.disabled = true;
        pushBtn.textContent = '▶ ' + PUSH + '（下一步是' + POP + '）';
        popBtn.disabled = false;
        popBtn.textContent = '◀ ' + POP + (ev.res ? '（收 ' + ev.res + '）' : '');
      } else {
        pushBtn.disabled = true;
        pushBtn.textContent = '▶ ' + PUSH;
        popBtn.disabled = frames.length === 0;
        popBtn.textContent = '◀ ' + POP;
      }
    }
    function makeFrame(ev) {
      var f = ctrlEl('button', 'tower-frame');
      f.type = 'button';
      f.setAttribute('aria-expanded', 'false');
      f.style.setProperty('--fd',
        (ev.depth === 1 || ev.depth === undefined) ? 'var(--accent)' : 'var(--accent-2)');
      var head = ctrlEl('div', 'tower-frame-head');
      head.appendChild(ctrlEl('span', 'tower-frame-name',
        (ev.fn || 'f') + (ev.depth !== undefined ? ' · depth ' + ev.depth : '')));
      head.appendChild(ctrlEl('span', 'tower-frame-badge',
        ev.badge || '第 ' + (++pushCount) + ' 次进栈'));
      if (ev.hyp) head.appendChild(ctrlEl('span', 'tower-frame-hyp', ev.hyp));
      f.appendChild(head);
      var body = ctrlEl('div', 'tower-frame-body');
      var dl = document.createElement('dl');
      FIELD_LABELS.forEach(function (kv) {
        if (ev[kv[0]] === undefined || ev[kv[0]] === '') return;
        dl.appendChild(ctrlEl('dt', '', kv[1]));
        dl.appendChild(ctrlEl('dd', '', ev[kv[0]]));
      });
      body.appendChild(dl);
      f.appendChild(body);
      f.addEventListener('click', function () {
        var open = f.classList.toggle('is-open');
        f.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      f.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft' ||
            e.key === 'ArrowUp' || e.key === 'ArrowDown') {
          e.preventDefault(); e.stopPropagation();  /* 帧间移动，不翻模块 */
          var d = (e.key === 'ArrowRight' || e.key === 'ArrowUp') ? 1 : -1;
          var i = frames.indexOf(f) + d;
          if (i >= 0 && i < frames.length) frames[i].focus();
        }
      });
      return f;
    }
    function doPush() {
      var ev = SCRIPT[idx];
      if (!ev || ev.act !== 'push') {
        say('这一步不是' + PUSH + '——按「◀ ' + POP + '」把栈顶弹出去。');
        return;
      }
      clearEmpty();
      var f = makeFrame(ev);
      f.classList.add('is-new');
      stack.appendChild(f);
      frames.push(f);
      say(ev.note || '');
      idx++;
      updateControls();
    }
    function doPop() {
      var ev = SCRIPT[idx];
      if (!frames.length) { say('栈已经是空的了。'); return; }
      if (!ev || ev.act !== 'pop') {
        say('这一步不是' + POP + '——按「▶ ' + PUSH + '」继续压栈。');
        return;
      }
      var f = frames.pop();
      f.classList.add('is-pop');
      setTimeout(function () { f.remove(); }, 240);
      if (ev.res) addResChip(ev.res);
      say(ev.note || '');
      idx++;
      /* v1.11：弹空后恢复空栈提示——否则栈区只剩 data-base 地基注释，
         学习者看不出"栈已空、可以重新压" */
      if (!frames.length) {
        stack.appendChild(ctrlEl('div', 'tower-empty',
          '栈是空的——点下面的「' + PUSH + '」继续压入。'));
      }
      updateControls();
    }
    pushBtn.addEventListener('click', doPush);
    popBtn.addEventListener('click', doPop);
    function resetTower() {
      idx = 0;
      frames.forEach(function (f) { f.remove(); });
      frames = []; pushCount = 0;
      clearEmpty();   /* v1.11：防重复——弹空恢复的提示也要清掉再重建 */
      if (chipsBox) {
        chipsBox.textContent = '';
        chipsBox.appendChild(ctrlEl('span', 't-muted',
          (data.collect && data.collect.empty) || '（还没有收集到返回值）'));
      }
      stack.appendChild(ctrlEl('div', 'tower-empty',
        '栈是空的——点下面的「' + PUSH + '」压入第一帧。'));
      say('每一步会发生什么，在这里说明。');
      updateControls();
    }
    if (resetBtn) resetBtn.addEventListener('click', resetTower);
    resetTower();
  });

  /* ---------- 11. 分叉沙盘：拖令牌过预标注的岔路口（不执行真实代码） ----------
     契约：.fork-scene 内含 class="fork-data" 的 JSON 数据块 + 空
     .fork-board。引擎自动生成：参数区（滑块/单选组）、岔路 SVG（入口轨道
     + 闸门 + 每分支一条滑道）、分支结果卡、预标注代码行、字幕与投放按钮。
     JSON：
       gate（闸门标签）/ entryTag（入口标签）/ tokenPrefix / goLabel
       params[]：{id,label,type:"range",min,max,step,value,fmt} 或
                 {id,label,type:"radio",options:[{value,label}]}
       branches[]：{id,title,cond,when:{参数id:"值|集合|*"},fx[],note,code[]}
     路由规则：从上到下取第一个 when 全部命中的分支（when 缺省 = 兜底），
     值只做字符串精确/集合匹配——学习者改参数即可走另一条路，全程不执行
     任何真实代码。键盘：令牌 ←/→ 推移，参数为原生表单控件。 */
  document.querySelectorAll('.fork-scene').forEach(function (scene) {
    var data = ctrlParse(scene, 'fork-data');
    var board = scene.querySelector('.fork-board');
    if (!board) return;
    if (!data || !Array.isArray(data.branches) || data.branches.length < 2) {
      ctrlError(scene, '沙盘');
      return;
    }
    var NS = 'http://www.w3.org/2000/svg';
    var branches = data.branches.slice(0, 4);   /* 分支数 2–4 */
    var nb = branches.length;
    var VBW = 720, VBH = 300;
    var ENTRYX = 30, FORKX = 340, ENDX = 590, RAILY = 150, CTLX = 470;
    var GAP = nb >= 4 ? 88 : 94;
    var OUTY = {};
    branches.forEach(function (b, i) { OUTY[b.id] = RAILY + (i - (nb - 1) / 2) * GAP; });
    var t = 0, settled = false, animRaf = null, litTimers = [];
    var values = {};

    /* --- 参数区 --- */
    var paramsBox = ctrlEl('div', 'fork-params');
    var inputs = {};
    (data.params || []).forEach(function (p) {
      if (p.type === 'radio') {
        var fs = document.createElement('fieldset');
        fs.className = 'fork-param';
        var legend = document.createElement('legend');
        legend.textContent = p.label || p.id;
        fs.appendChild(legend);
        (p.options || []).forEach(function (o, i) {
          var lab = ctrlEl('label', '');
          var r = document.createElement('input');
          r.type = 'radio';
          r.name = 'fork-' + p.id;
          r.value = String(o.value);
          if (i === 0) r.checked = true;
          lab.appendChild(r);
          lab.appendChild(document.createTextNode(' ' + o.label));
          fs.appendChild(lab);
        });
        paramsBox.appendChild(fs);
        inputs[p.id] = { kind: 'radio', el: fs };
      } else {   /* range 滑块 */
        var wrap = ctrlEl('label', 'fork-param', '');
        wrap.appendChild(document.createTextNode(p.label || p.id));
        var s = document.createElement('input');
        s.type = 'range';
        s.min = p.min !== undefined ? p.min : 0;
        s.max = p.max !== undefined ? p.max : 100;
        s.step = p.step !== undefined ? p.step : 1;
        s.value = p.value !== undefined ? p.value : s.min;
        s.setAttribute('aria-label', (p.label || p.id) + '（用左右方向键调整）');
        wrap.appendChild(s);
        var out = ctrlEl('output', 'fork-param-output t-code', '');
        wrap.appendChild(out);
        paramsBox.appendChild(wrap);
        inputs[p.id] = { kind: 'range', el: s, out: out, fmt: p.fmt || '' };
      }
    });
    board.appendChild(paramsBox);

    /* --- 岔路 SVG --- */
    var stage = ctrlEl('div', 'fork-stage');
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + VBW + ' ' + VBH);
    svg.setAttribute('width', '100%');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', '分岔图：入口轨道、' + (data.gate || '闸门') +
      '、' + nb + ' 条分支滑道');
    var rail = document.createElementNS(NS, 'path');
    rail.setAttribute('class', 'fork-rail');
    rail.setAttribute('d', 'M' + ENTRYX + ',' + RAILY + ' L' + (FORKX - 10) + ',' + RAILY);
    svg.appendChild(rail);
    var chutes = {};
    branches.forEach(function (b) {
      var y = OUTY[b.id];
      var ch = document.createElementNS(NS, 'path');
      ch.setAttribute('class', 'fork-chute');
      ch.setAttribute('d', 'M' + (FORKX + 10) + ',' + RAILY +
        ' Q' + CTLX + ',' + y + ' ' + ENDX + ',' + y);
      svg.appendChild(ch);
      chutes[b.id] = ch;
      var tag = document.createElementNS(NS, 'text');
      tag.setAttribute('class', 'fork-out-tag');
      tag.setAttribute('x', String(ENDX + 8));
      tag.setAttribute('y', String(y + 4));
      tag.textContent = b.title;   /* 滑道末端短标签 = 分支标题 */
      svg.appendChild(tag);
    });
    var gate = document.createElementNS(NS, 'g');
    gate.setAttribute('class', 'fork-gate');
    var gc = document.createElementNS(NS, 'circle');
    gc.setAttribute('cx', String(FORKX)); gc.setAttribute('cy', String(RAILY));
    gc.setAttribute('r', '22');
    gate.appendChild(gc);
    var gt = document.createElementNS(NS, 'text');
    gt.setAttribute('x', String(FORKX));
    gt.setAttribute('y', String(RAILY + 42));
    gt.setAttribute('text-anchor', 'middle');
    gt.textContent = data.gate || '岔路口';
    gate.appendChild(gt);
    svg.appendChild(gate);
    var entryTag = document.createElementNS(NS, 'text');
    entryTag.setAttribute('class', 'fork-out-tag');
    entryTag.setAttribute('x', String(ENTRYX));
    entryTag.setAttribute('y', String(RAILY - 22));
    entryTag.textContent = data.entryTag || '输入令牌';
    svg.appendChild(entryTag);
    stage.appendChild(svg);

    var token = ctrlEl('button', 'fork-token');
    token.type = 'button';
    token.setAttribute('role', 'slider');
    token.setAttribute('aria-label',
      '输入令牌：左右方向键推移，或点「' + (data.goLabel || '投放令牌') +
      '」让它滑进当前参数对应的分支');
    token.setAttribute('aria-orientation', 'horizontal');
    token.setAttribute('aria-valuemin', '0');
    token.setAttribute('aria-valuemax', '100');
    token.setAttribute('aria-valuenow', '0');
    stage.appendChild(token);
    board.appendChild(stage);

    /* --- 分支结果卡 --- */
    var outs = ctrlEl('div', 'fork-outs');
    branches.forEach(function (b) {
      var o = ctrlEl('div', 'fork-out');
      o.setAttribute('data-b', b.id);
      o.appendChild(ctrlEl('p', 'fork-out-t', b.title));
      if (b.cond) o.appendChild(ctrlEl('p', 'fork-out-cond t-muted', b.cond));
      var fx = ctrlEl('div', 'fork-fx');
      (b.fx || []).forEach(function (c) {
        fx.appendChild(ctrlEl('span', 'fork-fx-chip', c));
      });
      o.appendChild(fx);
      if (b.note) o.appendChild(ctrlEl('p', 'fork-out-note t-muted', b.note));
      outs.appendChild(o);
    });
    board.appendChild(outs);

    /* --- 预标注代码 --- */
    var hasCode = branches.some(function (b) { return (b.code || []).length; });
    if (hasCode) {
      var codeBox = ctrlEl('div', 'fork-code t-code');
      codeBox.setAttribute('aria-label', '对应的真实分支代码（预标注）');
      branches.forEach(function (b) {
        (b.code || []).forEach(function (line) {
          var l = ctrlEl('div', 'fork-code-line', line);
          l.setAttribute('data-b', b.id);
          codeBox.appendChild(l);
        });
      });
      board.appendChild(codeBox);
    }

    var cap = ctrlEl('div', 'fork-caption t-muted',
      '调整参数或拖动令牌，看它落进哪条分支。');
    cap.setAttribute('aria-live', 'polite');
    board.appendChild(cap);
    var actions = ctrlEl('div', 'bet-actions');
    var goBtn = ctrlEl('button', 'viz-btn fork-go', data.goLabel || '▶ 投放令牌');
    goBtn.type = 'button';
    actions.appendChild(goBtn);
    board.appendChild(actions);

    /* --- 路由：第一个 when 全命中的分支（缺 when = 兜底） --- */
    function readValues() {
      Object.keys(inputs).forEach(function (id) {
        var inp = inputs[id];
        if (inp.kind === 'radio') {
          var r = inp.el.querySelector('input:checked');
          values[id] = r ? r.value : '';
        } else {
          values[id] = String(inp.el.value);
        }
      });
    }
    function specMatch(spec, v) {
      if (spec === '*' || spec === undefined) return true;
      return String(spec).split('|').indexOf(v) !== -1;
    }
    function branch() {
      for (var i = 0; i < branches.length; i++) {
        var when = branches[i].when || {};
        var ok = true;
        var keys = Object.keys(when);
        if (keys.length === 0 && i < branches.length - 1) {
          continue;   /* 空 when 只允许兜底位（最后一个）；非最后视为不匹配 */
        }
        for (var j = 0; j < keys.length; j++) {
          if (values[keys[j]] === undefined || !specMatch(when[keys[j]], values[keys[j]])) {
            ok = false; break;
          }
        }
        if (ok) return branches[i].id;
      }
      return branches[branches.length - 1].id;   /* 防御：兜底走最后一条 */
    }

    /* --- 令牌位置：入口轨道 → 命中分支的滑道（贝塞尔） --- */
    function pos(curT, b) {
      if (curT <= 0.42) {
        var u = curT / 0.42;
        return { x: ENTRYX + (FORKX - ENTRYX) * u, y: RAILY };
      }
      var u = (curT - 0.42) / 0.58;
      var iu = 1 - u;
      var ey = OUTY[b];
      return {
        x: iu * iu * FORKX + 2 * iu * u * CTLX + u * u * ENDX,
        y: iu * iu * RAILY + 2 * iu * u * ey + u * u * ey
      };
    }
    function clearLit() {
      litTimers.forEach(clearTimeout);
      litTimers = [];
      scene.querySelectorAll('.fork-out').forEach(function (o) {
        o.classList.remove('is-on');
      });
      scene.querySelectorAll('.fork-fx-chip').forEach(function (c) {
        c.classList.remove('is-lit');
      });
      scene.querySelectorAll('.fork-code-line').forEach(function (l) {
        l.classList.remove('is-on');
      });
    }
    function settle(b) {
      if (settled) return;
      settled = true;
      token.classList.add('is-done');
      var out = scene.querySelector('.fork-out[data-b="' + b + '"]');
      if (out) {
        out.classList.add('is-on');
        Array.prototype.forEach.call(
          out.querySelectorAll('.fork-fx-chip'), function (c, i) {
            litTimers.push(setTimeout(function () {
              c.classList.add('is-lit');
            }, 140 * i));
          });
      }
      scene.querySelectorAll('.fork-code-line[data-b="' + b + '"]')
        .forEach(function (l) { l.classList.add('is-on'); });
      var br = branches.filter(function (x) { return x.id === b; })[0] || {};
      cap.textContent = '令牌落进：' + br.title + ' —— 沿途被改写的字段见高亮芯片。';
    }
    function unsettle(hint) {
      if (settled) {
        settled = false;
        token.classList.remove('is-done');
        clearLit();
      }
      if (cap && hint) cap.textContent = hint;
    }
    var lastAriaPct = -1;
    function place(curT) {
      var b = branch();
      var p = pos(curT, b);
      token.style.left = (p.x / VBW * 100) + '%';
      token.style.top = (p.y / VBH * 100) + '%';
      /* v1.11：aria-valuenow 节流——只在整百分比变化时写 DOM，
         拖拽/自动投放的高频帧不再逐帧 setAttribute */
      var pct = Math.round(curT * 100);
      if (pct !== lastAriaPct) {
        lastAriaPct = pct;
        token.setAttribute('aria-valuenow', String(pct));
      }
      if (curT >= 0.97) settle(b); else unsettle();
    }
    function route(hint) {
      readValues();
      var b = branch();
      Object.keys(chutes).forEach(function (k) {
        chutes[k].classList.toggle('is-on', k === b);
      });
      unsettle(hint);
      place(t);
    }
    function syncOutputs() {
      var p0 = (data.params || [])[0];
      if (p0 && inputs[p0.id] && inputs[p0.id].kind === 'range') {
        var inp = inputs[p0.id];
        if (inp.out) inp.out.textContent = inp.el.value + inp.fmt;
        token.textContent = (data.tokenPrefix || '📦') + ' ' + inp.el.value + inp.fmt;
      } else {
        token.textContent = data.tokenPrefix || '📦';
      }
      Object.keys(inputs).forEach(function (id) {
        if (inputs[id].kind === 'range' && inputs[id].out) {
          inputs[id].out.textContent = inputs[id].el.value + inputs[id].fmt;
        }
      });
    }
    Object.keys(inputs).forEach(function (id) {
      var inp = inputs[id];
      if (inp.kind === 'radio') {
        inp.el.addEventListener('change', function () {
          route('参数变了：令牌改走另一条路——再投一次试试。');
          syncOutputs();
        });
      } else {
        inp.el.addEventListener('input', function () {
          syncOutputs();
          route('参数变了：令牌改走另一条路——再投一次试试。');
        });
      }
    });

    /* --- 拖拽：水平位移映射到路程 t（v1.11：rect 缓存 + rAF 合帧，
       消除逐 move 读布局 + 写样式的强制同步布局） --- */
    var tokRect = null, tokRaf = null, tokX = null;
    token.addEventListener('pointerdown', function (e) {
      e.preventDefault();
      if (animRaf) { cancelAnimationFrame(animRaf); animRaf = null; }
      try { token.setPointerCapture(e.pointerId); } catch (err) {}
      token.classList.add('is-drag');
      tokRect = token.parentElement.getBoundingClientRect();
    });
    function tokFrame() {
      tokRaf = null;
      if (tokX === null || !tokRect) return;
      var r = tokRect;
      var px = (tokX - r.left) / r.width;
      t = Math.max(0, Math.min(1, px));
      place(t);
    }
    token.addEventListener('pointermove', function (e) {
      if (!token.classList.contains('is-drag')) return;
      tokX = e.clientX;
      if (!tokRaf) tokRaf = requestAnimationFrame(tokFrame);
    });
    function endDrag() {
      token.classList.remove('is-drag');
      if (tokRaf) { cancelAnimationFrame(tokRaf); tokRaf = null; }
      tokX = null; tokRect = null;
    }
    token.addEventListener('pointerup', endDrag);
    token.addEventListener('pointercancel', endDrag);
    token.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault(); e.stopPropagation();  /* 推移令牌，不翻模块 */
        t = Math.max(0, Math.min(1, t + (e.key === 'ArrowRight' ? 0.1 : -0.1)));
        place(t);
      }
    });
    goBtn.addEventListener('click', function () {
      if (animRaf) cancelAnimationFrame(animRaf);
      var reduce = false;
      try {
        reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      } catch (e) {}
      if (reduce) { t = 1; place(1); return; }
      var from = t >= 0.97 ? 0 : t;
      var t0 = null, DUR = 850;
      function stepAnim(ts) {
        if (t0 === null) t0 = ts;
        var k = Math.min(1, (ts - t0) / DUR);
        var e2 = 1 - Math.pow(1 - k, 3);   /* ease-out */
        t = from + (1 - from) * e2;
        place(t);
        if (k < 1) animRaf = requestAnimationFrame(stepAnim);
        else animRaf = null;
      }
      animRaf = requestAnimationFrame(stepAnim);
    });
    syncOutputs();
    route();
  });

  /* ===================================================================
     20. 调用图（call-graph）—— 把结构事实渲染成一张节点-边图（v1.13.1）
     -------------------------------------------------------------------
     宿主：.callgraph-scene + script(type=application/json) 的 callgraph-data 数据块
     数据契约（闭集，见 references/interactive-elements.md §14）：
       nodes[{id,label,kind,file,line}]
       links[{from,to,count,confidence,file,line,declared,back}]
       confidence 为闭集 verified|inferred 且**不可缺省**；verified 边必须带
       发起行 file:line（诚实边不允许含糊）。
     定位：探照灯讲"跨文件怎么走"、栈塔讲"运行时纵深"，调用图讲"整体形状"——
     谁调谁、谁被最多人调、哪些边只是推断。
     确定性：布局是纯函数，不依赖时间/随机数/DOM 测量顺序——同一份 JSON 必然
     产出同一张图（长标签截断用字符推进宽度估算而非 measureText：后者随字体
     是否就绪而变，是"同数据不同图"的源头）。
     layout algorithm adapted from CodeGraph (MIT, ui/src/lib/map-model.ts)
     — zero-dependency reimplementation
     =================================================================== */

  /* 20a. 几何常量（规格 §3.5；同一门课程内不逐图变化，小屏由 CSS 等比缩小） */
  var CG_LAYER_GAP = 74;    /* 层间垂直间距 */
  var CG_NODE_H = 40;       /* 节点盒高 */
  var CG_MIN_COL_W = 96;    /* 横向最小占位 */
  var CG_MAX_COL_W = 210;   /* 盒宽上限：更长的标签走截断 + title 全名 */
  var CG_NODE_GAP = 34;     /* 同层相邻节点间距（照 CodeGraph 的 NODE_GAP） */
  var CG_MIN_SLOT = 230;    /* 每节点在本层的最小横向份额：稀疏层也铺开，不挤成一团 */
  var CG_PADDING = 32;      /* 画布内边距（规格 §3.5 定为 32，CodeGraph 为 44） */
  var CG_GLYPH_COL = 30;    /* glyph 槽宽（glyph 居中于 17，标签从 30 起） */
  var CG_VBW_MIN = 480;     /* 画布下限：小图不至于被拉成巨字 */
  var CG_DECLARED_COVERAGE = 0.4;   /* declared 覆盖率下限，低于它回落 count（照 CodeGraph） */
  var CG_KIND_GLYPH = {
    'entry': '▶', 'function': 'ƒ', 'method': '◇',
    'class': '◫', 'module': '▦', 'file': '▤'
  };

  /* 字符推进宽度估算：全角/CJK 12px、半角 6.6px、代理对（emoji 等）14px */
  function cgCharW(s, i) {
    var c = s.charCodeAt(i);
    if (c >= 0xD800 && c <= 0xDBFF) return [14, 2];
    if ((c >= 0x1100 && c <= 0x115F) || (c >= 0x2E80 && c <= 0xA4CF)
        || (c >= 0xAC00 && c <= 0xD7A3) || (c >= 0xF900 && c <= 0xFAFF)
        || (c >= 0xFE30 && c <= 0xFE6F) || (c >= 0xFF00 && c <= 0xFF60)
        || (c >= 0xFFE0 && c <= 0xFFE6)) return [12, 1];
    return [6.6, 1];
  }
  function cgTextW(s) {
    var w = 0;
    for (var i = 0; i < s.length;) {
      var r = cgCharW(s, i);
      w += r[0]; i += r[1];
    }
    return w;
  }
  /* 超过盒宽按估算宽度截断为 …（全名由 title 与事实面板保留，禁止静默丢信息） */
  function cgElide(label, maxW) {
    if (cgTextW(label) <= maxW) return { text: label, cut: false };
    var ellW = cgTextW('…');
    var out = '', w = 0, i = 0;
    while (i < label.length) {
      var r = cgCharW(label, i);
      if (w + r[0] + ellW > maxW) break;
      out += label.substr(i, r[1]); w += r[0]; i += r[1];
    }
    return { text: out + '…', cut: true };
  }
  function cgNum(v) { return Math.round(v * 100) / 100; }
  /* 线宽：min(6, 1 + log2(count) × 0.7)——承载 700 个调用点的边明显更粗，
     但不会粗一百倍（规格 §4.2） */
  function cgStrokeW(count) {
    var c = (typeof count === 'number' && count >= 1) ? count : 1;
    return String(cgNum(Math.min(6, 1 + (Math.log(c) / Math.LN2) * 0.7)));
  }

  /* 20b. 布局（纯函数、零 DOM）
     对照 CodeGraph `ui/src/lib/map-model.ts` 的 buildMapLayout 逐步重实现：
     ① 两环互指消解 → ② 最长路径分层（**单位权重**）→ ③ 重心法 3 轮扫 →
     ④ 落位 → ⑤ 端口散布。注意 declared/count 在参照实现里决定的是"两环互指
     时谁算回边"（weightOf + 2-cycle break），**不是层跨**——照做，否则一条
     700 次调用的边会把画布撑成 700 层。
     所有查表用 Object.create(null)：节点 id 可能是 `constructor` 这类原型键。 */
  /* 20b-0. 同尾名守卫：文件级/模块级节点的 id 是路径形态，split('.') 末段是
     扩展名（如 py）而非符号名——拿它比较会把任意两条同扩展名文件的边误判成
     「同名疑义边」。符号级 id（无斜杠、末段非扩展名）行为不变。口径与
     validate_course.py 的 _cg_is_pathish 两侧必须同步演化。 */
  var CG_TAIL_EXTS = { py: 1, js: 1, ts: 1, tsx: 1, jsx: 1, go: 1, rs: 1,
    java: 1, c: 1, cc: 1, cpp: 1, h: 1, hpp: 1, cs: 1, rb: 1, lua: 1,
    php: 1, kt: 1, swift: 1, m: 1, json: 1, md: 1, css: 1 };
  function cgIsPathish(id) {
    return id.indexOf('/') !== -1 ||
      CG_TAIL_EXTS[id.slice(id.lastIndexOf('.') + 1).toLowerCase()] === 1;
  }
  function cgLayout(data) {
    var cmpStr = function (a, b) { return a < b ? -1 : (a > b ? 1 : 0); };
    var nodes = Object.create(null), order = [];
    /* 降级声明计数（v1.13.4 前提）：没画什么必须说出来，不许静默——
       自环被丢弃数、标签截断数、两端末段名相同的疑义边数（事实面板用） */
    var cutCount = 0, droppedSelfLoops = 0, sameTailCount = 0;
    (data.nodes || []).forEach(function (n) {
      if (!n || typeof n.id !== 'string' || !n.id) return;
      if (nodes[n.id]) return;                 /* 重复 id：以首个为准（确定性） */
      var label = (typeof n.label === 'string' && n.label) ? n.label : n.id;
      var w = Math.max(CG_MIN_COL_W,
                       Math.min(CG_MAX_COL_W, cgTextW(label) + CG_GLYPH_COL + 14));
      var el = cgElide(label, w - CG_GLYPH_COL - 14);
      if (el.cut) cutCount++;
      nodes[n.id] = {
        id: n.id, label: label, text: el.text, cut: el.cut,
        kind: (typeof n.kind === 'string') ? n.kind : '',
        file: (typeof n.file === 'string') ? n.file : '',
        line: (typeof n.line === 'number' && n.line >= 1) ? n.line : null,
        w: cgNum(w), x: 0, y: 0
      };
      order.push(n.id);
    });

    var links = [];
    (data.links || []).forEach(function (l) {
      if (!l || typeof l.from !== 'string' || typeof l.to !== 'string') return;
      if (!nodes[l.from] || !nodes[l.to]) return;   /* 端点不存在：渲染器跳过，校验器报错 */
      if (l.from === l.to) { droppedSelfLoops++; return; }   /* 自环禁止（规格 §2）：不画，但计入事实面板的「未画」声明 */
      /* 同名疑义边计数：仅符号级 id 参与——文件级/模块级 id 的 split 末段是
         扩展名而非符号名（守卫见 cgIsPathish，口径与 validate_course.py 同步） */
      if (!cgIsPathish(l.from) && !cgIsPathish(l.to)) {
        var ft = l.from.split('.'), tt = l.to.split('.');
        if (ft[ft.length - 1] === tt[tt.length - 1]) sameTailCount++;
      }
      var rec = {
        i: links.length, from: l.from, to: l.to,
        count: (typeof l.count === 'number' && l.count >= 1) ? l.count : 1,
        hasCount: typeof l.count === 'number' && l.count >= 1,
        declared: (typeof l.declared === 'number' && l.declared >= 1) ? l.declared : null,
        confidence: (l.confidence === 'inferred') ? 'inferred' : 'verified',
        file: (typeof l.file === 'string') ? l.file : '',
        line: (typeof l.line === 'number' && l.line >= 1) ? l.line : null,
        back: (l.back === true)
      };
      links.push(rec);
    });

    /* ① 分层基准（规格 §3.1）：declared 覆盖率 ≥ 40% 才认它，否则回落 count；
       两者皆无则按调用结构。降级必须显式声明，见事实面板与 data-cg-layer-mode。 */
    var declaredLinks = links.filter(function (l) { return l.declared !== null; });
    var useDeclared = links.length > 0 &&
      declaredLinks.length >= links.length * CG_DECLARED_COVERAGE;
    var anyCount = links.some(function (l) { return l.hasCount; });
    var mode = useDeclared ? 'declared' : (anyCount ? 'count' : 'structure');
    function weightOf(l) {
      if (useDeclared) return l.declared;
      return l.hasCount ? l.count : 1;
    }
    var layeringLinks = useDeclared ? declaredLinks : links;

    /* ② 两环互指消解：u→v 与 v→u 同时在场时，权重小的一侧退出分层图——它就是
       那条回边；权重相同按 id 定序，保证同一份数据两次运行结果一致（照 CodeGraph） */
    var byPair = Object.create(null);
    layeringLinks.forEach(function (l) { byPair[l.from + '\u0000' + l.to] = l; });
    var acyclic = [];
    layeringLinks.forEach(function (l) {
      var rev = byPair[l.to + '\u0000' + l.from];
      if (!rev) { acyclic.push(l); return; }
      var mine = weightOf(l), theirs = weightOf(rev);
      if (theirs > mine || (theirs === mine && l.from > l.to)) return;
      acyclic.push(l);
    });

    /* ③ 最长路径分层：layer = 1 + max(依赖目标的 layer)，叶子为 0。
       三环及以上由 visiting 兜底——命中在栈节点按参照实现返回 0、外层仍 +1。 */
    var out = Object.create(null);
    order.forEach(function (id) { out[id] = []; });
    acyclic.forEach(function (l) { out[l.from].push(l.to); });
    order.forEach(function (id) { out[id].sort(cmpStr); });

    var layer = Object.create(null), visiting = Object.create(null);
    order.forEach(function (root) {                 /* 起点顺序 = 数据声明顺序 */
      if (layer[root] !== undefined) return;
      visiting[root] = true;
      var stack = [{ id: root, i: 0, best: 0 }];
      while (stack.length) {
        var f = stack[stack.length - 1];
        var outs = out[f.id];
        if (f.i < outs.length) {
          var nx = outs[f.i++], got;
          if (layer[nx] !== undefined) got = layer[nx];
          else if (visiting[nx]) got = 0;
          else {
            visiting[nx] = true;
            stack.push({ id: nx, i: 0, best: 0 });
            continue;
          }
          f.best = Math.max(f.best, got + 1);
          continue;
        }
        layer[f.id] = f.best;
        delete visiting[f.id];
        stack.pop();
        var up = stack[stack.length - 1];
        if (up) up.best = Math.max(up.best, f.best + 1);
      }
    });

    var maxLayer = 0;
    order.forEach(function (id) { maxLayer = Math.max(maxLayer, layer[id] || 0); });
    var layerCount = maxLayer + 1;
    var rows = [];
    for (var r = 0; r < layerCount; r++) rows.push([]);
    order.forEach(function (id) { rows[layer[id] || 0].push(id); });
    rows.forEach(function (arr) { arr.sort(cmpStr); });   /* 层内起点：稳定字母序 */

    /* ④ 重心法 3 轮：邻居取双向（未给 options.order 时照 CodeGraph 两向都收），
       排序三级定序（重心 → 原位置 → id），不依赖 sort 稳定性 */
    var nbr = Object.create(null);
    order.forEach(function (id) { nbr[id] = []; });
    acyclic.forEach(function (l) {
      nbr[l.to].push(l.from);
      nbr[l.from].push(l.to);
    });
    var pos = Object.create(null);
    rows.forEach(function (arr) { arr.forEach(function (id, i) { pos[id] = i; }); });
    for (var sw = 0; sw < 3; sw++) {
      rows.forEach(function (arr) {
        var bary = Object.create(null);
        arr.forEach(function (id) {
          var list = nbr[id];
          if (!list.length) { bary[id] = Infinity; return; }
          var sum = 0;
          list.forEach(function (o) { sum += (pos[o] === undefined ? 0 : pos[o]); });
          bary[id] = sum / list.length;
        });
        arr.sort(function (a, b) {
          var ba = bary[a], bb = bary[b];
          if (ba !== bb && isFinite(ba - bb)) return ba - bb;
          if (ba !== bb) return ba < bb ? -1 : 1;   /* Infinity 相减是 NaN，绕开 */
          var pa = (pos[a] === undefined ? 0 : pos[a]);
          var pb = (pos[b] === undefined ? 0 : pos[b]);
          return (pa - pb) || cmpStr(a, b);
        });
        arr.forEach(function (id, i) { pos[id] = i; });
      });
    }

    /* ⑤ 落位：层号越大越靠上（源在下边出端口、目标在上边进端口 = 调用自上而下流） */
    var pitch = CG_NODE_H + CG_LAYER_GAP;
    var rowSum = [], naturalSpan = [], contentWidth = CG_VBW_MIN - CG_PADDING * 2;
    rows.forEach(function (arr, i) {
      var sum = 0;
      arr.forEach(function (id) { sum += nodes[id].w; });
      rowSum[i] = sum;
      naturalSpan[i] = sum + Math.max(0, arr.length - 1) * CG_NODE_GAP;
      contentWidth = Math.max(contentWidth, naturalSpan[i]);
    });
    var rowSpan = rows.map(function (arr, i) {
      return Math.min(contentWidth, Math.max(naturalSpan[i], arr.length * CG_MIN_SLOT));
    });
    rows.forEach(function (arr, i) {
      var span = rowSpan[i], gap = arr.length > 1 ? (span - rowSum[i]) / (arr.length - 1) : 0;
      var x = CG_PADDING + (contentWidth - span) / 2 +
              (arr.length === 1 ? (span - rowSum[i]) / 2 : 0);
      var y = cgNum(CG_PADDING + (layerCount - 1 - i) * pitch);
      arr.forEach(function (id) {
        var n = nodes[id];
        n.x = cgNum(x); n.y = y;
        x += n.w + gap;
      });
    });

    /* 端口散布：(i+1)/(n+1)——让 8 条依赖成扇面，而不是挤在一个角（规格 §3.5） */
    var outPool = Object.create(null), inPool = Object.create(null);
    order.forEach(function (id) { outPool[id] = []; inPool[id] = []; });
    links.forEach(function (l) { outPool[l.from].push(l); inPool[l.to].push(l); });
    order.forEach(function (id) {
      var o = outPool[id], n = inPool[id];
      o.forEach(function (l, i) { l.sf = (i + 1) / (o.length + 1); });
      n.forEach(function (l, i) { l.tf = (i + 1) / (n.length + 1); });
    });

    /* 回边 = 源层号小于目标层号（画面上朝上）——标出来，而不是拉直（规格 §3.4） */
    links.forEach(function (l) {
      if (!l.back) l.back = (layer[l.from] || 0) < (layer[l.to] || 0);
    });

    return {
      nodes: nodes, order: order, links: links, rows: rows, layer: layer,
      mode: mode, layerCount: layerCount,
      declared: declaredLinks.length, total: links.length,
      cutCount: cutCount, droppedSelfLoops: droppedSelfLoops,
      sameTailCount: sameTailCount,
      vbw: cgNum(contentWidth + CG_PADDING * 2),
      vbh: cgNum(layerCount * pitch - CG_LAYER_GAP + CG_PADDING * 2)
    };
  }

  /* 20c. 渲染与交互（只用 createElementNS；零 innerHTML、无内联 on*、无 fetch）
     线型 = 置信度：verified 实线 / inferred 虚线 / 回边强调色虚线（base.css §20）；
     每条边另绘同路径、透明、12px 宽的副本专供 hover（1px 线无法命中）。 */
  document.querySelectorAll('.callgraph-scene').forEach(function (scene) {
    var stage = scene.querySelector('.callgraph-stage');
    if (!stage) return;
    var facts = scene.querySelector('.callgraph-facts');
    var data = ctrlParse(scene, 'callgraph-data');
    if (!data || !data.nodes || !data.nodes.length) {
      ctrlError(scene, '调用图');
      return;
    }
    var G = cgLayout(data);
    if (!G.order.length) { ctrlError(scene, '调用图'); return; }
    scene.setAttribute('data-cg-layer-mode', G.mode);

    var NS = 'http://www.w3.org/2000/svg';
    function svgEl(tag) { return document.createElementNS(NS, tag); }

    var svg = svgEl('svg');
    svg.setAttribute('class', 'callgraph-svg');
    svg.setAttribute('viewBox', '0 0 ' + G.vbw + ' ' + G.vbh);
    svg.setAttribute('width', '100%');
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    var gEdges = svgEl('g');
    gEdges.setAttribute('class', 'cg-edges');
    var gNodes = svgEl('g');
    gNodes.setAttribute('class', 'cg-nodes');
    svg.appendChild(gEdges);
    svg.appendChild(gNodes);

    /* --- 边：可见路径与命中副本分两轮追加（命中副本在上，重叠边才可点） --- */
    var edgeRecs = [];
    G.links.forEach(function (l) {
      var a = G.nodes[l.from], b = G.nodes[l.to];
      var sx = cgNum(a.x + a.w * l.sf), tx = cgNum(b.x + b.w * l.tf);
      var sy, ty;
      if (l.back) {            /* 回边：从源的上边出去，落回目标的下边 */
        sy = cgNum(a.y); ty = cgNum(b.y + CG_NODE_H);
      } else {
        sy = cgNum(a.y + CG_NODE_H); ty = cgNum(b.y);
      }
      var midY = cgNum((sy + ty) / 2);
      /* 三次贝塞尔：源下端口 → 垂直中点 → 目标上端口（同一捆边同向弯曲） */
      var d = 'M' + sx + ',' + sy + ' C' + sx + ',' + midY + ' '
              + tx + ',' + midY + ' ' + tx + ',' + ty;

      var p = svgEl('path');
      p.setAttribute('class', 'cg-edge is-' + l.confidence + (l.back ? ' is-back' : ''));
      p.setAttribute('d', d);
      p.setAttribute('fill', 'none');
      p.setAttribute('stroke-width', cgStrokeW(l.count));
      p.setAttribute('pointer-events', 'none');
      p.setAttribute('data-cg-edge', String(l.i));
      p.setAttribute('data-cg-from', l.from);
      p.setAttribute('data-cg-to', l.to);
      p.setAttribute('data-cg-confidence', l.confidence);
      p.setAttribute('data-cg-back', l.back ? '1' : '0');
      gEdges.appendChild(p);

      var hit = svgEl('path');
      hit.setAttribute('class', 'cg-hit');
      hit.setAttribute('d', d);
      hit.setAttribute('fill', 'none');
      hit.setAttribute('stroke', 'transparent');
      hit.setAttribute('stroke-width', '12');
      hit.setAttribute('pointer-events', 'stroke');
      hit.setAttribute('data-cg-hit', String(l.i));
      gEdges.appendChild(hit);

      edgeRecs.push({ l: l, el: p, hit: hit });
    });

    /* --- 节点：圆角矩形 + 类型 glyph + 标签；空心描边，克制风格 --- */
    var nodeEls = Object.create(null);
    G.order.forEach(function (id) {
      var n = G.nodes[id];
      var g = svgEl('g');
      g.setAttribute('class', 'cg-node is-kind-' + (n.kind || 'unknown'));
      g.setAttribute('tabindex', '0');       /* 可 Tab 聚焦，聚焦即等同 hover */
      g.setAttribute('data-cg-id', id);
      g.setAttribute('data-cg-full', n.label);

      var ti = svgEl('title');               /* 截断时全名在这里，信息不丢 */
      ti.textContent = n.label + ' · ' + (n.file || '?')
                       + (n.line ? ':' + n.line : '');
      g.appendChild(ti);

      var r = svgEl('rect');
      r.setAttribute('class', 'cg-box');
      r.setAttribute('x', String(n.x));
      r.setAttribute('y', String(n.y));
      r.setAttribute('width', String(n.w));
      r.setAttribute('height', String(CG_NODE_H));
      r.setAttribute('rx', '8');
      g.appendChild(r);

      var gl = svgEl('text');
      gl.setAttribute('class', 'cg-glyph');
      gl.setAttribute('x', String(cgNum(n.x + 17)));
      gl.setAttribute('y', String(cgNum(n.y + CG_NODE_H / 2)));
      gl.setAttribute('text-anchor', 'middle');
      gl.setAttribute('dominant-baseline', 'central');
      gl.setAttribute('aria-hidden', 'true');
      gl.textContent = CG_KIND_GLYPH[n.kind] || '•';
      g.appendChild(gl);

      var lb = svgEl('text');
      lb.setAttribute('class', 'cg-label');
      lb.setAttribute('x', String(cgNum(n.x + CG_GLYPH_COL)));
      lb.setAttribute('y', String(cgNum(n.y + CG_NODE_H / 2)));
      lb.setAttribute('dominant-baseline', 'central');
      lb.textContent = n.text;
      if (n.cut) lb.setAttribute('data-cg-elided', '1');
      g.appendChild(lb);

      gNodes.appendChild(g);
      nodeEls[id] = g;
    });

    /* --- 事实面板：降级必须显式声明，不允许静默 --- */
    var hint = facts ? facts.textContent.replace(/\s+/g, ' ').trim() : '';
    var cov = G.declared + '/' + G.total;
    var modeNote = (G.mode === 'declared')
      ? '按声明深度（declared）决定分层与回边方向'
      : (G.mode === 'count'
         ? '⚠ 无声明深度（declared 覆盖 ' + cov + ' < 40%）：按调用点数决定回边方向'
         : '⚠ 无声明深度也无调用点数（declared 覆盖 ' + cov + '）：按调用结构分层');
    function setFacts(t) { if (facts) facts.textContent = t; }
    /* 多句拼接（分行显示靠 .callgraph-facts 的 white-space: pre-line）：
       提示一句 + 分层依据一句 + 「未画」清单一句；数量为 0 的项不出现，
       全零时整句不出现（照 CodeGraph MapKey 的省略逐条成句纪律） */
    function idleFacts() {
      var lines = [];
      if (hint) lines.push(hint);
      lines.push(modeNote);
      var omitted = [];
      if (G.droppedSelfLoops > 0)
        omitted.push(G.droppedSelfLoops + ' 条自环（递归请见栈塔）');
      if (G.cutCount > 0)
        omitted.push(G.cutCount + ' 个标签已截断（全名见 title）');
      if (G.sameTailCount > 0)
        omitted.push(G.sameTailCount + ' 条同名疑义边（请人工核对）');
      if (omitted.length) lines.push('未画：' + omitted.join('／'));
      setFacts(lines.join('\n'));
    }

    /* --- 高亮/淡化：状态类 .is-cg-hot / .is-cg-dim，与探照灯 .is-spot 严格分离 --- */
    function paint(sel) {
      var hotN = null, hotE = null;
      if (sel && sel.type === 'node') {
        hotN = Object.create(null); hotN[sel.id] = true;
        hotE = Object.create(null);
        edgeRecs.forEach(function (r) {
          if (r.l.from === sel.id || r.l.to === sel.id) hotE[r.l.i] = true;
        });
      } else if (sel && sel.type === 'edge') {
        hotN = Object.create(null); hotE = Object.create(null);
        var rec = edgeRecs[sel.i];
        if (!rec) return;
        hotE[sel.i] = true;
        hotN[rec.l.from] = true; hotN[rec.l.to] = true;
      }
      G.order.forEach(function (id) {
        var el = nodeEls[id];
        if (!hotN) { el.classList.remove('is-cg-hot', 'is-cg-dim'); return; }
        var on = !!hotN[id];
        el.classList.toggle('is-cg-hot', on);
        el.classList.toggle('is-cg-dim', !on);
      });
      edgeRecs.forEach(function (r) {
        if (!hotE) { r.el.classList.remove('is-cg-hot', 'is-cg-dim'); return; }
        var on = !!hotE[r.l.i];
        r.el.classList.toggle('is-cg-hot', on);
        r.el.classList.toggle('is-cg-dim', !on);
      });
    }
    function nodeFacts(id) {
      var n = G.nodes[id], outs = 0, ins = 0;
      edgeRecs.forEach(function (r) {
        if (r.l.from === id) outs++;
        if (r.l.to === id) ins++;
      });
      return n.label + ' · ' + (n.kind || '未知类型') + ' · '
             + (n.file || '?') + (n.line ? ':' + n.line : '')
             + ' · 出边 ' + outs + ' / 入边 ' + ins;
    }
    function edgeFacts(i) {
      var l = edgeRecs[i].l;
      var conf = (l.confidence === 'verified') ? 'verified（实锤）' : 'inferred（推断）';
      var src = l.file ? (l.file + (l.line ? ':' + l.line : ''))
                       : (l.line ? '第 ' + l.line + ' 行' : '未给依据行');
      return G.nodes[l.from].label + ' → ' + G.nodes[l.to].label + ' · '
             + l.count + ' 个调用点 · ' + conf + ' · ' + src;
    }

    var cur = null;
    function enter(key, sel, text) { cur = key; paint(sel); setFacts(text); }
    function leave(key) {
      if (cur !== key) return;
      cur = null; paint(null); idleFacts();
    }
    G.order.forEach(function (id) {
      var g = nodeEls[id];
      var key = 'n:' + id;
      g.addEventListener('mouseenter', function () {
        enter(key, { type: 'node', id: id }, nodeFacts(id));
      });
      g.addEventListener('focus', function () {
        enter(key, { type: 'node', id: id }, nodeFacts(id));
      });
      g.addEventListener('mouseleave', function () { leave(key); });
      g.addEventListener('blur', function () { leave(key); });
    });
    edgeRecs.forEach(function (r) {
      var key = 'e:' + r.l.i;
      r.hit.addEventListener('mouseenter', function () {
        enter(key, { type: 'edge', i: r.l.i }, edgeFacts(r.l.i));
      });
      r.hit.addEventListener('mouseleave', function () { leave(key); });
    });

    /* 一次性入场（≤200ms，只走 opacity），尊重 prefers-reduced-motion */
    if (reduceMotion()) scene.classList.add('is-cg-in');
    else lazyPlay(scene, function () { scene.classList.add('is-cg-in'); }, null);

    stage.appendChild(svg);
    idleFacts();
  });

})();
