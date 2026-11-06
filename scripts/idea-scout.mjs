// Idea Scout: daily research for things to build or invest in. Research only, not financial advice.
// 1) Collects free demand signals (Hacker News, new GitHub repos, startup-funding news, Product Hunt, Reddit, own stock screener).
// 2) If ANTHROPIC_API_KEY is set: Claude researches the signals on the web and writes ranked ideas with evidence.
//    Without a key: a scored signal digest.
// 3) Writes data/ideas/latest.md + dated JSON, and sends a free push via ntfy (NTFY_TOPIC) and/or Telegram.
import { writeFileSync, readFileSync, existsSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const UA = { 'User-Agent': 'idea-scout/1.0 (github.com/saieswarnookala/sec-edgar-worker)' };
const PAIN = /(i would pay|i'd pay|would pay for|is there (a|any) (tool|app|service)|looking for (a|an) (tool|app|service)|wish (there was|someone)|nobody has built|hate (having|doing)|manual(ly)? |spreadsheet|too expensive|alternative to)/i;
const DAY = 86400e3;

export function parseRss(xml) {
  return [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].map((m) => {
    const g = (t) => (new RegExp(`<${t}[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?<\\/${t}>`).exec(m[1])?.[1] || '').replace(/<[^>]+>/g, '').trim();
    return { title: g('title'), url: g('link'), date: g('pubDate') };
  }).filter((x) => x.title);
}
export function scoreSignal(s) { let k = Math.log10(1 + (s.points || 0)) * 2 + Math.log10(1 + (s.comments || 0)); if (PAIN.test(`${s.title} ${s.text || ''}`)) k += 3; return +k.toFixed(2); }
export function dedupe(items) { const seen = new Set(); return items.filter((x) => { const k = (x.url || x.title).toLowerCase(); return seen.has(k) ? false : seen.add(k); }); }

async function get(url, opt = {}, json = true) {
  try { const r = await fetch(url, { ...opt, headers: { ...UA, ...(opt.headers || {}) } }); if (!r.ok) return { err: `${r.status}` }; return { data: json ? await r.json() : await r.text() }; } catch (e) { return { err: e.message }; }
}
export async function collect(now = Date.now(), env = process.env) {
  const since = Math.floor((now - 7 * DAY) / 1000), out = { hn: [], github: [], news: [], producthunt: [], reddit: [], screener: [] }, errors = {};
  for (const [q, tags] of [['', 'ask_hn'], ['would pay', 'story'], ['is there a tool', 'story'], ['', 'show_hn']]) {
    const r = await get(`https://hn.algolia.com/api/v1/search?query=${encodeURIComponent(q)}&tags=${tags}&numericFilters=created_at_i>${since},points>${tags === 'show_hn' ? 80 : 15}&hitsPerPage=30`);
    if (r.err) { errors.hn = r.err; continue; }
    for (const h of r.data.hits || []) out.hn.push({ src: tags === 'show_hn' ? 'Show HN' : 'Ask HN', title: h.title, text: (h.story_text || '').replace(/<[^>]+>/g, ' ').slice(0, 400), url: `https://news.ycombinator.com/item?id=${h.objectID}`, points: h.points, comments: h.num_comments });
  }
  const gh = await get(`https://api.github.com/search/repositories?q=created:>${new Date(now - 14 * DAY).toISOString().slice(0, 10)}&sort=stars&order=desc&per_page=25`, { headers: env.GITHUB_TOKEN ? { Authorization: `Bearer ${env.GITHUB_TOKEN}` } : {} });
  if (gh.err) errors.github = gh.err; else out.github = (gh.data.items || []).map((r) => ({ src: 'GitHub', title: `${r.full_name}: ${r.description || ''}`.slice(0, 200), url: r.html_url, points: r.stargazers_count, lang: r.language }));
  for (const q of ['startup raises seed round', 'raises Series A AI', 'small business software demand']) {
    const r = await get(`https://news.google.com/rss/search?q=${encodeURIComponent(q + ' when:7d')}&hl=en-US&gl=US&ceid=US:en`, {}, false);
    if (r.err) errors.news = r.err; else out.news.push(...parseRss(r.data).slice(0, 12).map((x) => ({ src: 'News', ...x })));
  }
  const ph = await get('https://www.producthunt.com/feed', {}, false); if (ph.err) errors.producthunt = ph.err; else out.producthunt = parseRss(ph.data.replace(/<entry>/g, '<item>').replace(/<\/entry>/g, '</item>')).slice(0, 20).map((x) => ({ src: 'Product Hunt', ...x }));
  for (const sub of ['SomebodyMakeThis', 'SaaS', 'Entrepreneur']) {
    const r = await get(`https://www.reddit.com/r/${sub}/top.json?t=week&limit=15`);
    if (r.err) { errors.reddit = r.err; continue; }
    for (const c of r.data.data?.children || []) out.reddit.push({ src: `r/${sub}`, title: c.data.title, text: (c.data.selftext || '').slice(0, 400), url: `https://reddit.com${c.data.permalink}`, points: c.data.score, comments: c.data.num_comments });
  }
  if (existsSync('data/screen.json')) { try { const s = JSON.parse(readFileSync('data/screen.json', 'utf8')); const rows = (s.rows || s.results || []).slice(0, 15); out.screener = rows.map((r) => ({ src: 'Screener', title: `${r.symbol || r.ticker} ${r.name || ''}`.trim(), detail: r })); } catch (e) { errors.screener = e.message; } }
  for (const k of ['hn', 'reddit', 'github']) out[k] = dedupe(out[k]).map((x) => ({ ...x, score: scoreSignal(x) })).sort((a, b) => b.score - a.score);
  return { signals: out, errors };
}

export const PROFILE = `Reader: a senior platform engineer (Kubernetes AKS/EKS, AWS Lambda/SNS, CI/CD, healthcare automation), CKA certified, based in Dallas TX, working a full-time contract.
Builds side projects with AI coding tools; open to SaaS, developer tools, MCP connectors for AI assistants, automation services, and content.
Investing style: evidence-based, mostly index funds and a tested ETF momentum strategy; skeptical of day trading.`;
export function buildPrompt(signals, recent) {
  const brief = (arr, n) => arr.slice(0, n).map((x) => `- [${x.src}] ${x.title}${x.points ? ` (${x.points} pts)` : ''} ${x.url || ''}${x.text ? `\n  ${x.text.slice(0, 200)}` : ''}`).join('\n');
  return `You are a research analyst finding realistic ways for one person to make money. ${PROFILE}

Fresh signals from the last 7 days:
HACKER NEWS:\n${brief(signals.hn, 25)}
REDDIT:\n${brief(signals.reddit, 15)}
NEW FAST-GROWING GITHUB PROJECTS:\n${brief(signals.github, 15)}
PRODUCT HUNT:\n${brief(signals.producthunt, 12)}
FUNDING NEWS:\n${brief(signals.news, 15)}
STOCK SCREENER (profitable, growing companies):\n${brief(signals.screener, 10)}

Ideas already suggested recently (do not repeat): ${recent.join('; ') || 'none'}

Use web search to verify demand and competition for the most promising leads (at least 4 searches). Then return ONLY a JSON object, no markdown fences:
{"summary": "2 sentences on this week's themes",
 "ideas": [{"title": "...", "category": "build|service|content|invest", "what": "1-2 sentences", "why_now": "evidence-based reason", "evidence": ["url", "..."], "competition": "who already does it", "first_step": "a concrete first step this weekend", "effort": "low|medium|high", "money_model": "how it makes money", "risk": "main risk", "fit": 1-10, "confidence": 1-10}]}
Give 6-8 ideas, at least one per category, ranked best first. Be honest: say when an idea is crowded or weak. For "invest", give research directions, never buy/sell instructions.`;
}
export function parseIdeas(text) { const s = text.indexOf('{'), e = text.lastIndexOf('}'); if (s < 0 || e < s) throw new Error('no JSON in model output'); return JSON.parse(text.slice(s, e + 1)); }
async function research(signals, recent, env) {
  const body = { model: env.ANTHROPIC_MODEL || 'claude-sonnet-5-5', max_tokens: 8000, tools: [{ type: 'web_search_20250305', name: 'web_search', max_uses: 8 }], messages: [{ role: 'user', content: buildPrompt(signals, recent) }] };
  const r = await fetch('https://api.anthropic.com/v1/messages', { method: 'POST', headers: { 'content-type': 'application/json', 'x-api-key': env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' }, body: JSON.stringify(body) });
  const j = await r.json(); if (!r.ok) throw new Error(`anthropic ${r.status}: ${JSON.stringify(j).slice(0, 300)}`);
  const text = (j.content || []).filter((b) => b.type === 'text').map((b) => b.text).join('\n');
  return { ...parseIdeas(text), usage: j.usage };
}
export function digestIdeas(signals) { // no-LLM fallback: top pain-point signals
  const pool = [...signals.hn, ...signals.reddit].filter((x) => PAIN.test(`${x.title} ${x.text || ''}`)).slice(0, 6);
  const gh = signals.github.slice(0, 3);
  return { summary: 'Signal digest (no AI analysis: add an ANTHROPIC_API_KEY secret for researched ideas).',
    ideas: [...pool.map((x) => ({ title: x.title, category: 'build', what: `Demand signal from ${x.src} (${x.points || 0} points, ${x.comments || 0} comments)`, evidence: [x.url], fit: null, confidence: null })),
      ...gh.map((x) => ({ title: x.title, category: 'build', what: 'Fast-growing new GitHub project; look for a hosted/paid version or integrations', evidence: [x.url] }))] };
}
export function toMarkdown(date, res, errors) {
  const L = [`# Idea Scout: ${date}`, '', res.summary || '', ''];
  (res.ideas || []).forEach((x, i) => {
    L.push(`## ${i + 1}. ${x.title}`, '', `**Category:** ${x.category || '-'}${x.effort ? `  |  **Effort:** ${x.effort}` : ''}${x.fit ? `  |  **Fit:** ${x.fit}/10` : ''}${x.confidence ? `  |  **Confidence:** ${x.confidence}/10` : ''}`, '');
    for (const [k, lab] of [['what', 'What'], ['why_now', 'Why now'], ['competition', 'Competition'], ['money_model', 'Money model'], ['first_step', 'First step'], ['risk', 'Risk']]) if (x[k]) L.push(`- **${lab}:** ${x[k]}`);
    if (x.evidence?.length) L.push(`- **Evidence:** ${x.evidence.slice(0, 4).map((u) => `<${u}>`).join(' ')}`);
    L.push('');
  });
  const errs = Object.entries(errors || {}); if (errs.length) L.push('', `<sub>Sources unavailable this run: ${errs.map(([k, v]) => `${k} (${v})`).join(', ')}</sub>`);
  L.push('', '<sub>Research only, not financial advice.</sub>'); return L.join('\n');
}
export async function notify(env, title, msg, click) {
  const sent = [];
  if (env.NTFY_TOPIC) { const r = await fetch(`https://ntfy.sh/${env.NTFY_TOPIC}`, { method: 'POST', body: msg, headers: { Title: title, Tags: 'bulb', Click: click, Priority: '3' } }).catch((e) => ({ ok: false, status: e.message })); sent.push(`ntfy ${r.ok ? 'ok' : r.status}`); }
  if (env.TELEGRAM_BOT_TOKEN && env.TELEGRAM_CHAT_ID) { const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: `${title}\n\n${msg}\n\n${click}` }) }).catch((e) => ({ ok: false, status: e.message })); sent.push(`telegram ${r.ok ? 'ok' : r.status}`); }
  return sent;
}
async function main(env = process.env) {
  const date = new Date().toISOString().slice(0, 10), dir = 'data/ideas'; mkdirSync(dir, { recursive: true });
  const histF = `${dir}/history.json`, hist = existsSync(histF) ? JSON.parse(readFileSync(histF, 'utf8')) : [];
  const { signals, errors } = await collect(Date.now(), env);
  console.log('signals', Object.fromEntries(Object.entries(signals).map(([k, v]) => [k, v.length])), 'errors', errors);
  let res, mode = 'digest';
  if (env.ANTHROPIC_API_KEY) { try { res = await research(signals, hist.slice(-40).map((h) => h.title), env); mode = 'ai'; } catch (e) { console.log('AI research failed:', e.message); errors.ai = e.message.slice(0, 120); } }
  if (!res) res = digestIdeas(signals);
  const md = toMarkdown(date, res, errors);
  writeFileSync(`${dir}/latest.md`, md); writeFileSync(`${dir}/${date}.json`, JSON.stringify({ date, mode, ...res, errors, signals }, null, 1));
  writeFileSync(histF, JSON.stringify([...hist, ...(res.ideas || []).map((x) => ({ date, title: x.title, category: x.category }))].slice(-400), null, 1));
  const top = (res.ideas || []).slice(0, 3).map((x, i) => `${i + 1}. ${x.title}`).join('\n');
  const click = `https://github.com/${env.GITHUB_REPOSITORY || 'saieswarnookala/sec-edgar-worker'}/blob/main/data/ideas/latest.md`;
  console.log('notify', await notify(env, `💡 ${res.ideas?.length || 0} money ideas (${mode === 'ai' ? 'researched' : 'signals'})`, top || 'No strong signals today.', click));
  console.log(md.slice(0, 1500));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch((e) => { console.error(e); process.exit(1); });
