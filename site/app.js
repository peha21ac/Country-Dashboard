/* Dashboard renderer: vanilla JS + SVG, no external dependencies. */
"use strict";
const NS = "http://www.w3.org/2000/svg";
const YEAR_MS = 365.25 * 864e5;
const BANDS = [
  { from: Date.UTC(2014, 0, 1), to: Date.UTC(2017, 0, 1), name: "2014–16 commodity slump" },
  { from: Date.UTC(2020, 2, 1), to: Date.UTC(2021, 6, 1), name: "2020–21 COVID-19" },
  { from: Date.UTC(2022, 0, 1), to: Date.UTC(2023, 0, 1), name: "2022 inflation surge" },
];
const EUROLEX = "https://eur-lex.europa.eu/eli/dec/1998/683/oj/eng";

// ---- chart definitions (what to draw; data comes from data.json) ----------
const CHARTS = [
  { id: "fx", title: "Nominal exchange rate: fixed to the euro, moving with the dollar",
    read: "XOF per EUR is fixed by law. XOF per USD moves only because EUR/USD moves. On the blue line, up means the CFA franc is weaker against the dollar.",
    panels: [
      { title: "XOF per 1 unit of foreign currency", kind: "line", dec: 1, series: [
        { id: "xof_usd", name: "XOF per USD", short: "USD", c: "--s1" },
        { id: "peg", name: "XOF per EUR (fixed parity)", short: "EUR (fixed)", c: "--s2", dec: 2 }] },
      { title: "USD per 1 EUR (up = euro stronger)", kind: "line", dec: 3, series: [
        { id: "eurusd", name: "EUR/USD", short: "EUR/USD", c: "--s3" }] }],
    extraCaps: [{ title: "XOF per EUR (fixed parity)", units: "XOF per 1 EUR (up = XOF weaker)", freq: "Constant (legal parity)",
      source: "EU Council Decision 98/683/EC on exchange-rate matters in the CFA franc zone", url: EUROLEX,
      latest: "Not an observation: the parity is a constant, not a market quote",
      transform: "None. Drawn as the constant 655.957 (shown as 655.96) across the same dates as EUR/USD." }] },
  { id: "rer", title: "Real exchange rate against the US dollar",
    read: "Up means real depreciation of the XOF (Ivorian goods get cheaper in dollar terms). Down means real appreciation, the usual sign of overvaluation. The index shows change since 2010; it is not an estimate of the right level.",
    panels: [{ title: "Index, 2010 = 100", kind: "line", dec: 1, ref: { v: 100, label: "Base year 2010 = 100" }, series: [
      { id: "rer", name: "Real exchange rate vs USD", short: "RER", c: "--s1" }] }],
    ends: ["Real appreciation", "Real depreciation"] },
  { id: "cocoa", title: "Cocoa: priced in dollars, paid out in CFA francs",
    read: "The upper panel is the world price in USD. The lower panel is the same price converted at the month's average XOF/USD rate, which is what the exporter and the treasury receive in local currency.",
    panels: [
      { title: "USD per metric tonne", kind: "line", dec: 0, series: [{ id: "cocoa_usd", name: "Cocoa, USD per tonne", short: "USD", c: "--s1" }] },
      { title: "XOF million per metric tonne", kind: "line", dec: 2, series: [{ id: "cocoa_xof", name: "Cocoa, XOF million per tonne", short: "XOF", c: "--s2" }] }] },
  { id: "trade", title: "External balance on goods and services",
    read: "Positive is a surplus. This is goods and services together, the nearest series available; a goods-only balance was not found in the sources used.",
    panels: [{ title: "% of GDP", kind: "bar", dec: 1, zero: true, series: [{ id: "ci_trade_bal", name: "External balance, % of GDP", short: "Balance", c: "--s1" }] }] },
  { id: "infl", title: "Consumer price inflation",
    read: "Annual average, headline only. Core inflation is not published for Côte d'Ivoire in the sources used, and no proxy is shown.",
    panels: [{ title: "% year on year", kind: "line", dec: 1, zero: true, series: [{ id: "ci_infl", name: "Headline CPI inflation", short: "Headline", c: "--s1" }] }] },
  { id: "fiscal", title: "Public finances",
    read: "Deficits are negative. Pale or dashed marks are IMF projections, not outturns.",
    panels: [
      { title: "General government net lending/borrowing, % of GDP", kind: "bar", dec: 1, zero: true, series: [{ id: "ci_gov_bal", name: "Net lending/borrowing", short: "Balance", c: "--s1" }] },
      { title: "General government gross debt, % of GDP", kind: "line", dec: 1, series: [{ id: "ci_debt", name: "Gross debt", short: "Debt", c: "--s2" }] }] },
  { id: "growth", title: "Real GDP growth",
    read: "Year-on-year change in real GDP. Pale marks are IMF projections.",
    panels: [{ title: "% year on year", kind: "bar", dec: 1, zero: true, series: [{ id: "ci_gdp_growth", name: "Real GDP growth", short: "Growth", c: "--s1" }] }] },
];

