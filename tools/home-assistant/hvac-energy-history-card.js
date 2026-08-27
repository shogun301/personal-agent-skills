const DEFAULTS = {
  hours_to_show: 24,
  today: false,
  selected_date: false,
  temperature_min: 70,
  temperature_max: 84,
};

class HvacEnergyHistoryCard extends HTMLElement {
  setConfig(config) {
    if (!config?.entities) throw new Error("entities is required");
    this.config = { ...DEFAULTS, ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._lastLoad = 0;
    this._periodKey = null;
    this._renderShell();
  }

  set hass(hass) {
    this._hass = hass;
    this._maybeLoad();
  }

  connectedCallback() {
    this._poll = setInterval(() => this._maybeLoad(), 1500);
    this._resizeObserver = new ResizeObserver(() => {
      clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => this._renderChart(), 80);
    });
    this._resizeObserver.observe(this);
  }

  disconnectedCallback() {
    clearInterval(this._poll);
    this._resizeObserver?.disconnect();
    clearTimeout(this._resizeTimer);
  }

  getCardSize() {
    return 7;
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; min-width: 0; max-width: 100%; }
        ha-card { overflow: hidden; min-width: 0; max-width: 100%; }
        .head { padding: 18px 20px 4px; display: flex; align-items: flex-start; gap: 12px; }
        .titles { min-width: 0; flex: 1; }
        .title { color: var(--primary-text-color); font-size: 22px; line-height: 1.25; }
        .subtitle { margin-top: 4px; color: var(--secondary-text-color); font-size: 13px; }
        button { border: 0; background: transparent; color: var(--secondary-text-color); cursor: pointer; font-size: 21px; padding: 2px 6px; }
        .legend { display: flex; flex-wrap: wrap; gap: 7px 15px; padding: 7px 20px 2px; color: var(--secondary-text-color); font-size: 12px; }
        .key { display: inline-flex; align-items: center; white-space: nowrap; }
        .swatch { width: 18px; height: 3px; margin-right: 6px; border-radius: 2px; background: var(--c); }
        .swatch.bold { height: 5px; }
        .fill { width: 15px; height: 11px; margin-right: 6px; border-radius: 2px; background: var(--c); opacity: .28; }
        .wrap { position: relative; min-width: 0; padding: 2px 8px 12px; overflow: hidden; }
        svg { display: block; width: 100%; max-width: 100%; height: auto; overflow: hidden; }
        .tip { display: none; position: absolute; z-index: 3; pointer-events: none; padding: 8px 10px; border-radius: 7px; background: var(--card-background-color, #222); color: var(--primary-text-color); box-shadow: 0 2px 9px rgba(0,0,0,.35); font-size: 12px; line-height: 1.45; white-space: nowrap; }
        .status { min-height: 380px; display: grid; place-items: center; color: var(--secondary-text-color); padding: 20px; text-align: center; }
        @media (max-width: 520px) {
          .head { padding: 14px 12px 3px; gap: 8px; }
          .title { font-size: 18px; }
          .subtitle { font-size: 12px; }
          .legend { gap: 6px 10px; padding: 6px 12px 2px; font-size: 11px; }
          .swatch { width: 14px; }
          .wrap { padding: 2px 4px 10px; }
          .status { min-height: 300px; }
        }
      </style>
      <ha-card>
        <div class="head">
          <div class="titles">
            <div class="title"></div>
            <div class="subtitle">Temperature and setpoint: left axis · Battery SOC: right axis</div>
          </div>
          <button title="Refresh history" aria-label="Refresh history">↻</button>
        </div>
        <div class="legend">
          <span class="key"><i class="swatch" style="--c:#3B82F6"></i>Bedroom temperature</span>
          <span class="key"><i class="swatch bold" style="--c:#1D4ED8"></i>Bedroom setpoint</span>
          <span class="key"><i class="swatch" style="--c:#F97316"></i>Living temperature</span>
          <span class="key"><i class="swatch bold" style="--c:#C2410C"></i>Living setpoint</span>
          <span class="key"><i class="swatch" style="--c:#22A06B"></i>Battery SOC</span>
          <span class="key"><i class="fill" style="--c:#3B82F6"></i>Bedroom AC on</span>
          <span class="key"><i class="fill" style="--c:#F97316"></i>Living AC on</span>
          <span class="key">◆ command issued</span>
        </div>
        <div class="wrap"><div class="status">Loading history…</div><div class="tip"></div></div>
      </ha-card>`;
    this.shadowRoot.querySelector(".title").textContent = this.config.title || "Thermostats, AC & battery SOC — today";
    this.shadowRoot.querySelector("button").addEventListener("click", () => this._load(true));
  }

  _collection() {
    if (!this.config.selected_date) return null;
    const connection = this._hass?.connection;
    if (!connection) return null;
    const key = this.config.collection_key
      ? `_${this.config.collection_key}`
      : (this._hass.panelUrl ? `_energy_${this._hass.panelUrl}` : "_energy");
    return connection[key] || null;
  }

  _range() {
    const now = new Date();
    if (this.config.selected_date) {
      const collection = this._collection();
      const selectedStart = collection?.start ? new Date(collection.start) : null;
      const selectedEnd = collection?.end ? new Date(collection.end) : null;
      if (selectedStart && selectedEnd && Number.isFinite(selectedStart.getTime()) && Number.isFinite(selectedEnd.getTime()) && selectedEnd > selectedStart) {
        const start = new Date(selectedStart.getFullYear(), selectedStart.getMonth(), selectedStart.getDate());
        const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 1);
        return { start, end };
      }
      return {
        start: new Date(now.getFullYear(), now.getMonth(), now.getDate()),
        end: new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1),
      };
    }
    if (this.config.today) {
      return {
        start: new Date(now.getFullYear(), now.getMonth(), now.getDate()),
        end: new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1),
      };
    }
    return { start: new Date(now.getTime() - this.config.hours_to_show * 3600000), end: now };
  }

  _maybeLoad(force = false) {
    if (!this._hass || this._loading) return;
    const { start, end } = this._range();
    const periodKey = `${start.toISOString()}|${end.toISOString()}`;
    if (!force && periodKey === this._periodKey && Date.now() - this._lastLoad < 60000) return;
    this._load(force, { start, end, periodKey });
  }

  async _load(force = false, range = null) {
    if (!this._hass || this._loading) return;
    const selectedRange = range || (() => {
      const { start, end } = this._range();
      return { start, end, periodKey: `${start.toISOString()}|${end.toISOString()}` };
    })();
    if (!force && selectedRange.periodKey === this._periodKey && Date.now() - this._lastLoad < 60000) return;
    this._loading = true;
    this._error = null;
    try {
      const { start, end, periodKey } = selectedRange;
      const ids = Object.values(this.config.entities).filter(Boolean);
      const path = `history/period/${encodeURIComponent(start.toISOString())}?filter_entity_id=${encodeURIComponent(ids.join(","))}&end_time=${encodeURIComponent(end.toISOString())}&minimal_response&no_attributes`;
      const groups = await this._hass.callApi("GET", path);
      const byId = {};
      for (const group of groups || []) {
        if (group?.length && group[0].entity_id) byId[group[0].entity_id] = group;
      }
      for (const id of ids) {
        if (!byId[id]?.length && this._hass.states[id]) byId[id] = [this._hass.states[id]];
      }
      this._data = { start, end, byId };
      this._periodKey = periodKey;
      this._lastLoad = Date.now();
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this._renderChart();
    }
  }

  _points(id, numeric = true) {
    const { start, end, byId } = this._data;
    const raw = byId[id] || [];
    const pts = raw.map((s) => ({
      t: new Date(s.last_changed || s.last_updated).getTime(),
      v: numeric ? Number(s.state) : s.state,
    })).filter((p) => Number.isFinite(p.t) && (!numeric || Number.isFinite(p.v)))
      .sort((a, b) => a.t - b.t);
    if (!pts.length) return pts;
    const lo = start.getTime(), hi = end.getTime();
    const dataHi = Math.min(hi, Date.now());
    const bounded = pts.filter((p) => p.t >= lo && p.t <= hi);
    const seed = [...pts].reverse().find((p) => p.t <= lo) || bounded[0] || pts[0];
    if (!bounded.length || bounded[0].t > lo) bounded.unshift({ t: lo, v: seed.v });
    else bounded[0] = { ...bounded[0], t: Math.max(lo, bounded[0].t) };
    const last = bounded[bounded.length - 1];
    if (last.t < dataHi) bounded.push({ t: dataHi, v: last.v });
    return bounded;
  }

  _stepPath(points, x, y) {
    if (!points.length) return "";
    let d = `M ${x(points[0].t)} ${y(points[0].v)}`;
    for (let i = 1; i < points.length; i++) d += ` H ${x(points[i].t)} V ${y(points[i].v)}`;
    return d;
  }

  _linePath(points, x, y) {
    return points.map((p, i) => `${i ? "L" : "M"} ${x(p.t)} ${y(p.v)}`).join(" ");
  }

  _areaPath(points, x, y, bottom) {
    if (!points.length) return "";
    return `${this._linePath(points, x, y)} L ${x(points.at(-1).t)} ${bottom} L ${x(points[0].t)} ${bottom} Z`;
  }

  _onIntervals(points, lo, hi) {
    const out = [];
    const dataHi = Math.min(hi, Date.now());
    for (let i = 0; i < points.length; i++) {
      if (points[i].v !== "on") continue;
      const a = Math.max(lo, points[i].t);
      const b = Math.min(dataHi, points[i + 1]?.t ?? dataHi);
      if (b > a) out.push([a, b]);
    }
    return out;
  }

  _commands(id, room) {
    const rows = this._data.byId[id] || [];
    const lo = this._data.start.getTime(), hi = this._data.end.getTime();
    return rows.map((s) => {
      const t = new Date(s.last_changed || s.last_updated).getTime();
      const raw = String(s.state || "").trim();
      if (!raw || ["unknown", "unavailable", "none", "null"].includes(raw.toLowerCase()) || t < lo || t > hi) return null;
      let parsed = {};
      try { parsed = JSON.parse(raw); } catch (_) { parsed = { detail: raw }; }
      const source = parsed.source || parsed.reason || "thermostat command";
      const target = parsed.target_temperature ?? parsed.temperature ?? parsed.target ?? parsed.setpoint;
      return { t, room, text: `${room}: ${source}${target != null ? ` · ${target} °F` : ""}` };
    }).filter(Boolean);
  }

  _valueAt(points, t) {
    if (!points.length) return null;
    let v = points[0].v;
    for (const p of points) { if (p.t > t) break; v = p.v; }
    return v;
  }

  _renderChart() {
    const wrap = this.shadowRoot?.querySelector(".wrap");
    if (!wrap) return;
    if (this._error) {
      wrap.querySelector(".status")?.remove();
      wrap.insertAdjacentHTML("afterbegin", `<div class="status">Could not load chart history.<br>${this._esc(this._error)}</div>`);
      return;
    }
    if (!this._data) return;

    wrap.querySelector(".status")?.remove();
    wrap.querySelector("svg")?.remove();
    const e = this.config.entities;
    const bedTemp = this._points(e.bedroom_temperature);
    const bedSet = this._points(e.bedroom_setpoint);
    const liveTemp = this._points(e.living_temperature);
    const liveSet = this._points(e.living_setpoint);
    const soc = this._points(e.battery_soc);
    const bedAc = this._points(e.bedroom_ac, false);
    const liveAc = this._points(e.living_ac, false);
    const commands = [
      ...this._commands(e.bedroom_command, "Bedroom"),
      ...this._commands(e.living_command, "Living"),
    ].sort((a, b) => a.t - b.t);

    const width = Math.round(wrap.getBoundingClientRect().width - 16);
    if (width < 180) return;
    const compact = width < 520;
    const height = compact ? 340 : 420;
    const left = compact ? 42 : 52, right = compact ? 44 : 58, top = 18, bottom = 42;
    const plotW = width - left - right, plotH = height - top - bottom;
    const lo = this._data.start.getTime(), hi = this._data.end.getTime();
    const x = (t) => left + ((t - lo) / (hi - lo)) * plotW;
    const tMin = Number(this.config.temperature_min), tMax = Number(this.config.temperature_max);
    const yT = (v) => top + ((tMax - v) / (tMax - tMin)) * plotH;
    const yS = (v) => top + ((100 - v) / 100) * plotH;
    const esc = (s) => this._esc(s);

    const grid = [];
    const fontSize = compact ? 10 : 12;
    for (let v = tMin; v <= tMax + .001; v += compact ? 4 : 2) {
      const yy = yT(v);
      grid.push(`<line x1="${left}" y1="${yy}" x2="${left + plotW}" y2="${yy}" stroke="var(--divider-color)" opacity=".7"/>`);
      grid.push(`<text x="${left - 6}" y="${yy + 4}" text-anchor="end" fill="var(--secondary-text-color)" font-size="${fontSize}">${v}°</text>`);
    }
    for (const v of [0, 25, 50, 75, 100]) {
      grid.push(`<text x="${left + plotW + 6}" y="${yS(v) + 4}" fill="var(--secondary-text-color)" font-size="${fontSize}">${v}%</text>`);
    }
    const tf = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
    const df = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
    const hourMs = 60 * 60 * 1000;
    const hourCount = Math.round((hi - lo) / hourMs);
    for (let hourIndex = 0; hourIndex <= hourCount; hourIndex++) {
      const hourTime = lo + hourIndex * hourMs;
      const hourX = x(hourTime);
      grid.push(`<line x1="${hourX}" y1="${top}" x2="${hourX}" y2="${top + plotH}" stroke="var(--divider-color)" opacity=".22"/>`);
    }

    const tickCount = compact ? 3 : 6;
    for (let i = 0; i <= tickCount; i++) {
      const tt = lo + (hi - lo) * i / tickCount, xx = x(tt), dt = new Date(tt);
      grid.push(`<line x1="${xx}" y1="${top}" x2="${xx}" y2="${top + plotH}" stroke="var(--divider-color)" opacity=".45"/>`);
      const tickLabel = i === 0 ? df.format(dt) : tf.format(dt);
      grid.push(`<text x="${xx}" y="${height - 18}" text-anchor="middle" fill="var(--secondary-text-color)" font-size="${fontSize}">${tickLabel}</text>`);
    }

    const clips = (intervals) => intervals.map(([a, b]) => `<rect x="${x(a)}" y="${top}" width="${Math.max(1, x(b) - x(a))}" height="${plotH}"/>`).join("");
    const commandSvg = commands.map((c) => {
      const xx = x(c.t), color = c.room === "Bedroom" ? "#1D4ED8" : "#C2410C";
      const when = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" }).format(new Date(c.t));
      return `<g><title>${esc(`${when} · ${c.text}`)}</title><line x1="${xx}" y1="${top}" x2="${xx}" y2="${top + plotH}" stroke="${color}" stroke-width="1.5" stroke-dasharray="4 4" opacity=".8"/><path d="M ${xx} ${top - 1} l 5 7 l -5 7 l -5 -7 z" fill="${color}"/></g>`;
    }).join("");

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.innerHTML = `
      <defs>
        <clipPath id="bed-ac-${this._uid()}">${clips(this._onIntervals(bedAc, lo, hi))}</clipPath>
        <clipPath id="live-ac-${this._uid()}">${clips(this._onIntervals(liveAc, lo, hi))}</clipPath>
        <clipPath id="plot-${this._uid()}"><rect x="${left}" y="${top}" width="${plotW}" height="${plotH}"/></clipPath>
      </defs>
      <g>${grid.join("")}</g>
      <g clip-path="url(#plot-${this._uid()})">
        <path d="${this._areaPath(bedTemp, x, yT, top + plotH)}" fill="#3B82F6" opacity=".20" stroke="none" clip-path="url(#bed-ac-${this._uid()})"/>
        <path d="${this._areaPath(liveTemp, x, yT, top + plotH)}" fill="#F97316" opacity=".18" stroke="none" clip-path="url(#live-ac-${this._uid()})"/>
        ${commandSvg}
        <path d="${this._linePath(bedTemp, x, yT)}" fill="none" stroke="#3B82F6" stroke-width="2.2"/>
        <path d="${this._stepPath(bedSet, x, yT)}" fill="none" stroke="#1D4ED8" stroke-width="4.5"/>
        <path d="${this._linePath(liveTemp, x, yT)}" fill="none" stroke="#F97316" stroke-width="2.2"/>
        <path d="${this._stepPath(liveSet, x, yT)}" fill="none" stroke="#C2410C" stroke-width="4.5"/>
        <path d="${this._linePath(soc, x, yS)}" fill="none" stroke="#22A06B" stroke-width="2.5"/>
        <line class="cross" x1="0" y1="${top}" x2="0" y2="${top + plotH}" stroke="var(--primary-text-color)" stroke-width="1" opacity=".55" style="display:none"/>
      </g>
      <text x="${left}" y="12" fill="var(--secondary-text-color)" font-size="12" font-weight="600">°F</text>
      <text x="${left + plotW + 4}" y="12" fill="#22A06B" font-size="12" font-weight="600">SOC</text>
      <rect class="hit" x="${left}" y="${top}" width="${plotW}" height="${plotH}" fill="transparent"/>
    `;
    wrap.insertBefore(svg, wrap.querySelector(".tip"));

    const tip = wrap.querySelector(".tip"), cross = svg.querySelector(".cross"), hit = svg.querySelector(".hit");
    const rows = [
      ["Bedroom temp", bedTemp, "°F"], ["Bedroom setpoint", bedSet, "°F"],
      ["Living temp", liveTemp, "°F"], ["Living setpoint", liveSet, "°F"],
      ["Battery SOC", soc, "%"],
    ];
    hit.addEventListener("pointermove", (ev) => {
      const rect = svg.getBoundingClientRect(), px = ev.clientX - rect.left;
      const tt = lo + Math.max(0, Math.min(1, (px - left) / plotW)) * (hi - lo);
      cross.style.display = ""; cross.setAttribute("x1", px); cross.setAttribute("x2", px);
      const values = rows.map(([name, pts, unit]) => { const v = this._valueAt(pts, tt); return `${name}: ${v == null ? "—" : `${Number(v).toFixed(unit === "%" ? 0 : 1)}${unit}`}`; });
      tip.textContent = `${new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(tt))}\n${values.join("\n")}`;
      tip.style.whiteSpace = "pre-line"; tip.style.display = "block";
      const localX = ev.clientX - wrap.getBoundingClientRect().left;
      tip.style.left = `${Math.min(Math.max(8, localX + 12), wrap.clientWidth - 190)}px`;
      tip.style.top = `${Math.max(8, ev.clientY - wrap.getBoundingClientRect().top - 80)}px`;
    });
    hit.addEventListener("pointerleave", () => { cross.style.display = "none"; tip.style.display = "none"; });
  }

  _uid() {
    if (!this.__uid) this.__uid = Math.random().toString(36).slice(2, 9);
    return this.__uid;
  }

  _esc(value) {
    return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
}

const POWER_SERIES = [
  ["solar", "Solar generation", "#3B82F6"],
  ["consumption", "Total consumption", "#FF6B57"],
  ["grid_import", "Grid import", "#FBBF24"],
  ["battery_charging", "Battery charging", "#22A06B"],
  ["battery_discharging", "Battery discharging", "#A78BFA"],
];

class SiteBatteryPowerHistoryCard extends HTMLElement {
  setConfig(config) {
    if (!config?.entities) throw new Error("entities is required");
    this.config = { ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._periodKey = null;
    this._renderShell();
  }

  set hass(hass) {
    this._hass = hass;
    this._maybeLoad();
  }

  connectedCallback() {
    this._poll = setInterval(() => this._maybeLoad(), 1500);
    this._resizeObserver = new ResizeObserver(() => {
      clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => this._renderChart(), 80);
    });
    this._resizeObserver.observe(this);
  }

  disconnectedCallback() {
    clearInterval(this._poll);
    clearTimeout(this._resizeTimer);
    this._resizeObserver?.disconnect();
  }

  getCardSize() { return 6; }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; min-width:0; max-width:100%; }
        ha-card { overflow:hidden; min-width:0; max-width:100%; }
        .head { padding:18px 20px 4px; display:flex; align-items:flex-start; gap:12px; }
        .titles { min-width:0; flex:1; }
        .title { color:var(--primary-text-color); font-size:22px; line-height:1.25; }
        .subtitle { margin-top:4px; color:var(--secondary-text-color); font-size:13px; }
        button { border:0; background:transparent; color:var(--secondary-text-color); cursor:pointer; font-size:21px; padding:2px 6px; }
        .legend { display:flex; flex-wrap:wrap; gap:7px 15px; padding:7px 20px 2px; color:var(--secondary-text-color); font-size:12px; }
        .key { display:inline-flex; align-items:center; white-space:nowrap; }
        .swatch { width:18px; height:3px; margin-right:6px; border-radius:2px; background:var(--c); }
        .wrap { position:relative; min-width:0; padding:2px 8px 12px; overflow:hidden; }
        svg { display:block; width:100%; max-width:100%; height:auto; overflow:hidden; }
        .tip { display:none; position:absolute; z-index:3; pointer-events:none; padding:8px 10px; border-radius:7px; background:var(--card-background-color,#222); color:var(--primary-text-color); box-shadow:0 2px 9px rgba(0,0,0,.35); font-size:12px; line-height:1.45; white-space:pre-line; }
        .status { min-height:310px; display:grid; place-items:center; color:var(--secondary-text-color); padding:20px; text-align:center; }
        @media (max-width:520px) {
          .head { padding:14px 12px 3px; gap:8px; }
          .title { font-size:18px; }
          .subtitle { font-size:12px; }
          .legend { gap:6px 10px; padding:6px 12px 2px; font-size:11px; }
          .swatch { width:14px; }
          .wrap { padding:2px 4px 10px; }
          .status { min-height:270px; }
        }
      </style>
      <ha-card>
        <div class="head"><div class="titles"><div class="title"></div><div class="subtitle">Selected day · 5-minute mean · kW</div></div><button title="Refresh history" aria-label="Refresh history">↻</button></div>
        <div class="legend">${POWER_SERIES.map(([, label, color]) => `<span class="key"><i class="swatch" style="--c:${color}"></i>${label}</span>`).join("")}</div>
        <div class="wrap"><div class="status">Loading selected-day power…</div><div class="tip"></div></div>
      </ha-card>`;
    this.shadowRoot.querySelector(".title").textContent = this.config.title || "Site & battery power — selected day";
    this.shadowRoot.querySelector("button").addEventListener("click", () => this._maybeLoad(true));
  }

