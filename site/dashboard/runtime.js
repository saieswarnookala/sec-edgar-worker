// Sentinel website runtime: a small stand-in for the Claude dashboard runtime (dash.*), so the dashboard
// page runs unchanged. Datasets come from /api/data/* (live) and /data/* (files built by GitHub Actions).
(function () {
  const DEFAULTS = { symbol: 'LULU', exchange: 'US', base: 'yoy', range: '1Y' };
  const enc = encodeURIComponent;
  const getJSON = async (u) => { const r = await fetch(u, { credentials: 'same-origin' }); if (r.status === 401) { location.href = '/login?next=' + enc(location.pathname + location.search + location.hash); throw new Error('Signed out'); } const t = await r.text(); let j; try { j = JSON.parse(t); } catch { j = t; } if (!r.ok) throw new Error((j && j.error) || ('HTTP ' + r.status)); return j; };
  const getText = async (u) => { const r = await fetch(u, { credentials: 'same-origin' }); if (r.status === 401) { location.href = '/login'; throw new Error('Signed out'); } const t = await r.text(); if (!r.ok) { let e = t; try { e = JSON.parse(t).error || t; } catch {} throw new Error(e); } return t; };
  const csvRows = (text) => {
    const lines = text.replace(/\r/g, '').trim().split('\n'); if (!lines.length) return [];
    const split = (l) => { const out = []; let cur = '', q = false; for (let i = 0; i < l.length; i++) { const c = l[i]; if (q) { if (c === '"' && l[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c; } else if (c === '"') q = true; else if (c === ',') { out.push(cur); cur = ''; } else cur += c; } out.push(cur); return out; };
    const h = split(lines[0]);
    return lines.slice(1).map((l) => { const c = split(l); const o = {}; h.forEach((k, i) => { const v = c[i] ?? ''; o[k] = v === '' ? null : (/^-?\d+(\.\d+)?(e-?\d+)?$/i.test(v) ? Number(v) : v); }); return o; });
  };
  let dipCache = null;
  const dipText = async (sym) => {
    dipCache = dipCache || getText('/data/dip_daily.csv').then(csvRows);
    const rows = (await dipCache).filter((r) => r.symbol === sym).sort((a, b) => (a.date < b.date ? 1 : -1));
    return ['datetime;open;high;low;close;volume', ...rows.map((r) => [r.date, r.open, r.open, r.close, r.close, 0].join(';'))].join('\n');
  };
  const live = (feed, text) => ({ key: (p) => String(p.symbol || ''), get: (p) => (text ? getText : getJSON)('/api/data/' + feed + '?symbol=' + enc(p.symbol || '')) });
  const file = (name, kind) => ({ key: () => 'static', get: () => (kind === 'csv' ? getText('/data/' + name).then(csvRows) : getJSON('/data/' + name)) });
  const SOURCES = {
    company: live('company'), prices: live('prices', true), profile: live('profile'), statements: live('statements'),
    industry: file('industry_benchmarks_jan2026.csv', 'csv'), screen: file('screen.json'), universe: file('universe.json'),
    strategies: file('strategies_oct10.json'), etf_monthly: file('etf_monthly.csv', 'csv'), etf_monthly_long: file('etf_monthly_long.csv', 'csv'),
    dip_spy: { key: () => 'static', get: () => dipText('SPY') }, dip_qqq: { key: () => 'static', get: () => dipText('QQQ') },
  };

  const loaders = {}, calcs = {}, cbs = [], state = {};
  let P = { ...DEFAULTS };
  for (const [k, v] of new URLSearchParams(location.search)) P[k] = v;
  let started = false, scheduled = false;

  const toRows = (x) => (Array.isArray(x) ? x : x && Array.isArray(x.rows) ? x.rows : typeof x === 'string' ? csvRows(x) : []);
  async function load(id) {
    const src = SOURCES[id]; if (!src) return;
    const key = src.key(P);
    if (state[id] && state[id].key === key && state[id].status !== 'error') return;
    const token = {};
    state[id] = { status: 'loading', data: [], key, token };
    schedule();
    try {
      const answer = await src.get(P);
      const out = loaders[id] ? await loaders[id].fn({ answer, args: { ...P } }) : answer;
      if (state[id].token !== token) return;
      state[id] = { status: 'ok', data: toRows(out), meta: out && out.meta, key, token };
    } catch (e) {
      if (state[id].token !== token) return;
      state[id] = { status: 'error', data: [], error: String((e && e.message) || e), key, token };
    }
    schedule();
  }
  const memo = {};
  function order() {
    const seen = new Set(), out = [];
    const visit = (id) => { if (seen.has(id) || !calcs[id]) return; seen.add(id); for (const i of calcs[id].inputs) visit(i); out.push(id); };
    Object.keys(calcs).forEach(visit); return out;
  }
  function computeCalcs() {
    for (const id of order()) {
      const c = calcs[id], ins = c.inputs.map((i) => state[i]);
      if (ins.some((s) => !s || s.status === 'loading' || s.status === 'missing')) { state[id] = { status: 'loading', data: [] }; continue; }
      if (ins.some((s) => s.status !== 'ok')) { state[id] = { status: 'error', data: [], error: 'Needs data that failed to load' }; continue; }
      const datas = ins.map((s) => s.data);
      const m = memo[id];
      if (m && m.inputs.length === datas.length && m.inputs.every((d, k) => d === datas[k])) { state[id] = m.state; continue; }
      let st;
      try { st = { status: 'ok', data: c.fn(...datas) || [] }; } catch (e) { st = { status: 'error', data: [], error: String(e.message || e) }; }
      memo[id] = { inputs: datas, state: st }; state[id] = st;
    }
  }
  function schedule() {
    if (!started || scheduled) return; scheduled = true;
    requestAnimationFrame(() => { scheduled = false; computeCalcs(); for (const f of cbs) { try { f(); } catch (e) { console.error(e); } } });
  }
  const writeUrl = (hash) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(P)) if (v != null && v !== '' && DEFAULTS[k] !== v) q.set(k, String(v));
    const qs = q.toString();
    history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + (hash != null ? (hash ? '#' + hash : '') : location.hash));
  };

  window.dash = {
    colors: ['#c2410c', '#2563eb', '#0f766e', '#7c3aed', '#b45309', '#0e7490', '#be123c', '#4d7c0f'],
    loader: (id, def) => { loaders[id] = def; },
    calc: (id, def) => { calcs[id] = def; },
    onData: (f) => { cbs.push(f); schedule(); },
    data: (id) => state[id] || { status: 'missing', data: [] },
    params: () => ({ ...P }),
    setParams: (obj) => {
      for (const [k, v] of Object.entries(obj || {})) { if (v == null) delete P[k]; else P[k] = v; }
      for (const k of Object.keys(DEFAULTS)) if (P[k] == null) P[k] = DEFAULTS[k];
      writeUrl(null);
      Object.keys(SOURCES).forEach(load);
      schedule();
    },
    setLink: (name) => writeUrl(name === 'overview' ? '' : name),
    fields: () => [],
    __start: () => { started = true; Object.keys(SOURCES).forEach(load); schedule(); bar(); },
  };

  async function bar() {
    const el = document.getElementById('sw-bar'); if (!el) return;
    try {
      const me = await getJSON('/api/me');
      el.innerHTML = '';
      const brand = document.createElement('strong'); brand.textContent = 'Sentinel'; el.appendChild(brand);
      const sp = document.createElement('span'); sp.className = 'sw-sp'; el.appendChild(sp);
      const who = document.createElement('span'); who.className = 'sw-who'; who.textContent = me.name; el.appendChild(who);
      if (me.role === 'admin') { const a = document.createElement('a'); a.href = '/admin'; a.textContent = 'Users'; el.appendChild(a); }
      const b = document.createElement('button'); b.type = 'button'; b.textContent = 'Log out';
      b.addEventListener('click', async () => { await fetch('/api/logout', { method: 'POST', headers: { 'X-Sentinel': '1' } }); location.href = '/login'; });
      el.appendChild(b);
    } catch {}
  }
})();