// ---- helpers ---------------------------------------------------------------
const $ = (s, r = document) => r.querySelector(s);
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") e.textContent = v; else if (v != null) e.setAttribute(k, v);
  }
  for (const k of kids) if (k != null) e.append(k);
  return e;
}
function sv(tag, attrs = {}, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}
const fmtNum = (v, d) => Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
function fmtUtc(iso) {
  const d = new Date(iso);
  return d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}
const CHI = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Chicago", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZoneName: "short" });
function fmtChicago(iso) {
  const p = Object.fromEntries(CHI.formatToParts(new Date(iso)).map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute} ${p.timeZoneName}`;
}
const fmtBoth = iso => `${fmtUtc(iso)} (${fmtChicago(iso)}, Chicago)`;
function ago(iso) {
  const h = (Date.now() - new Date(iso).getTime()) / 36e5;
  if (h < 1) return "less than an hour ago";
  if (h < 48) return `${Math.round(h)} hours ago`;
  return `${Math.round(h / 24)} days ago`;
}
function niceTicks(lo, hi, n = 5) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const step0 = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(step0))), norm = step0 / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, t = [];
  for (let v = a; v <= b + step / 2; v += step) t.push(Math.abs(v) < step / 1e6 ? 0 : v);
  return t;
}
function css(name) { return `var(${name})`; }

// ---- data prep -------------------------------------------------------------
function seriesPoints(doc, id) {
  if (id === "peg") {
    const base = doc.series.xof_usd;
    return base.dates.map((d, i) => ({ t: Date.parse(d), v: doc.meta.peg_xof_per_eur, f: "", label: d, raw: d }));
  }
  const s = doc.series[id];
  const annual = s.freq === "annual", monthly = s.freq === "monthly";
  return s.dates.map((d, i) => ({
    t: annual ? Date.UTC(+d.slice(0, 4), 6, 1) : Date.parse(d), v: s.values[i], f: s.flags[i],
    label: annual ? d.slice(0, 4) : monthly ? d.slice(0, 7) : d, raw: d,
  }));
}
function nearest(pts, t) {
  let lo = 0, hi = pts.length - 1;
  while (lo < hi) { const m = (lo + hi) >> 1; if (pts[m].t < t) lo = m + 1; else hi = m; }
  if (lo > 0 && Math.abs(pts[lo - 1].t - t) <= Math.abs(pts[lo].t - t)) lo--;
  return lo;
}

// ---- badges and captions ---------------------------------------------------
function statusBadge(s) {
  if (s.status === "unavailable") return el("span", { class: "badge bad", text: "✕ No data" });
  if (s.status === "stale") return el("span", { class: "badge warn", text: `▲ Stale: last good data ${s.last_obs_label || "unknown"}` });
  if (s.warn) return el("span", { class: "badge warn", text: `▲ Older than expected (${s.age_days} days; limit ${s.limit_days})` });
  return el("span", { class: "badge ok", text: "✓ Refreshed OK" });
}
function captionFor(s) {
  const latest = el("dd", {});
  latest.append(s.last_obs_label ? `${s.last_obs_label} ` : "None ", statusBadge(s));
  if (s.proj_from) latest.append(` Projections from ${s.proj_from}.`);
  const src = el("dd", {}, el("a", { href: s.url, text: s.source }), ` (${s.series_id})`);
  const dl = el("dl", {},
    el("dt", { text: "Units" }), el("dd", { text: s.unit }),
    el("dt", { text: "Frequency" }), el("dd", { text: s.freq[0].toUpperCase() + s.freq.slice(1) }),
    el("dt", { text: "Source" }), src,
    el("dt", { text: "Latest observation" }), latest,
    el("dt", { text: "Transformation" }), el("dd", { text: s.transform }));
  if (s.error) dl.append(el("dt", { text: "Last error" }), el("dd", { text: s.error }));
  return el("section", {}, el("h3", { text: s.title }), dl);
}
function captionExtra(c) {
  return el("section", {}, el("h3", { text: c.title }), el("dl", {},
    el("dt", { text: "Units" }), el("dd", { text: c.units }),
    el("dt", { text: "Frequency" }), el("dd", { text: c.freq }),
    el("dt", { text: "Source" }), el("dd", {}, el("a", { href: c.url, text: c.source })),
    el("dt", { text: "Latest observation" }), el("dd", { text: c.latest }),
    el("dt", { text: "Transformation" }), el("dd", { text: c.transform })));
}

// ---- chart rendering -------------------------------------------------------
const tooltipEls = new WeakMap();

function renderChart(def, doc, host, from) {
  host.textContent = "";
  const ids = def.panels.flatMap(p => p.series.map(s => s.id));
  const missing = ids.filter(id => id !== "peg" && !doc.series[id].values.length);
  const x0 = Date.UTC(from, 0, 1);
  if (missing.length) {
    const s = doc.series[missing[0]];
    host.append(el("div", { class: "empty", role: "status",
      text: `No data for ${s.title}. ${s.error ? "Last error: " + s.error + ". " : ""}Nothing is estimated in its place; it will appear after the next successful refresh.` }));
    return;
  }
  const W = Math.max(280, Math.floor(host.clientWidth || host.parentElement.clientWidth || 800));
  const wide = W >= 720;
  const M = { l: 54, r: wide ? 118 : 14, t: 8, b: 4 };
  const ctx = { panels: [], def };

  // legend (>= 2 series, or when projections are drawn)
  const prepared = def.panels.map(p => ({ p, series: p.series.map(s => ({ s, pts: seriesPoints(doc, s.id).filter(q => q.t >= x0) })) }));
  const hasProj = prepared.some(pp => pp.series.some(x => x.pts.some(q => q.f === "proj")));
  if (ids.length >= 2 || hasProj) {
    const lg = el("div", { class: "legend" });
    for (const pp of prepared) for (const x of pp.series) {
      const k = pp.p.kind === "bar" ? el("i", { class: "bx", style: `background:${css(x.s.c)}` }) : el("i", { class: "ln", style: `border-color:${css(x.s.c)}` });
      lg.append(el("span", {}, k, x.s.name));
    }
    if (hasProj) lg.append(el("span", {}, el("i", { class: "ln dash", style: "border-color:var(--ink-3)" }), "IMF projection (pale or dashed)"));
    host.append(lg);
  }

  let xmax = x0;
  for (const pp of prepared) for (const x of pp.series) if (x.pts.length) xmax = Math.max(xmax, x.pts[x.pts.length - 1].t);
  const hasBar = def.panels.some(p => p.kind === "bar");
  const pad = hasBar ? YEAR_MS * 0.6 : 0;
  const xa = x0 - (hasBar ? YEAR_MS * 0.1 : 0), xb = xmax + pad;
  const plotW = W - M.l - M.r;
  const X = t => M.l + ((t - xa) / (xb - xa)) * plotW;
  const invX = px => xa + ((px - M.l) / plotW) * (xb - xa);
  const spanY = (xb - xa) / YEAR_MS, maxLabels = Math.max(2, Math.floor(plotW / 52));
  const stepY = [1, 2, 5, 10].find(k => spanY / k <= maxLabels) || 10;

  const tip = el("div", { class: "tip", role: "status" });
  host.style.position = "relative";
  const lineCtx = [];

  prepared.forEach((pp, pi) => {
    const last = pi === prepared.length - 1;
    const H = (pp.p.kind === "bar" ? 190 : def.panels.length > 1 && pi > 0 ? 150 : 230) - (wide ? 0 : 40);
    const m = { ...M, b: last ? 22 : 4 };
    const plotH = H - m.t - m.b;
    host.append(el("p", { class: "panel-title", text: pp.p.title }));
    const vals = pp.series.flatMap(x => x.pts.map(q => q.v));
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (pp.p.ref) { lo = Math.min(lo, pp.p.ref.v); hi = Math.max(hi, pp.p.ref.v); }
    if (pp.p.zero || pp.p.kind === "bar") { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (pp.p.kind === "line") { const pd = (hi - lo) * 0.06 || 1; lo -= pd; hi += pd; }
    const ticks = niceTicks(lo, hi, 4), ylo = ticks[0], yhi = ticks[ticks.length - 1];
    const Y = v => m.t + (1 - (v - ylo) / (yhi - ylo)) * plotH;

    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", tabindex: "0",
      "aria-label": `${def.title}. ${pp.p.title}. ${pp.series.map(x => x.s.name).join(", ")}. Use left and right arrow keys to read values.` });
    // bands
    for (const b of BANDS) {
      const a = Math.max(b.from, xa), z = Math.min(b.to, xb);
      if (z > a) svg.append(sv("rect", { x: X(a), y: m.t, width: X(z) - X(a), height: plotH, style: "fill:var(--band)" }));
    }
    // grid + y labels
    for (const t of ticks) {
      svg.append(sv("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), style: "stroke:var(--grid)", "stroke-width": 1 }));
      const tstep = ticks[1] - ticks[0], tdec = tstep >= 1 ? 0 : Math.min(3, Math.ceil(-Math.log10(tstep) - 1e-9));
      svg.append(sv("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, fmtNum(t, tdec)));
    }
    // x labels
    if (last) {
      for (let y = Math.ceil(new Date(xa).getUTCFullYear() / stepY) * stepY; Date.UTC(y, 0, 1) <= xb; y += stepY) {
        const tx = Date.UTC(y, 0, 1); if (tx < xa) continue;
        svg.append(sv("text", { x: X(tx), y: H - 4, "text-anchor": "middle" }, String(y)));
      }
    }
    // reference / zero lines
    if (pp.p.zero) svg.append(sv("line", { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), style: "stroke:var(--ink-3)", "stroke-width": 1 }));
    if (pp.p.ref) {
      svg.append(sv("line", { x1: m.l, x2: W - m.r, y1: Y(pp.p.ref.v), y2: Y(pp.p.ref.v), style: "stroke:var(--ink-3)", "stroke-dasharray": "4 4", "stroke-width": 1 }));
      svg.append(sv("text", { x: W - m.r - 4, y: Y(pp.p.ref.v) - 5, "text-anchor": "end" }, pp.p.ref.label));
    }
    // marks
    const labels = [];
    pp.series.forEach(x => {
      if (!x.pts.length) return;
      if (pp.p.kind === "line") {
        const act = x.pts.filter(q => q.f !== "proj"), proj = x.pts.filter(q => q.f === "proj");
        const path = a => a.map((q, i) => `${i ? "L" : "M"}${X(q.t).toFixed(1)},${Y(q.v).toFixed(1)}`).join("");
        if (act.length) svg.append(sv("path", { d: path(act), fill: "none", style: `stroke:${css(x.s.c)}`, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
        if (proj.length) {
          const seg = act.length ? [act[act.length - 1], ...proj] : proj;
          svg.append(sv("path", { d: path(seg), fill: "none", style: `stroke:${css(x.s.c)}`, "stroke-width": 2, "stroke-dasharray": "5 4" }));
        }
        const e = act.length ? act[act.length - 1] : proj[proj.length - 1];
        svg.append(sv("circle", { cx: X(e.t), cy: Y(e.v), r: 4, style: `fill:${css(x.s.c)};stroke:var(--surface)`, "stroke-width": 2 }));
        if (wide) labels.push({ y: Y(e.v), x: X(e.t), text: `${x.s.short} ${fmtNum(e.v, x.s.dec ?? pp.p.dec)}`, above: proj.length > 0 });
      } else {
        const n = Math.max(1, (xb - xa) / YEAR_MS), bw = Math.max(3, Math.min(22, (plotW / n) * 0.62));
        x.pts.forEach(q => {
          const y1 = Y(Math.max(q.v, 0)), y2 = Y(Math.min(q.v, 0)), r = Math.min(4, bw / 2, Math.abs(y2 - y1));
          const top = q.v >= 0, xl = X(q.t) - bw / 2, xr = xl + bw;
          const d = top
            ? `M${xl},${y2} L${xl},${y1 + r} Q${xl},${y1} ${xl + r},${y1} L${xr - r},${y1} Q${xr},${y1} ${xr},${y1 + r} L${xr},${y2} Z`
            : `M${xl},${y1} L${xl},${y2 - r} Q${xl},${y2} ${xl + r},${y2} L${xr - r},${y2} Q${xr},${y2} ${xr},${y2 - r} L${xr},${y1} Z`;
          const proj = q.f === "proj";
          const bar = sv("path", { d, style: `fill:${css(x.s.c)};fill-opacity:${proj ? 0.38 : 1};stroke:${proj ? css(x.s.c) : "none"}`, "stroke-dasharray": proj ? "3 2" : "none", class: "bar" });
          bar.dataset.t = q.t; svg.append(bar);
        });
      }
    });
    // direct labels, nudged apart
    labels.sort((a, b) => a.y - b.y);
    for (let i = 1; i < labels.length; i++) if (labels[i].y - labels[i - 1].y < 14) labels[i].y = labels[i - 1].y + 14;
    labels.forEach(l => svg.append(l.above
      ? sv("text", { x: l.x - 8, y: l.y - 10, class: "lab", "text-anchor": "end" }, l.text)
      : sv("text", { x: l.x + 9, y: l.y + 4, class: "lab" }, l.text)));
    if (def.ends && pp.p.kind === "line") {
      svg.append(sv("text", { x: m.l + 4, y: m.t + 12 }, `▲ ${def.ends[1]}`));
      svg.append(sv("text", { x: m.l + 4, y: H - m.b - 6 }, `▼ ${def.ends[0]}`));
    }
    // crosshair + hit layer
    const cross = sv("line", { y1: m.t, y2: m.t + plotH, style: "stroke:var(--ink-2)", "stroke-width": 1, visibility: "hidden" });
    const dots = pp.series.map(x => { const c = sv("circle", { r: 4.5, style: `fill:${css(x.s.c)};stroke:var(--surface)`, "stroke-width": 2, visibility: "hidden" }); return c; });
    if (pp.p.kind === "line") { svg.append(cross); dots.forEach(d => svg.append(d)); }
    const hit = sv("rect", { x: m.l, y: m.t, width: plotW, height: plotH, fill: "transparent" });
    svg.append(hit);
    const panel = { svg, cross, dots, pp, X, Y, m, plotH, kind: pp.p.kind, idx: null };
    ctx.panels.push(panel);
    if (pp.p.kind === "line") lineCtx.push(panel);
    host.append(el("div", { class: "plot" }, svg));
    hit.addEventListener("pointermove", e => { const r = svg.getBoundingClientRect(); show(panel, invX(((e.clientX - r.left) / r.width) * W)); });
    hit.addEventListener("pointerleave", hide);
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", e => {
      if (e.key === "Escape") return hide();
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const pts = pp.series[0].pts; if (!pts.length) return;
      let i = panel.idx == null ? pts.length - 1 : panel.idx + (e.key === "ArrowRight" ? 1 : -1);
      i = Math.max(0, Math.min(pts.length - 1, i)); show(panel, pts[i].t);
    });
  });

  function hide() {
    tip.classList.remove("on");
    ctx.panels.forEach(p => { p.cross.setAttribute("visibility", "hidden"); p.dots.forEach(d => d.setAttribute("visibility", "hidden")); p.idx = null; p.svg.querySelectorAll(".bar").forEach(b => b.style.opacity = ""); });
  }
  function show(panel, t) {
    const rows = []; let label = "";
    const isLine = panel.kind === "line";
    const targets = isLine ? lineCtx : [panel];
    let tx = null;
    targets.forEach(p => p.pp.series.forEach((x, k) => {
      if (!x.pts.length) return;
      const i = nearest(x.pts, t), q = x.pts[i];
      if (p === panel && k === 0) { panel.idx = i; }
      if (tx == null) { tx = q.t; label = q.label + (q.f === "proj" ? " (IMF projection)" : ""); }
      rows.push({ name: x.s.name, c: x.s.c, v: fmtNum(q.v, x.s.dec ?? p.pp.p.dec), proj: q.f === "proj" });
      if (isLine) { p.dots[k].setAttribute("cx", p.X(q.t)); p.dots[k].setAttribute("cy", p.Y(q.v)); p.dots[k].setAttribute("visibility", "visible"); }
    }));
    if (isLine) lineCtx.forEach(p => { p.cross.setAttribute("x1", p.X(tx)); p.cross.setAttribute("x2", p.X(tx)); p.cross.setAttribute("visibility", "visible"); });
    else {
      panel.svg.querySelectorAll(".bar").forEach(b => b.style.opacity = Math.abs(+b.dataset.t - tx) < 1 ? "1" : "0.55");
    }
    tip.textContent = "";
    tip.append(el("div", { class: "d", text: label }));
    rows.forEach(r => tip.append(el("div", { class: "r" }, el("span", { class: "k" }, el("b", { style: `border-color:${css(r.c)}` }), r.name), el("span", { class: "v", text: r.v }))));
    const px = panel.X(tx);
    const hostW = host.clientWidth, w = 200;
    tip.style.left = Math.max(0, Math.min(hostW - w, px + 14 > hostW - w ? px - w - 14 : px + 14)) + "px";
    tip.style.top = (host.querySelector(".plot") ? panel.svg.parentElement.offsetTop + 8 : 8) + "px";
    tip.classList.add("on");
  }
  host.append(tip);
}

// ---- table view (lazy, respects range filter) ------------------------------
function buildTable(def, doc, from) {
  const ids = def.panels.flatMap(p => p.series.map(s => ({ id: s.id, name: s.name, dec: s.dec ?? p.dec })));
  const cols = ids.map(i => ({ ...i, pts: seriesPoints(doc, i.id).filter(q => q.t >= Date.UTC(from, 0, 1)) }));
  if (!cols[0].pts.length) return el("p", { text: "No data." });
  const maps = cols.map(c => new Map(c.pts.map(q => [q.raw, q])));
  const keys = cols[0].pts.map(q => q.raw).reverse();
  const limit = 400, shown = keys.slice(0, limit);
  const table = el("table", {});
  table.append(el("thead", {}, el("tr", {}, el("th", { text: "Period" }), ...cols.map(c => el("th", { text: c.name })))));
  const tb = el("tbody", {});
  shown.forEach(k => {
    const tr = el("tr", {}, el("td", { text: maps[0].get(k).label + (maps[0].get(k).f === "proj" ? " (proj.)" : "") }));
    cols.forEach((c, i) => { const q = maps[i].get(k); tr.append(el("td", { text: q ? fmtNum(q.v, c.dec) : "" })); });
    tb.append(tr);
  });
  table.append(tb);
  const wrap = el("div", { class: "scroll" }, table);
  const note = keys.length > limit ? el("p", { text: `Showing the latest ${limit} of ${keys.length} rows. The full series is in the CSV files.` }) : null;
  return el("div", {}, wrap, note);
}

// ---- page ------------------------------------------------------------------
async function main() {
  let doc;
  try {
    const r = await fetch("data.json", { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    doc = await r.json();
  } catch (e) {
    $("#st-ok").textContent = "Data file could not be loaded";
    $("#banner").append(el("div", { class: "banner bad", role: "alert", text: `data.json failed to load (${e.message}). Reload the page; if it persists the last deploy is broken.` }));
    return;
  }
  const m = doc.meta, S = doc.series;

  // two separate timestamps
  if (m.last_successful_refresh) {
    $("#st-ok").textContent = fmtUtc(m.last_successful_refresh);
    $("#st-ok-chi").textContent = `${fmtChicago(m.last_successful_refresh)} in Chicago`;
    $("#st-ok-sub").textContent = `${ago(m.last_successful_refresh)}. Last attempt: ${m.last_attempt ? fmtBoth(m.last_attempt) : "unknown"}.`;
  } else {
    $("#st-ok").textContent = "Never";
    $("#st-ok-sub").textContent = `No refresh has fetched every series yet. Last attempt: ${m.last_attempt ? fmtBoth(m.last_attempt) : "unknown"}.`;
  }
  $("#gen").textContent = fmtBoth(m.generated);

  // banner for problems
  const issues = Object.values(S).filter(s => s.status !== "ok" || s.warn);
  const bn = $("#banner");
  if (issues.length) {
    const ul = el("ul", {});
    issues.forEach(s => ul.append(el("li", { text: `${s.title}: ${s.status === "unavailable" ? "no data" : s.status === "stale" ? `stale, last good observation ${s.last_obs_label}` : `latest observation ${s.last_obs_label} is ${s.age_days} days past its period end (limit ${s.limit_days})`}` })));
    bn.append(el("div", { class: "banner" + (issues.some(s => s.status === "unavailable") ? " bad" : ""), role: "status" }, el("strong", { text: `${issues.length} of ${Object.keys(S).length} series need attention` }), ul));
  }

  // controls
  let from = 2005;
  const range = $("#range");
  [2005, 2010, 2015, 2020].forEach(y => {
    const b = el("button", { type: "button", "aria-pressed": String(y === from), text: y === 2005 ? "2005 (all)" : String(y) });
    b.addEventListener("click", () => { from = y; range.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); renderAll(); });
    range.append(b);
  });
  const themeBtn = $("#theme");
  const modes = ["auto", "light", "dark"];
  let mode = document.documentElement.dataset.theme || "auto";
  const applyTheme = () => {
    if (mode === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = mode;
    themeBtn.textContent = `Theme: ${mode}`;
    try { mode === "auto" ? localStorage.removeItem("theme") : localStorage.setItem("theme", mode); } catch (e) {}
  };
  themeBtn.addEventListener("click", () => { mode = modes[(modes.indexOf(mode) + 1) % 3]; applyTheme(); });
  applyTheme();

  // chart sections
  const root = $("#charts"), hosts = [], tableBoxes = [];
  CHARTS.forEach(def => {
    const sec = el("section", { class: "chart", id: def.id });
    sec.append(el("h2", { text: def.title }), el("p", { class: "read", text: def.read }));
    const host = el("div", {}); sec.append(host);
    const caps = el("div", { class: "cap" });
    const seen = new Set();
    def.panels.flatMap(p => p.series).forEach(s => { if (s.id !== "peg" && !seen.has(s.id)) { seen.add(s.id); caps.append(captionFor(S[s.id])); } });
    (def.extraCaps || []).forEach(c => caps.append(captionExtra(c)));
    sec.append(caps);
    const det = el("details", { class: "tbl" }, el("summary", { text: "Table view" }));
    const box = el("div", {}); det.append(box);
    det.addEventListener("toggle", () => { if (det.open) { box.textContent = ""; box.append(buildTable(def, doc, from)); } });
    sec.append(det);
    root.append(sec);
    hosts.push({ def, host }); tableBoxes.push({ def, det, box });
  });
  function renderAll() {
    hosts.forEach(h => renderChart(h.def, doc, h.host, from));
    tableBoxes.forEach(t => { if (t.det.open) { t.box.textContent = ""; t.box.append(buildTable(t.def, doc, from)); } });
  }
  renderAll();
  let lastW = root.clientWidth, timer;
  new ResizeObserver(() => { clearTimeout(timer); timer = setTimeout(() => { if (root.clientWidth !== lastW) { lastW = root.clientWidth; renderAll(); } }, 120); }).observe(root);

  // gaps
  const gl = $("#gap-list");
  doc.unavailable.forEach(g => gl.append(el("div", { class: "gap" }, el("h3", { text: g.title }),
    el("p", { text: g.why }), el("p", {}, el("strong", { text: "Fallback: " }), g.fallback + " "), el("p", {}, el("a", { href: g.link, text: "Where to look" })))));

  // status table
  const t = $("#status-table");
  t.append(el("thead", {}, el("tr", {}, ...["Series", "Status", "Last good fetch", "Latest observation", "Age / limit", "Data"].map(h => el("th", { text: h })))));
  const tb = el("tbody", {});
  Object.values(S).forEach(s => tb.append(el("tr", {},
    el("td", { text: s.title }), el("td", {}, statusBadge(s)),
    el("td", { style: "white-space:nowrap" }, ...(s.last_fetch_ok ? [fmtUtc(s.last_fetch_ok), document.createElement("br"), fmtChicago(s.last_fetch_ok)] : ["never"])),
    el("td", { text: s.last_obs_label || "none" }),
    el("td", { text: s.age_days == null ? "" : `${s.age_days} / ${s.limit_days} days` }),
    el("td", {}, s.rows ? el("a", { href: `data/${s.id}.csv`, text: "CSV" }) : "none"))));
  t.append(tb);
}
main();
