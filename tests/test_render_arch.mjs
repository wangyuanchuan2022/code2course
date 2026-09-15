/* ===================================================================
   test_render_arch.mjs — 架构图 / 调用图渲染确定性 harness（v1.18.0）
   -------------------------------------------------------------------
   零依赖、node 直跑：node tests/test_render_arch.mjs
   做法：用最小 DOM stub 在 node vm 里加载 resources/app.js（真实生产代码
   路径，不是测试替身重写的渲染器），把场景 DOM 序列化成字符串，断言：

     [1] BR baseline  调用图（仅旧字段）渲染结果与冻结基线逐字节一致
                      —— 保证「既有 .callgraph-scene 缺省行为逐字不变」
     [2] AR-DET       架构图同一份 JSON 两次渲染（两个全新 vm 上下文）
                      输出逐字节一致
     [3] AR-FACT      事实面板文本顺序：结构行 -> 作用 -> 调用 -> 角色，
                      边面板含 依赖：<kind> · <detail>
     [4] AR-KIND      kind 决定箭头样式（owns 无箭头 / call·dependency
                      实心头 / data·control 空心·点形头）且不改变线型
     [5] AR-MARK      module_marks 渲染为模块归属标注（带 + chip + 图例行）
     [6] AR-LEGEND    图例只在有声明 kind 时出现；无 kind 不渲染图例
     [7] AR-REGRESS   调用图路径仍不含任何新渲染物（arrow/kind/legend）

   输出全 ASCII。退出码 0 = 全绿。
   =================================================================== */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createHash } from 'node:crypto';
import vm from 'node:vm';

const sha256 = (s) => createHash('sha256').update(s, 'utf8').digest('hex');

const HERE = dirname(fileURLToPath(import.meta.url));
const APP_JS = join(HERE, '..', 'resources', 'app.js');
const SRC = readFileSync(APP_JS, 'utf8');

let failed = 0;
function ok(name, cond, detail) {
  const tag = cond ? 'PASS' : 'FAIL';
  if (!cond) failed++;
  console.log('[' + tag + '] ' + name + (cond || !detail ? '' : ' -- ' + detail));
}
function eq(name, a, b) {
  ok(name, a === b, 'got ' + JSON.stringify(String(a).slice(0, 120)) +
     ' want ' + JSON.stringify(String(b).slice(0, 120)));
}