  _collection() {
    const connection = this._hass?.connection;
    if (!connection) return null;
    const key = this.config.collection_key
      ? `_${this.config.collection_key}`
      : (this._hass.panelUrl ? `_energy_${this._hass.panelUrl}` : "_energy");
    return connection[key] || null;
  }

  _range() {
    const now = new Date();
    const fallbackStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const fallbackEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    const collection = this._collection();
    const start = collection?.start ? new Date(collection.start) : fallbackStart;
    const end = collection?.end ? new Date(collection.end) : fallbackEnd;
    return Number.isFinite(start.getTime()) && Number.isFinite(end.getTime()) && end > start
      ? { start, end }
      : { start: fallbackStart, end: fallbackEnd };
  }

  async _maybeLoad(force = false) {
    if (!this._hass || this._loading) return;
    const { start, end } = this._range();
    const key = `${start.toISOString()}|${end.toISOString()}`;
    if (!force && this._periodKey === key && Date.now() - (this._lastLoad || 0) < 60000) return;
    this._loading = true;
    this._error = null;
    try {
      const now = new Date();
      const queryEnd = now > start && now < end ? now : end;
      const ids = POWER_SERIES.map(([name]) => this.config.entities[name]).filter(Boolean);
      const stats = queryEnd > start ? await this._hass.callWS({
        type: "recorder/statistics_during_period",
        start_time: start.toISOString(),
        end_time: queryEnd.toISOString(),
        statistic_ids: ids,
        period: "5minute",
        units: { power: "kW" },
        types: ["mean"],
      }) : {};
      this._data = { start, end, stats: stats || {} };
      this._periodKey = key;
      this._lastLoad = Date.now();
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this._renderChart();
    }
  }

