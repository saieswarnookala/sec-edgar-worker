import assert from 'node:assert/strict';
import { parseRss, scoreSignal, dedupe, buildPrompt, parseIdeas, digestIdeas, toMarkdown, notify, collect } from './scripts/idea-scout.mjs';
const rss = '<rss><channel><item><title><![CDATA[Acme raises $5M seed]]></title><link>https://x.com/a</link><pubDate>Mon</pubDate></item><item><title>B</title><link>https://x.com/b</link></item></channel></rss>';
assert.deepEqual(parseRss(rss).map((x) => x.title), ['Acme raises $5M seed', 'B']);
assert.ok(scoreSignal({ title: 'Is there a tool to reconcile invoices?', points: 50 }) > scoreSignal({ title: 'Cool demo', points: 50 }));
assert.equal(dedupe([{ url: 'a' }, { url: 'A' }, { url: 'b' }]).length, 2);
const sig = { hn: [{ src: 'Ask HN', title: 'I would pay for a K8s cost tool', url: 'u1', points: 40 }], reddit: [], github: [{ src: 'GitHub', title: 'x/y: agent', url: 'u2', points: 900 }], producthunt: [], news: [], screener: [] };
const p = buildPrompt(sig, ['Old idea']); assert.ok(p.includes('K8s cost tool') && p.includes('Old idea') && p.includes('JSON'));
assert.equal(parseIdeas('Here you go:\n{"summary":"s","ideas":[{"title":"T"}]}\nthanks').ideas[0].title, 'T');
const d = digestIdeas({ ...sig, hn: [...sig.hn.map((x) => ({ ...x, score: 5 })), { src: 'Ask HN', title: 'Which TV do you recommend for privacy?', text: 'doing it manually', score: 9 }] });
assert.equal(d.ideas[0].title, 'I would pay for a K8s cost tool'); assert.ok(!d.ideas.some((x) => x.title.includes('TV'))); assert.equal(d.ideas.length, 2);
const md = toMarkdown('2026-11-05', { summary: 'S', ideas: [{ title: 'T', category: 'build', what: 'W', evidence: ['https://e'] }] }, { reddit: '403' });
assert.ok(md.includes('## 1. T') && md.includes('reddit (403)'));
// notify with mocked fetch
const calls = []; globalThis.fetch = async (url, opt) => { calls.push([url, opt]); return { ok: true, status: 200, json: async () => ({}), text: async () => '' }; };
const sent = await notify({ NTFY_TOPIC: 'abc' }, 'Title', 'Msg', 'https://click'); assert.equal(sent[0], 'ntfy ok'); assert.equal(calls[0][0], 'https://ntfy.sh/'); const b = JSON.parse(calls[0][1].body); assert.equal(b.topic, 'abc'); assert.equal(b.click, 'https://click'); assert.equal(b.title, 'Title');
// collect tolerates failing sources
globalThis.fetch = async () => ({ ok: false, status: 403 });
const c = await collect(Date.now(), {}); assert.equal(c.signals.hn.length, 0); assert.ok(c.errors.hn);
console.log('idea scout tests passed');