/* ---------------- 最小 DOM stub（只实现 app.js 用到的面） ---------------- */
function Esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/\n/g, '&#10;');
}
function makeEl(tag, ns) {
  const el = {
    tagName: tag, _ns: ns || null, _attrs: [], children: [],
    _classes: [], _text: '', listeners: Object.create(null), style: null,
    dataset: {}, hidden: false
  };
  el.style = { setProperty() {} };
  Object.defineProperty(el, 'className', {
    get() { return el._classes.join(' '); },
    set(v) { el._classes = String(v).split(/\s+/).filter(Boolean); }
  });
  Object.defineProperty(el, 'textContent', {
    get() { return el._text; },
    set(v) { el._text = String(v); el.children.length = 0; }
  });
  Object.defineProperty(el, 'classList', {
    get() {
      return {
        add(...cs) { cs.forEach((c) => { if (!el._classes.includes(c)) el._classes.push(c); }); },
        remove(...cs) { el._classes = el._classes.filter((c) => !cs.includes(c)); },
        contains(c) { return el._classes.includes(c); },
        toggle(c, force) {
          const has = el._classes.includes(c);
          const on = force === undefined ? !has : !!force;
          if (on && !has) el._classes.push(c);
          if (!on && has) el._classes = el._classes.filter((x) => x !== c);
          return on;
        }
      };
    }
  });
  el.setAttribute = (n, v) => {
    const s = String(v);
    const at = el._attrs.find((a) => a[0] === n);
    if (at) at[1] = s; else el._attrs.push([n, s]);
    if (n === 'class') el._classes = s.split(/\s+/).filter(Boolean);
  };
  el.getAttribute = (n) => {
    if (n === 'class') return el.className;
    const at = el._attrs.find((a) => a[0] === n);
    return at ? at[1] : null;
  };
  el.appendChild = (c) => { el.children.push(c); return c; };
  el.removeChild = (c) => {
    const i = el.children.indexOf(c);
    if (i >= 0) el.children.splice(i, 1);
    return c;
  };
  el.addEventListener = (t, fn) => {
    (el.listeners[t] = el.listeners[t] || []).push(fn);
  };
  el.removeEventListener = () => {};
  el.querySelector = () => null;
  el.querySelectorAll = () => [];
  el.closest = () => null;
  el.focus = () => {};
  el.select = () => {};
  el.getBoundingClientRect = () => ({ left: 0, top: 0, width: 100, height: 100 });
  el.scrollIntoView = () => {};
  return el;
}
function serialize(el, depth) {
  depth = depth || 0;
  const pad = '  '.repeat(depth);
  /* class 统一从 _classes 出（setAttribute('class') 与 className 都同步进它），
     避免同一属性打印两次 */
  const attrs = el._attrs.filter((a) => a[0] !== 'class')
    .map((a) => ' ' + a[0] + '="' + Esc(a[1]) + '"').join('');
  const cls = el._classes.length ? ' class="' + Esc(el._classes.join(' ')) + '"' : '';
  const head = pad + '<' + el.tagName + cls + attrs + '>';
  const body = el._text ? (el.children.length ? '' : pad + '  ' + Esc(el._text) + '\n') : '';
  if (!el._text && !el.children.length) return head + '\n';
  let out = head + '\n' + body;
  el.children.forEach((c) => { out += serialize(c, depth + 1); });
  return out + pad + '</' + el.tagName + '>\n';
}
function walk(el, fn) {
  fn(el);
  el.children.forEach((c) => walk(c, fn));
}
function findByAttr(root, name, value) {
  let hit = null;
  walk(root, (e) => {
    if (hit) return;
    const v = e.getAttribute(name);
    if (v !== null && (value === undefined || v === value)) hit = e;
  });
  return hit;
}
function fire(el, type) {
  (el.listeners[type] || []).forEach((fn) => fn({ type, target: el, preventDefault() {} }));
}