  _points(id) {
    return (this._data?.stats?.[id] || []).map((row) => ({
      t: new Date(row.start).getTime(),
      v: Number(row.mean),
    })).filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v)).sort((a, b) => a.t - b.t);
  }

  _nearest(points, time) {
    if (!points.length) return null;
    let best = points[0];
    for (const point of points) {
      if (Math.abs(point.t - time) < Math.abs(best.t - time)) best = point;
      if (point.t > time) break;
    }
    return best.v;
  }

  _renderChart() {
    const wrap = this.shadowRoot?.querySelector(".wrap");
    if (!wrap) return;
    if (this._error) {
      wrap.innerHTML = `<div class="status">Could not load selected-day power.<br>${this._esc(this._error)}</div><div class="tip"></div>`;
      return;
    }
    if (!this._data) return;
    wrap.querySelector(".status")?.remove();
    wrap.querySelector("svg")?.remove();

    const series = POWER_SERIES.map(([name, label, color]) => ({ name, label, color, points: this._points(this.config.entities[name]) }));
    const width = Math.round(wrap.getBoundingClientRect().width - 16);
    if (width < 180) return;
    const compact = width < 520;
    const height = compact ? 300 : 350;
    const left = compact ? 42 : 56, right = compact ? 8 : 18, top = 18, bottom = 42;
    const plotW = width - left - right, plotH = height - top - bottom;
    const lo = this._data.start.getTime(), hi = this._data.end.getTime();
    const x = (t) => left + ((t - lo) / (hi - lo)) * plotW;
    const observedMax = Math.max(0, ...series.flatMap((s) => s.points.map((p) => p.v)));
    const yMax = Math.max(1, Math.ceil(observedMax / 2) * 2);
    const y = (v) => top + ((yMax - Math.max(0, v)) / yMax) * plotH;
    const grid = [];
    const fontSize = compact ? 10 : 12;
    const yTickCount = compact ? 4 : 5;
    for (let i = 0; i <= yTickCount; i++) {
      const value = yMax * i / yTickCount, yy = y(value);
      grid.push(`<line x1="${left}" y1="${yy}" x2="${left + plotW}" y2="${yy}" stroke="var(--divider-color)" opacity=".7"/><text x="${left - 6}" y="${yy + 4}" text-anchor="end" fill="var(--secondary-text-color)" font-size="${fontSize}">${value.toFixed(value < 2 ? 1 : 0)}</text>`);
    }
    const tf = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
    const df = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
    const tickCount = compact ? 3 : 6;
    for (let i = 0; i <= tickCount; i++) {
      const tt = lo + (hi - lo) * i / tickCount, xx = x(tt), dt = new Date(tt);
      grid.push(`<line x1="${xx}" y1="${top}" x2="${xx}" y2="${top + plotH}" stroke="var(--divider-color)" opacity=".45"/><text x="${xx}" y="${height - 18}" text-anchor="middle" fill="var(--secondary-text-color)" font-size="${fontSize}">${i === 0 ? df.format(dt) : tf.format(dt)}</text>`);
    }
    const paths = series.map((s) => `<path d="${s.points.map((p, i) => `${i ? "L" : "M"} ${x(p.t)} ${y(p.v)}`).join(" ")}" fill="none" stroke="${s.color}" stroke-width="2.4"/>`).join("");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", width); svg.setAttribute("height", height);
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.innerHTML = `<g>${grid.join("")}</g><g>${paths}<line class="cross" x1="0" y1="${top}" x2="0" y2="${top + plotH}" stroke="var(--primary-text-color)" opacity=".55" style="display:none"/></g><text x="${left}" y="12" fill="var(--secondary-text-color)" font-size="12" font-weight="600">kW</text><rect class="hit" x="${left}" y="${top}" width="${plotW}" height="${plotH}" fill="transparent"/>`;
    wrap.insertBefore(svg, wrap.querySelector(".tip"));
    const tip = wrap.querySelector(".tip"), hit = svg.querySelector(".hit"), cross = svg.querySelector(".cross");
    hit.addEventListener("pointermove", (event) => {
      const rect = svg.getBoundingClientRect(), px = event.clientX - rect.left;
      const time = lo + Math.max(0, Math.min(1, (px - left) / plotW)) * (hi - lo);
      cross.style.display = ""; cross.setAttribute("x1", px); cross.setAttribute("x2", px);
      const values = series.map((s) => `${s.label}: ${this._nearest(s.points, time)?.toFixed(2) ?? "—"} kW`);
      tip.textContent = `${new Intl.DateTimeFormat(undefined, { month:"short", day:"numeric", hour:"numeric", minute:"2-digit" }).format(new Date(time))}\n${values.join("\n")}`;
      tip.style.display = "block";
      const localX = event.clientX - wrap.getBoundingClientRect().left;
      tip.style.left = `${Math.min(Math.max(8, localX + 12), wrap.clientWidth - 210)}px`;
      tip.style.top = `${Math.max(8, event.clientY - wrap.getBoundingClientRect().top - 85)}px`;
    });
    hit.addEventListener("pointerleave", () => { cross.style.display = "none"; tip.style.display = "none"; });
  }

  _esc(value) {
    return String(value).replace(/[&<>"']/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
  }
}

const conditionalExportSeries = (threshold) => [
  ["all", `Export while SOC < ${threshold}%`, "#DC2626"],
  ["peak", `SOC < ${threshold}% · configured peak window`, "#F59E0B"],
];

class ConditionalExportEnergyHistoryCard extends HTMLElement {
  setConfig(config) {
    if (!config?.entities?.grid_export || !config?.entities?.battery_soc) {
      throw new Error("entities.grid_export and entities.battery_soc are required");
    }
    this.config = {
      peak_start: "16:00",
      peak_end: "21:00",
      soc_threshold: 100,
      billing_cycle_name: "billing",
      billing_cycle_start_day: 1,
      ...config,
      entities: { ...config.entities },
    };
    this._peakStartMinutes = this._parseClock(this.config.peak_start, "peak_start");
    this._peakEndMinutes = this._parseClock(this.config.peak_end, "peak_end");
    this._socThreshold = Number(this.config.soc_threshold);
    if (!Number.isFinite(this._socThreshold)) throw new Error("soc_threshold must be numeric");
    this._billingCycleStartDay = Number(this.config.billing_cycle_start_day);
    if (!Number.isInteger(this._billingCycleStartDay) || this._billingCycleStartDay < 1 || this._billingCycleStartDay > 28) {
      throw new Error("billing_cycle_start_day must be an integer from 1 to 28");
    }
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._periodKey = null;
    const currentBillingPeriod = this._billingPeriod(new Date());
    this._selectedStart = currentBillingPeriod.start;
    this._selectedEnd = currentBillingPeriod.end;
    this._renderShell();
  }

  set hass(hass) {
    this._hass = hass;
    this._maybeLoad();
  }

  connectedCallback() {
    this._poll = setInterval(() => this._maybeLoad(), 1500);
    this._resizeObserver = new ResizeObserver(() => {
      clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => this._renderChart(), 80);
    });
    this._resizeObserver.observe(this);
  }

  disconnectedCallback() {
    clearInterval(this._poll);
    clearTimeout(this._resizeTimer);
    this._resizeObserver?.disconnect();
  }

  getCardSize() { return 6; }

  _parseClock(value, name) {
    const match = /^(\d{1,2}):(\d{2})$/.exec(String(value));
    const hours = match ? Number(match[1]) : NaN;
    const minutes = match ? Number(match[2]) : NaN;
    if (!Number.isInteger(hours) || hours < 0 || hours > 23 || !Number.isInteger(minutes) || minutes < 0 || minutes > 59) {
      throw new Error(`${name} must be HH:MM`);
    }
    return hours * 60 + minutes;
  }

  _clockLabel(totalMinutes) {
    const date = new Date(2000, 0, 1, Math.floor(totalMinutes / 60), totalMinutes % 60);
    return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
  }

  _parseInputDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
    if (!match) return null;
    const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    return date.getFullYear() === Number(match[1]) && date.getMonth() === Number(match[2]) - 1 && date.getDate() === Number(match[3])
      ? date
      : null;
  }

  _formatInputDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  _billingPeriod(reference) {
    const date = new Date(reference);
    const startMonthOffset = date.getDate() >= this._billingCycleStartDay ? 0 : -1;
    const start = new Date(date.getFullYear(), date.getMonth() + startMonthOffset, this._billingCycleStartDay);
    const end = new Date(start.getFullYear(), start.getMonth() + 1, this._billingCycleStartDay);
    return { start, end };
  }

  _inclusiveEnd(end) {
    return new Date(end.getFullYear(), end.getMonth(), end.getDate() - 1);
  }

  _rangeLabel(start, end) {
    const formatter = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" });
    return `${formatter.format(start)}–${formatter.format(this._inclusiveEnd(end))}`;
  }

  _syncDateInputs() {
    const startInput = this.shadowRoot?.querySelector(".range-start");
    const endInput = this.shadowRoot?.querySelector(".range-end");
    if (!startInput || !endInput) return;
    startInput.value = this._formatInputDate(this._selectedStart);
    endInput.value = this._formatInputDate(this._inclusiveEnd(this._selectedEnd));
    endInput.setCustomValidity("");
    this._updateRangeSummary();
  }

  _updateRangeSummary() {
    const subtitle = this.shadowRoot?.querySelector(".subtitle");
    if (!subtitle || !this._selectedStart || !this._selectedEnd) return;
    const peakLabel = `${this._clockLabel(this._peakStartMinutes)}–${this._clockLabel(this._peakEndMinutes)}`;
    subtitle.textContent = `${this._rangeLabel(this._selectedStart, this._selectedEnd)} · 5-minute means · cumulative kWh · Daily peak ${peakLabel}`;
  }

  _applyDateInputs() {
    const startInput = this.shadowRoot.querySelector(".range-start");
    const endInput = this.shadowRoot.querySelector(".range-end");
    const start = this._parseInputDate(startInput.value);
    const inclusiveEnd = this._parseInputDate(endInput.value);
    if (!start || !inclusiveEnd) return;
    if (inclusiveEnd < start) {
      endInput.setCustomValidity("Through date must be on or after the From date");
      endInput.reportValidity();
      return;
    }
    endInput.setCustomValidity("");
    this._selectedStart = start;
    this._selectedEnd = new Date(inclusiveEnd.getFullYear(), inclusiveEnd.getMonth(), inclusiveEnd.getDate() + 1);
    this._updateRangeSummary();
    this._maybeLoad(true);
  }

  _selectCurrentBillingPeriod() {
    const range = this._billingPeriod(new Date());
    this._selectedStart = range.start;
    this._selectedEnd = range.end;
    this._syncDateInputs();
    this._maybeLoad(true);
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; min-width:0; max-width:100%; }
        ha-card { overflow:hidden; min-width:0; max-width:100%; }
        .head { padding:18px 20px 4px; display:flex; align-items:flex-start; gap:12px; }
        .titles { min-width:0; flex:1; }
        .title { color:var(--primary-text-color); font-size:22px; line-height:1.25; }
        .subtitle { margin-top:4px; color:var(--secondary-text-color); font-size:13px; }
        button { font:inherit; cursor:pointer; }
        .refresh { border:0; background:transparent; color:var(--secondary-text-color); font-size:21px; padding:2px 6px; }
        .date-range { display:flex; flex-wrap:wrap; align-items:end; gap:8px 12px; padding:8px 20px 5px; }
        .date-range label { display:grid; gap:3px; color:var(--secondary-text-color); font-size:11px; }
        .date-range input { min-height:34px; box-sizing:border-box; border:1px solid var(--divider-color); border-radius:7px; padding:5px 8px; background:var(--card-background-color); color:var(--primary-text-color); color-scheme:dark; font:inherit; font-size:13px; }
        .range-current { min-height:34px; border:1px solid var(--primary-color); border-radius:7px; padding:5px 10px; background:transparent; color:var(--primary-color); font-size:12px; }
        .legend { display:flex; flex-wrap:wrap; gap:7px 15px; padding:7px 20px 2px; color:var(--secondary-text-color); font-size:12px; }
        .key { display:inline-flex; align-items:center; white-space:nowrap; }
        .swatch { width:18px; height:3px; margin-right:6px; border-radius:2px; background:var(--c); }
        .totals { display:flex; flex-wrap:wrap; gap:8px 18px; padding:6px 20px 3px; color:var(--primary-text-color); font-size:14px; }
        .totals strong { font-variant-numeric:tabular-nums; }
        .wrap { position:relative; min-width:0; padding:2px 8px 12px; overflow:hidden; }
        svg { display:block; width:100%; max-width:100%; height:auto; overflow:hidden; }
        .tip { display:none; position:absolute; z-index:3; pointer-events:none; padding:8px 10px; border-radius:7px; background:var(--card-background-color,#222); color:var(--primary-text-color); box-shadow:0 2px 9px rgba(0,0,0,.35); font-size:12px; line-height:1.45; white-space:pre-line; }
        .status { min-height:290px; display:grid; place-items:center; color:var(--secondary-text-color); padding:20px; text-align:center; }
        @media (max-width:520px) {
          .head { padding:14px 12px 3px; gap:8px; }
          .title { font-size:18px; }
          .subtitle { font-size:12px; }
          .date-range, .legend, .totals { gap:6px 10px; padding-left:12px; padding-right:12px; font-size:11px; }
          .date-range label { flex:1 1 132px; }
          .date-range input { width:100%; }
          .range-current { flex:1 1 100%; }
          .swatch { width:14px; }
          .wrap { padding:2px 4px 10px; }
          .status { min-height:260px; }
        }
      </style>
      <ha-card>
        <div class="head"><div class="titles"><div class="title"></div><div class="subtitle"></div></div><button class="refresh" title="Refresh history" aria-label="Refresh history">↻</button></div>
        <div class="date-range" aria-label="Export energy date range">
          <label>From<input class="range-start" type="date"></label>
          <label>Through<input class="range-end" type="date"></label>
          <button class="range-current" type="button"></button>
        </div>
        <div class="legend">${conditionalExportSeries(this._socThreshold).map(([, label, color]) => `<span class="key"><i class="swatch" style="--c:${color}"></i>${label}</span>`).join("")}</div>
        <div class="totals"><span>Selected range <strong class="total-all">—</strong></span><span>Daily peak windows <strong class="total-peak">—</strong></span></div>
        <div class="wrap"><div class="status">Loading export energy for this range…</div><div class="tip"></div></div>
      </ha-card>`;
    this.shadowRoot.querySelector(".title").textContent = this.config.title || "Exported energy with battery headroom — billing period";
    this.shadowRoot.querySelector(".range-current").textContent = `Current ${this.config.billing_cycle_name} period`;
    this.shadowRoot.querySelector(".refresh").addEventListener("click", () => this._maybeLoad(true));
    this.shadowRoot.querySelector(".range-start").addEventListener("change", () => this._applyDateInputs());
    this.shadowRoot.querySelector(".range-end").addEventListener("change", () => this._applyDateInputs());
    this.shadowRoot.querySelector(".range-current").addEventListener("click", () => this._selectCurrentBillingPeriod());
    this._syncDateInputs();
  }

  _range() {
    return { start: new Date(this._selectedStart), end: new Date(this._selectedEnd) };
  }

  async _maybeLoad(force = false) {
    if (!this._hass || this._loading) return;
    const { start, end } = this._range();
    const key = `${start.toISOString()}|${end.toISOString()}`;
    if (!force && this._periodKey === key && Date.now() - (this._lastLoad || 0) < 60000) return;
    this._loading = true;
    this._error = null;
    try {
      const now = new Date();
      const queryEnd = now > start && now < end ? now : end;
      const ids = [this.config.entities.grid_export, this.config.entities.battery_soc];
      const stats = queryEnd > start ? await this._hass.callWS({
        type: "recorder/statistics_during_period",
        start_time: start.toISOString(),
        end_time: queryEnd.toISOString(),
        statistic_ids: ids,
        period: "5minute",
        units: { power: "kW" },
        types: ["mean"],
      }) : {};
      this._data = { start, end, queryEnd, stats: stats || {} };
      this._periodKey = key;
      this._lastLoad = Date.now();
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this._renderChart();
    }
  }

  _points(id) {
    return (this._data?.stats?.[id] || []).map((row) => ({
      t: new Date(row.start).getTime(),
      v: Number(row.mean),
    })).filter((point) => Number.isFinite(point.t) && Number.isFinite(point.v)).sort((a, b) => a.t - b.t);
  }

  _peakBounds(time) {
    const day = new Date(time);
    const start = new Date(day.getFullYear(), day.getMonth(), day.getDate(), Math.floor(this._peakStartMinutes / 60), this._peakStartMinutes % 60).getTime();
    let end = new Date(day.getFullYear(), day.getMonth(), day.getDate(), Math.floor(this._peakEndMinutes / 60), this._peakEndMinutes % 60).getTime();
    if (end <= start) end = new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1, Math.floor(this._peakEndMinutes / 60), this._peakEndMinutes % 60).getTime();
    return { start, end };
  }

  _computeCumulative(exportPoints, socPoints, start, end, queryEnd) {
    const bucketMs = 5 * 60 * 1000;
    const lo = start.getTime(), hi = Math.min(end.getTime(), queryEnd.getTime());
    const all = [{ t: lo, v: 0 }], peak = [{ t: lo, v: 0 }];
    const socByStart = new Map(socPoints.map((point) => [point.t, point.v]));
    let allTotal = 0, peakTotal = 0, skippedBuckets = 0;
    for (const point of exportPoints) {
      if (point.t < lo || point.t >= hi) continue;
      const bucketEnd = Math.min(point.t + bucketMs, hi);
      if (bucketEnd <= point.t) continue;
      const soc = socByStart.has(point.t) ? socByStart.get(point.t) : null;
      if (soc == null) skippedBuckets++;
      if (soc != null && soc < this._socThreshold) {
        const powerKw = Math.max(0, point.v);
        allTotal += powerKw * (bucketEnd - point.t) / 3600000;
        const bounds = this._peakBounds(point.t);
        const overlapMs = Math.max(0, Math.min(bucketEnd, bounds.end) - Math.max(point.t, bounds.start));
        peakTotal += powerKw * overlapMs / 3600000;
      }
      all.push({ t: bucketEnd, v: allTotal });
      peak.push({ t: bucketEnd, v: peakTotal });
    }
    return { all, peak, allTotal, peakTotal, skippedBuckets };
  }

  _nearest(points, time) {
    if (!points.length) return null;
    let best = points[0];
    for (const point of points) {
      if (Math.abs(point.t - time) < Math.abs(best.t - time)) best = point;
      if (point.t > time) break;
    }
    return best.v;
  }

  _linePath(points, x, y) {
    return points.map((point, index) => `${index ? "L" : "M"} ${x(point.t)} ${y(point.v)}`).join(" ");
  }

  _renderChart() {
    const wrap = this.shadowRoot?.querySelector(".wrap");
    if (!wrap) return;
    if (this._error) {
      wrap.innerHTML = `<div class="status">Could not load export energy for this range.<br>${this._esc(this._error)}</div><div class="tip"></div>`;
      return;
    }
    if (!this._data) return;
    wrap.querySelector(".status")?.remove();
    wrap.querySelector("svg")?.remove();

    const exportPoints = this._points(this.config.entities.grid_export);
    const socPoints = this._points(this.config.entities.battery_soc);
    const cumulative = this._computeCumulative(exportPoints, socPoints, this._data.start, this._data.end, this._data.queryEnd);
    const series = conditionalExportSeries(this._socThreshold).map(([name, label, color]) => ({ name, label, color, points: cumulative[name] }));
    this.shadowRoot.querySelector(".total-all").textContent = `${cumulative.allTotal.toFixed(2)} kWh`;
    this.shadowRoot.querySelector(".total-peak").textContent = `${cumulative.peakTotal.toFixed(2)} kWh`;

    const width = Math.round(wrap.getBoundingClientRect().width - 16);
    if (width < 180) return;
    const compact = width < 520;
    const height = compact ? 290 : 340;
    const left = compact ? 46 : 58, right = compact ? 8 : 18, top = 18, bottom = 42;
    const plotW = width - left - right, plotH = height - top - bottom;
    const lo = this._data.start.getTime(), hi = this._data.end.getTime();
    const x = (time) => left + ((time - lo) / (hi - lo)) * plotW;
    const observedMax = Math.max(0, cumulative.allTotal, cumulative.peakTotal);
    const yMax = Math.max(0.5, Math.ceil(observedMax * 2) / 2);
    const y = (value) => top + ((yMax - Math.max(0, value)) / yMax) * plotH;
    const grid = [];
    const fontSize = compact ? 10 : 12;
    const yTickCount = compact ? 4 : 5;
    for (let index = 0; index <= yTickCount; index++) {
      const value = yMax * index / yTickCount, yy = y(value);
      grid.push(`<line x1="${left}" y1="${yy}" x2="${left + plotW}" y2="${yy}" stroke="var(--divider-color)" opacity=".7"/><text x="${left - 6}" y="${yy + 4}" text-anchor="end" fill="var(--secondary-text-color)" font-size="${fontSize}">${value.toFixed(2)}</text>`);
    }
    const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
    const dateFormat = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
    const multiDay = hi - lo > 2 * 86400000;
    const tickCount = compact ? 3 : 6;
    for (let index = 0; index <= tickCount; index++) {
      const time = lo + (hi - lo) * index / tickCount, xx = x(time), date = new Date(time);
      const tickLabel = multiDay || index === 0 ? dateFormat.format(date) : timeFormat.format(date);
      grid.push(`<line x1="${xx}" y1="${top}" x2="${xx}" y2="${top + plotH}" stroke="var(--divider-color)" opacity=".45"/><text x="${xx}" y="${height - 18}" text-anchor="middle" fill="var(--secondary-text-color)" font-size="${fontSize}">${tickLabel}</text>`);
    }
    const paths = series.map((item) => `<path d="${this._linePath(item.points, x, y)}" fill="none" stroke="${item.color}" stroke-width="2.6"/>`).join("");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", width); svg.setAttribute("height", height);
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.innerHTML = `<g>${grid.join("")}</g><g>${paths}<line class="cross" x1="0" y1="${top}" x2="0" y2="${top + plotH}" stroke="var(--primary-text-color)" opacity=".55" style="display:none"/></g><text x="${left}" y="12" fill="var(--secondary-text-color)" font-size="12" font-weight="600">kWh</text><rect class="hit" x="${left}" y="${top}" width="${plotW}" height="${plotH}" fill="transparent"/>`;
    wrap.insertBefore(svg, wrap.querySelector(".tip"));
    const tip = wrap.querySelector(".tip"), hit = svg.querySelector(".hit"), cross = svg.querySelector(".cross");
    hit.addEventListener("pointermove", (event) => {
      const rect = svg.getBoundingClientRect(), px = event.clientX - rect.left;
      const time = lo + Math.max(0, Math.min(1, (px - left) / plotW)) * (hi - lo);
      cross.style.display = ""; cross.setAttribute("x1", px); cross.setAttribute("x2", px);
      const values = series.map((item) => `${item.label}: ${this._nearest(item.points, time)?.toFixed(2) ?? "—"} kWh`);
      tip.textContent = `${new Intl.DateTimeFormat(undefined, { month:"short", day:"numeric", hour:"numeric", minute:"2-digit" }).format(new Date(time))}\n${values.join("\n")}`;
      tip.style.display = "block";
      const localX = event.clientX - wrap.getBoundingClientRect().left;
      tip.style.left = `${Math.min(Math.max(8, localX + 12), wrap.clientWidth - 250)}px`;
      tip.style.top = `${Math.max(8, event.clientY - wrap.getBoundingClientRect().top - 85)}px`;
    });
    hit.addEventListener("pointerleave", () => { cross.style.display = "none"; tip.style.display = "none"; });
  }

  _esc(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[character]));
  }
}

if (!customElements.get("hvac-energy-history-card")) customElements.define("hvac-energy-history-card", HvacEnergyHistoryCard);
if (!customElements.get("site-battery-power-history-card")) customElements.define("site-battery-power-history-card", SiteBatteryPowerHistoryCard);
if (!customElements.get("conditional-export-energy-history-card")) customElements.define("conditional-export-energy-history-card", ConditionalExportEnergyHistoryCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "hvac-energy-history-card",
  name: "HVAC & Energy History",
  description: "Thermostat history with AC shading, command markers, and battery SOC",
});
window.customCards.push({
  type: "site-battery-power-history-card",
  name: "Site & Battery Power History",
  description: "Selected-day solar, consumption, grid, and battery power in kW",
});
window.customCards.push({
  type: "conditional-export-energy-history-card",
  name: "Conditional Export Energy History",
  description: "Cumulative grid export over an independent date range while battery SOC is below a threshold, including daily peak-window totals",
});
