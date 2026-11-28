// Sends the private paper bots' monthly card (written by the encrypted paper job to a JSON file: names + numbers only) to ntfy.
// usage: NTFY_TOPIC=... node paper-notify.mjs /tmp/fr_notify.json
import { readFileSync } from 'node:fs';
import { paperSvg, reportPng } from './report.mjs';
const D = JSON.parse(readFileSync(process.argv[2], 'utf8')), topic = process.env.NTFY_TOPIC;
if (!topic) { console.log('no ntfy topic set: card not sent'); process.exit(0); }
const png = await reportPng(paperSvg(D));
const line = D.rows.filter((r) => r.name !== 'SPY').map((r) => `${r.name.replace('Mix ', '')} ${r.total_pct >= 0 ? '+' : ''}${r.total_pct.toFixed(1)}%`).join(' | ').replace(/[^\x20-\x7E]/g, '-');
const headers = png ? { Title: `Paper bots: ${D.month} card`, Message: line.slice(0, 900), Filename: 'paper-bots.png', Tags: 'bar_chart' } : { Title: `Paper bots: ${D.month} card`, Tags: 'bar_chart' };
const r = await fetch(`https://ntfy.sh/${topic}`, { method: png ? 'PUT' : 'POST', body: png || line, headers });
console.log('ntfy', r.status);