/* ---------------- 场景装配 ---------------- */
function scene(tag, opts) {
  const s = makeEl('div');
  s.className = tag + ' scene';
  if (opts.stageCls) {
    const st = makeEl('div'); st.className = opts.stageCls;
    const fa = makeEl('div'); fa.className = opts.factsCls;
    const dt = makeEl('script'); dt.className = opts.dataCls;
    dt.textContent = typeof opts.json === 'string' ? opts.json : JSON.stringify(opts.json);
    s.appendChild(st); s.appendChild(fa); s.appendChild(dt);
    s._stage = st; s._facts = fa; s._data = dt;
  }
  s.querySelector = (sel) => {
    if (sel === '.' + opts.stageCls) return s._stage;
    if (sel === '.' + opts.factsCls) return s._facts;
    if (sel === 'script.' + opts.dataCls) return s._data;
    return null;
  };
  s.querySelectorAll = () => [];
  return s;
}
/* 每个场景一个全新 vm 上下文：跨上下文一致才算「同一份数据两次渲染逐字节相同」 */
function runScene(makeScene) {
  const s = makeScene();
  const doc = {
    documentElement: { dataset: {} },
    body: makeEl('body'),
    hidden: false,
    activeElement: null,
    createElement: (t) => makeEl(t),
    createElementNS: (ns, t) => makeEl(t, ns),
    createTextNode: (t) => { const e = makeEl('#text'); e.textContent = t; return e; },
    querySelector: () => null,
    querySelectorAll: (sel) => (sel === '.callgraph-scene' ? (s._cg || [])
      : sel === '.arch-scene' ? (s._arch || []) : []),
    getElementById: () => null,
    addEventListener: () => {},
    execCommand: () => false
  };
  const sandbox = {
    console, JSON, Math, Date, Object, Array, String, Number, Boolean,
    RegExp, Error, TypeError, isFinite, isNaN, parseInt, parseFloat,
    WeakMap, Map, Set, Promise, Symbol, setTimeout: () => 0, clearTimeout: () => {},
    requestAnimationFrame: () => 0, cancelAnimationFrame: () => {},
    document: doc,
    navigator: { clipboard: null },
    localStorage: { getItem: () => null, setItem: () => {} },
    history: { scrollRestoration: 'auto', replaceState: () => {} },
    location: { hash: '', pathname: '/', search: '' },
    IntersectionObserver: class { observe() {} unobserve() {} disconnect() {} }
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.matchMedia = () => ({ matches: false });
  sandbox.scrollTo = () => {};
  const ctx = vm.createContext(sandbox);
  vm.runInContext(SRC, ctx, { filename: 'app.js' });
  return s;
}
function render(host, json) {
  const s = runScene(() => {
    const root = makeEl('div');
    const sc = scene(host === 'cg' ? 'callgraph-scene' : 'arch-scene', {
      stageCls: host === 'cg' ? 'callgraph-stage' : 'arch-stage',
      factsCls: host === 'cg' ? 'callgraph-facts' : 'arch-facts',
      dataCls: host === 'cg' ? 'callgraph-data' : 'arch-data',
      json
    });
    root._cg = host === 'cg' ? [sc] : [];
    root._arch = host === 'arch' ? [sc] : [];
    root._scene = sc;
    return root;
  });
  return s._scene;
}
function svgOf(sc) { return sc._stage.children.find((c) => c.tagName === 'svg'); }
function pillsOf(sc) { return sc._stage.children.filter((c) => c.tagName !== 'svg'); }
function attrsOf(el, keys) {
  return keys.map((k) => k + '=' + el.getAttribute(k)).join(' ');
}

/* ---------------- 夹具 ---------------- */
/* 旧字段调用图：含自环（计入「未画」）、两环互指、同尾名疑义边 */
const CG_JSON = {
  nodes: [
    { id: 'main', label: 'main.py', kind: 'entry', file: 'main.py', line: 12 },
    { id: 'solver', label: 'solver.py', kind: 'module', file: 'solver.py', line: 3 },
    { id: 'vision', label: 'vision.py', kind: 'module', file: 'vision.py', line: 1 },
    { id: 'util', label: 'util.py', kind: 'module', file: 'util.py', line: 1 },
    { id: 'pkg.a.load', label: 'pkg.a.load()', kind: 'function', file: 'pkg/a.py', line: 40 },
    { id: 'pkg.b.load', label: 'pkg.b.load()', kind: 'function', file: 'pkg/b.py', line: 7 }
  ],
  links: [
    { from: 'main', to: 'solver', count: 2, confidence: 'verified', file: 'main.py', line: 31 },
    { from: 'main', to: 'vision', count: 1, confidence: 'inferred' },
    { from: 'solver', to: 'util', count: 5, confidence: 'verified', file: 'solver.py', line: 55 },
    { from: 'pkg.a.load', to: 'util', count: 1, confidence: 'verified', file: 'pkg/a.py', line: 44 },
    { from: 'pkg.b.load', to: 'util', count: 1, confidence: 'inferred' },
    { from: 'util', to: 'solver', count: 1, confidence: 'inferred', back: true },
    { from: 'util', to: 'util', count: 1, confidence: 'inferred' }
  ]
};
/* 新字段架构图：desc/role/view + kind/detail + module_marks */
const ARCH_JSON = {
  nodes: [
    { id: 'main', label: 'main.py', kind: 'entry', file: 'main.py', line: 12,
      desc: '程序入口：拉起 UI 与求解器', role: '启动与装配', view: 'own' },
    { id: 'solver', label: 'solver.py', kind: 'module', file: 'solver.py', line: 3,
      desc: '按概率模型给出下一步落子', role: '决策核心', view: 'flow' },
    { id: 'vision', label: 'vision.py', kind: 'module', file: 'vision.py', line: 1,
      desc: '截屏并识别棋盘格子', role: '环境感知', view: 'own' },
    { id: 'util', label: 'util.py', kind: 'module', file: 'util.py', line: 1,
      desc: '格子坐标与配置读写', role: '公共工具', view: 'own' },
    { id: 'cfg', label: 'cfg.json', kind: 'file', file: 'cfg.json', line: 1,
      desc: '窗口与阈值配置', role: '配置来源', view: 'flow' },
    { id: 'ui', label: 'ui.py', kind: 'module', file: 'ui.py', line: 1,
      desc: '绘制热力与提示框', role: '输出呈现', view: 'own' }
  ],
  links: [
    { from: 'main', to: 'solver', count: 1, confidence: 'verified',
      file: 'main.py', line: 31, kind: 'owns', detail: 'main 持有 Solver 实例并驱动一次求解' },
    { from: 'main', to: 'vision', count: 1, confidence: 'verified',
      file: 'main.py', line: 22, kind: 'call', detail: '启动时调 capture() 拉一帧' },
    { from: 'main', to: 'cfg', count: 3, confidence: 'verified',
      file: 'main.py', line: 14, kind: 'dependency', detail: '读窗口标题与阈值' },
    { from: 'solver', to: 'util', count: 4, confidence: 'verified',
      file: 'solver.py', line: 55, kind: 'call', detail: '坐标换算与邻域枚举' },
    { from: 'vision', to: 'solver', count: 2, confidence: 'inferred',
      kind: 'data', detail: '把格子矩阵交给概率模型' },
    { from: 'solver', to: 'ui', count: 1, confidence: 'inferred',
      kind: 'control', detail: '算完后触发一次重绘' }
  ],
  module_marks: [
    { id: 'm1', label: '模块 1 · 环境与视觉', covers: ['vision', 'cfg', 'util'] },
    { id: 'm2', label: '模块 2 · 决策与呈现', covers: ['solver', 'ui', 'util'] }
  ]
};
/* 调用图宿主也必须吃新字段：desc/role 上节点，kind/detail 上边（契约 §二） */
const CG_NEW_JSON = {
  nodes: CG_JSON.nodes.map((n) => (n.id === 'main'
    ? Object.assign({}, n, { desc: '封面入口：装配并启动', role: '启动器' })
    : n)),
  links: CG_JSON.links.map((l, i) => {
    if (i === 0) return Object.assign({}, l, { kind: 'owns', detail: 'main 持有 Solver' });
    if (i === 1) return Object.assign({}, l, { detail: '无 kind 只给 detail' });
    if (i === 3) return Object.assign({}, l, { kind: 'data', detail: '把坐标矩阵递过去' });
    return l;
  })
};

/* 无 kind 的架构图：图例不得渲染 */
const ARCH_NOKIND = {
  nodes: [
    { id: 'a', label: 'a.py', kind: 'module', file: 'a.py', line: 1, desc: '甲', role: '甲' },
    { id: 'b', label: 'b.py', kind: 'module', file: 'b.py', line: 1 },
    { id: 'c', label: 'c.py', kind: 'module', file: 'c.py', line: 1 },
    { id: 'd', label: 'd.py', kind: 'module', file: 'd.py', line: 1 }
  ],
  links: [
    { from: 'a', to: 'b', count: 1, confidence: 'verified', file: 'a.py', line: 2 },
    { from: 'b', to: 'c', count: 1, confidence: 'inferred' },
    { from: 'c', to: 'd', count: 1, confidence: 'verified', file: 'c.py', line: 9 }
  ]
};

/* ---------------- [1] 调用图缺省行为冻结基线 ----------------
   基线 = 改造前 app.js 对 CG_JSON 的渲染串 SHA-256（见报告 §4 取证）。
   不直接贴 4KB 串是为了让文件可读；失配时下面会把实际串整段 ASCII 转义
   打印出来供逐行比对（诊断性不丢）。 */
const CG_BASELINE_SHA = '495c6d01d0252395217d497be08b64294237b907942b33cac683f7ce0cbd88c8';

const cgSc = render('cg', CG_JSON);
const cgText = serialize(svgOf(cgSc)) + 'FACTS\n' + Esc(cgSc._facts.textContent) + '\n'
  + 'LAYERMODE=' + cgSc.getAttribute('data-cg-layer-mode') + '\n';

if (process.argv.includes('--record')) {
  console.log('RECORD sha256=' + sha256(cgText) + ' bytes=' + Buffer.byteLength(cgText, 'utf8'));
  console.log('RECORD dump=' + JSON.stringify(cgText));
  process.exit(0);
}

if (CG_BASELINE_SHA === '__CG_BASELINE_SHA__') {
  ok('BR baseline frozen', false, 'baseline not embedded yet; run with --record');
  process.exit(1);
}
if (sha256(cgText) !== CG_BASELINE_SHA) {
  console.log('CG-BASELINE MISMATCH: actual sha256=' + sha256(cgText));
  console.log('CG-BASELINE dump=' + JSON.stringify(cgText));
}
eq('BR callgraph default bytes frozen', sha256(cgText), CG_BASELINE_SHA);

/* ---------------- [7] 调用图未新增渲染物 ---------------- */
ok('AR-REGRESS no cg-arrow in callgraph host', cgText.indexOf('cg-arrow') === -1);
ok('AR-REGRESS no data-cg-kind in callgraph host', cgText.indexOf('data-cg-kind') === -1);
ok('AR-REGRESS no arch-legend in callgraph host', cgText.indexOf('arch-legend') === -1);
ok('AR-REGRESS facts keep legacy shape',
  cgSc._facts.textContent.indexOf('依赖：') === -1 && cgSc._facts.textContent.indexOf('作用：') === -1);

/* ---------------- [2] 架构图确定性 ---------------- */
const archA = render('arch', ARCH_JSON);
const archB = render('arch', ARCH_JSON);
const archAStr = serialize(svgOf(archA)) + 'PILLS\n' + pillsOf(archA).map((p) => serialize(p)).join('');
const archBStr = serialize(svgOf(archB)) + 'PILLS\n' + pillsOf(archB).map((p) => serialize(p)).join('');
eq('AR-DET two renders byte-identical', archAStr, archBStr);

/* 同一 vm 内连渲两次也必须一致（无累积全局态） */
const archC = render('arch', ARCH_JSON);
eq('AR-DET third render byte-identical', archAStr,
  serialize(svgOf(archC)) + 'PILLS\n' + pillsOf(archC).map((p) => serialize(p)).join(''));

/* ---------------- [3] 事实面板 ---------------- */
const gMain = findByAttr(svgOf(archA), 'data-cg-id', 'main');
fire(gMain, 'mouseenter');
const nf = archA._facts.textContent;
ok('AR-FACT node panel has desc', nf.indexOf('作用：程序入口：拉起 UI 与求解器') !== -1, nf);
ok('AR-FACT node panel has role', nf.indexOf('角色：启动与装配') !== -1, nf);
ok('AR-FACT node panel order structure<desc<calls<role',
  nf.indexOf('main.py · entry') === 0 &&
  nf.indexOf('作用：') < nf.indexOf('调用：') &&
  nf.indexOf('调用：') < nf.indexOf('角色：'), nf);
const hit0 = findByAttr(svgOf(archA), 'data-cg-hit', '0');
fire(hit0, 'mouseenter');
const ef = archA._facts.textContent;
ok('AR-FACT edge panel has kind+detail',
  ef.indexOf('依赖：owns · main 持有 Solver 实例并驱动一次求解') !== -1, ef);
const hit4 = findByAttr(svgOf(archA), 'data-cg-hit', '4');
fire(hit4, 'mouseenter');
ok('AR-FACT data-kind edge panel',
  archA._facts.textContent.indexOf('依赖：data · 把格子矩阵交给概率模型') !== -1,
  archA._facts.textContent);
fire(hit4, 'mouseleave');
ok('AR-FACT idle drops the node panel',
  archA._facts.textContent.indexOf('作用：') === -1 &&
  archA._facts.textContent.indexOf('依赖：') === -1 &&
  archA._facts.textContent.indexOf('按调用点数') !== -1, archA._facts.textContent);

/* ---------------- [4] kind 决定箭头、线型仍只承载置信度 ---------------- */
function edgePath(sc, i) { return findByAttr(svgOf(sc), 'data-cg-edge', String(i)); }
function arrowsOf(sc) {
  const out = [];
  walk(svgOf(sc), (e) => { if (e._classes.indexOf('cg-arrow') !== -1) out.push(e); });
  return out;
}
const arrows = arrowsOf(archA);
eq('AR-KIND six arrows drawn (owns gets none)', arrows.length, 5);
const arrowKinds = arrows.map((a) => a.getAttribute('data-cg-kind'));
eq('AR-KIND call solid', arrowKinds.filter((k) => k === 'call').length, 2);
eq('AR-KIND dependency solid', arrowKinds.filter((k) => k === 'dependency').length, 1);
eq('AR-KIND data hollow', arrowKinds.filter((k) => k === 'data').length, 1);
eq('AR-KIND control dot', arrowKinds.filter((k) => k === 'control').length, 1);
ok('AR-KIND owns has no arrow', arrowKinds.indexOf('owns') === -1);
eq('AR-KIND call head is filled', arrows[0].getAttribute('fill'), 'var(--text)');
const hollow = arrows.find((a) => a.getAttribute('data-cg-kind') === 'data');
eq('AR-KIND data head is hollow', hollow.getAttribute('fill'), 'none');
const dot = arrows.find((a) => a.getAttribute('data-cg-kind') === 'control');
ok('AR-KIND control head is a dot', dot.tagName === 'circle');
ok('AR-KIND arrows inert', arrows.every((a) => a.getAttribute('pointer-events') === 'none'));
eq('AR-KIND line type still confidence: verified solid',
  edgePath(archB, 0).getAttribute('class'), 'cg-edge is-verified');
eq('AR-KIND line type still confidence: inferred dashed',
  edgePath(archB, 4).getAttribute('class'), 'cg-edge is-inferred');
eq('AR-KIND back edge keeps accent dashed',
  edgePath(cgSc, 5).getAttribute('class'), 'cg-edge is-inferred is-back');

/* ---------------- [5][6] 模块标注与图例 ---------------- */
const marks = [];
walk(svgOf(archA), (e) => { if (e._classes.indexOf('cg-mark-band') !== -1) marks.push(e); });
eq('AR-MARK two module bands', marks.length, 2);
ok('AR-MARK band is inert rect',
  marks.every((m) => m.tagName === 'rect' && m.getAttribute('pointer-events') === 'none'));
const chips = [];
walk(svgOf(archA), (e) => { if (e._classes.indexOf('cg-mark-chip') !== -1) chips.push(e); });
eq('AR-MARK chip per covered node', chips.length, 6);
const marked = findByAttr(svgOf(archA), 'data-arch-mark', 'm1');
ok('AR-MARK nodes carry module attr', !!marked);
const shared = findByAttr(svgOf(archA), 'data-cg-id', 'util');
eq('AR-MARK shared node carries both modules', shared.getAttribute('data-arch-mark'), 'm1 m2');
ok('AR-GEOM no NaN in rendered geometry',
  archAStr.indexOf('NaN') === -1 && cgText.indexOf('NaN') === -1);
const flow = findByAttr(svgOf(archA), 'data-cg-id', 'solver');
const own = findByAttr(svgOf(archA), 'data-cg-id', 'main');
ok('AR-VIEW flow node is visually distinct',
  flow.className.indexOf('arch-view-flow') !== -1 &&
  own.className.indexOf('arch-view-flow') === -1,
  flow.className + ' | ' + own.className);
ok('AR-VIEW flow variant class is not a state class',
  flow.className.indexOf('is-arch') === -1);
ok('AR-VIEW callgraph host never gets view classes',
  cgText.indexOf('arch-view-flow') === -1);
ok('AR-MARK mark rows rendered under figure',
  pillsOf(archA).some((p) => p.className.indexOf('arch-marks') !== -1) ||
  pillsOf(archA).some((p) => serialize(p).indexOf('覆盖') !== -1));
const pillsText = pillsOf(archA).map((p) => serialize(p)).join('');
ok('AR-MARK mark caption names module and coverage',
  pillsText.indexOf('模块 1 · 环境与视觉') !== -1 && pillsText.indexOf('覆盖') !== -1);
ok('AR-LEGEND legend lists declared kinds',
  pillsText.indexOf('arch-legend') !== -1 && pillsText.indexOf('owns') !== -1 &&
  pillsText.indexOf('control') !== -1);
ok('AR-LEGEND legend does not list kind-less graphs',
  pillsOf(render('arch', ARCH_NOKIND)).map((p) => serialize(p)).join('')
    .indexOf('arch-legend') === -1);
ok('AR-LEGEND callgraph host never gets a legend', cgText.indexOf('arch-legend') === -1);

/* ---------------- [8] 调用图宿主吃新字段、但不因新字段变形 ---------------- */
const cgNew = render('cg', CG_NEW_JSON);
const cgNewStr = serialize(svgOf(cgNew));
const cgNewArrows = arrowsOf(cgNew);
const cgNewEdge0Class = edgePath(cgNew, 0).getAttribute('class');   /* 悬停前采集 */
/* owns 声明了 kind 但形态就是「无箭头」，故只有 data 那条出箭头 */
eq('AR-CGNEW only arrow-bearing kinds get a head', cgNewArrows.length, 1);
eq('AR-CGNEW arrow kind honoured', cgNewArrows[0].getAttribute('data-cg-kind'), 'data');
eq('AR-CGNEW arrow shape honoured', cgNewArrows[0].getAttribute('class'), 'cg-arrow is-hollow');
eq('AR-CGNEW declared owns renders no head',
  (cgNewStr.match(/data-cg-kind="owns"/g) || []).length, 1);
eq('AR-CGNEW declared data renders path+head',
  (cgNewStr.match(/data-cg-kind="data"/g) || []).length, 2);
ok('AR-CGNEW undeclared edges carry no kind attr',
  edgePath(cgNew, 2).getAttribute('data-cg-kind') === null &&
  edgePath(cgNew, 4).getAttribute('data-cg-kind') === null &&
  edgePath(cgNew, 5).getAttribute('data-cg-kind') === null);
ok('AR-CGNEW callgraph host still gets no legend',
  pillsOf(cgNew).map((p) => serialize(p)).join('').indexOf('arch-legend') === -1);
fire(findByAttr(svgOf(cgNew), 'data-cg-id', 'main'), 'mouseenter');
ok('AR-CGNEW callgraph node panel takes desc/role',
  cgNew._facts.textContent.indexOf('作用：封面入口：装配并启动') !== -1 &&
  cgNew._facts.textContent.indexOf('角色：启动器') !== -1, cgNew._facts.textContent);
fire(findByAttr(svgOf(cgNew), 'data-cg-hit', '1'), 'mouseenter');
ok('AR-CGNEW detail without kind falls back to call',
  cgNew._facts.textContent.indexOf('依赖：call · 无 kind 只给 detail') !== -1,
  cgNew._facts.textContent);
fire(findByAttr(svgOf(cgNew), 'data-cg-hit', '0'), 'mouseenter');
ok('AR-CGNEW declared owns panel line',
  cgNew._facts.textContent.indexOf('依赖：owns · main 持有 Solver') !== -1,
  cgNew._facts.textContent);
eq('AR-CGNEW legacy line type untouched', cgNewEdge0Class, 'cg-edge is-verified');

/* ---------------- 汇总 ---------------- */
const bytes = Buffer.byteLength(archAStr, 'utf8');
if (failed === 0) {
  console.log('AR-DET: PASS bytes=' + bytes);
  process.exit(0);
}
console.log('AR-DET: FAIL failures=' + failed);
process.exit(1);
