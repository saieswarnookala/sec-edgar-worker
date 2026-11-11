// Fallback executor: Robinhood calls go through the official Claude Code + Robinhood MCP connection.
// Our code still decides every order. Each call runs `claude -p` allowed to use exactly ONE Robinhood tool,
// and we read Claude Code's event stream to check it made exactly one call, to that tool, with exactly our arguments.
// Anything else fails closed (and an unexpected order placement halts the bot).
import { spawn } from 'node:child_process';
import { readFileSync, existsSync, writeFileSync } from 'node:fs';

const canon = (v) => (Array.isArray(v) ? v.map(canon) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, canon(v[k])])) : typeof v === 'number' ? +v.toFixed(6) : v);
export const sameArgs = (a, b) => JSON.stringify(canon(a ?? {})) === JSON.stringify(canon(b ?? {}));

export function runClaude(prompt, { bin = 'claude', allowed = [], timeoutMs = 180e3 } = {}) {
  return new Promise((resolve, reject) => {
    const args = ['-p', prompt, '--output-format', 'stream-json', '--verbose', '--max-turns', '3'];
    if (allowed.length) args.push('--allowedTools', allowed.join(','));
    const p = spawn(bin, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '';
    const t = setTimeout(() => { p.kill('SIGKILL'); reject(new Error('claude -p timed out')); }, timeoutMs);
    p.stdout.on('data', (d) => (out += d)); p.stderr.on('data', (d) => (err += d));
    p.on('error', (e) => { clearTimeout(t); reject(e); });
    p.on('close', (code) => {
      clearTimeout(t);
      const events = out.split('\n').filter(Boolean).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
      if (!events.length) return reject(new Error(`claude -p gave no output (exit ${code}): ${err.slice(0, 300)}`));
      resolve(events);
    });
  });
}

// Pull every tool call and tool result out of Claude Code's stream-json events.
export function toolEvents(events) {
  const uses = [], results = {};
  for (const e of events) for (const c of e?.message?.content || []) {
    if (e.type === 'assistant' && c.type === 'tool_use') uses.push({ id: c.id, name: c.name, input: c.input });
    if (e.type === 'user' && c.type === 'tool_result') results[c.tool_use_id] = { text: typeof c.content === 'string' ? c.content : (c.content || []).filter((x) => x.type === 'text').map((x) => x.text).join('\n'), isError: !!c.is_error };
  }
  return { uses, results, final: events.find((e) => e.type === 'result') };
}

export class UnexpectedAction extends Error { constructor(m, placed) { super(m); this.name = 'UnexpectedAction'; this.placed = placed; } }

// Client with the same shape as the MCP SDK Client (listTools / callTool), so live-dip.mjs works unchanged.
export function claudeClient({ bin = process.env.CLAUDE_BIN || 'claude', server = process.env.CLAUDE_MCP_SERVER || 'robinhood', toolsFile } = {}) {
  const full = (n) => `mcp__${server}__${n}`;
  return {
    claude: true,
    async listTools() {
      if (toolsFile && existsSync(toolsFile)) return { tools: JSON.parse(readFileSync(toolsFile, 'utf8')) };
      const ev = await runClaude(`List every tool you have whose name starts with "${full('')}". Output ONLY a JSON array, no prose, of objects {"name": <name without the "${full('')}" prefix>, "description": <first sentence>, "inputSchema": <the tool's exact JSON input schema>}. Do not call any tool.`, { bin, allowed: [] });
      const { uses, final } = toolEvents(ev);
      if (uses.length) throw new UnexpectedAction('Claude called a tool while listing tools');
      const txt = String(final?.result || '').replace(/^```(json)?|```$/gm, '').trim();
      const tools = JSON.parse(txt);
      if (toolsFile) writeFileSync(toolsFile, JSON.stringify(tools, null, 1));
      return { tools };
    },
    async callTool({ name, arguments: args }) {
      const prompt = `Call the tool ${full(name)} exactly once with exactly these arguments, unchanged:\n${JSON.stringify(args)}\nDo not call any other tool. Do not retry. After the call, reply with the single word DONE.`;
      const ev = await runClaude(prompt, { bin, allowed: [full(name)] });
      const { uses, results } = toolEvents(ev);
      const robin = uses.filter((u) => u.name.startsWith(full('')));
      const placedOrder = robin.some((u) => /place_|cancel_/.test(u.name));
      if (robin.length !== 1) throw new UnexpectedAction(`expected 1 Robinhood call, Claude made ${robin.length}`, placedOrder && robin.length > 1);
      const u = robin[0];
      if (u.name !== full(name)) throw new UnexpectedAction(`Claude called ${u.name} instead of ${full(name)}`, placedOrder);
      if (!sameArgs(u.input, args)) throw new UnexpectedAction(`Claude changed the arguments: sent ${JSON.stringify(u.input)} instead of ${JSON.stringify(args)}`, placedOrder);
      const r = results[u.id];
      if (!r) throw new Error(`no result returned for ${name}`);
      return { content: [{ type: 'text', text: r.text }], isError: r.isError };
    },
  };
}
