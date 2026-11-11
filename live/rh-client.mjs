// Robinhood official trading MCP client (https://agent.robinhood.com/mcp/trading), plain code, no AI in the order path.
// Lessons from other builders baked in:
//  - never open a browser sign-in when unattended: fail closed and alert instead (one bot opened ~67 tabs)
//  - refresh the token ourselves at startup using the SAVED expiry (the SDK forgets expiry across restarts)
//  - tokens live in a 0600 file on the VM, never in git
import { readFileSync, writeFileSync, existsSync, mkdirSync, chmodSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { discoverOAuthServerInfo, refreshAuthorization } from '@modelcontextprotocol/sdk/client/auth.js';

export const RH_URL = process.env.RH_MCP_URL || 'https://agent.robinhood.com/mcp/trading';
export const HOME = process.env.SENTINEL_HOME || join(homedir(), '.sentinel-live');
const AUTH_FILE = join(HOME, 'rh-auth.json');
const PORT = +(process.env.RH_CALLBACK_PORT || 8765);
export class AuthRequired extends Error { constructor(m) { super(m); this.name = 'AuthRequired'; } }

const load = () => (existsSync(AUTH_FILE) ? JSON.parse(readFileSync(AUTH_FILE, 'utf8')) : {});
const save = (o) => { mkdirSync(HOME, { recursive: true, mode: 0o700 }); writeFileSync(AUTH_FILE, JSON.stringify(o, null, 1), { mode: 0o600 }); chmodSync(AUTH_FILE, 0o600); };

export function makeProvider({ interactive = false, onUrl = () => {} } = {}) {
  return {
    get redirectUrl() { return `http://localhost:${PORT}/callback`; },
    get clientMetadata() { return { client_name: 'sentinel-live (dip strategy)', redirect_uris: [`http://localhost:${PORT}/callback`], grant_types: ['authorization_code', 'refresh_token'], response_types: ['code'], token_endpoint_auth_method: 'none' }; },
    clientInformation: () => load().client_information,
    saveClientInformation: (ci) => save({ ...load(), client_information: ci }),
    tokens: () => load().tokens,
    saveTokens: (t) => save({ ...load(), tokens: t, saved_at: Date.now() }),
    saveCodeVerifier: (v) => save({ ...load(), code_verifier: v }),
    codeVerifier: () => load().code_verifier,
    redirectToAuthorization: (url) => {
      if (!interactive) throw new AuthRequired('Robinhood sign-in expired. On the VM run: cd ~/sec-edgar-worker/live && node live-dip.mjs login');
      onUrl(String(url));
    },
  };
}

// Seconds until the saved access token expires (null if unknown).
export function tokenSecondsLeft(a = load(), now = Date.now()) {
  if (!a.tokens || !a.saved_at || !a.tokens.expires_in) return null;
  return Math.round((a.saved_at + a.tokens.expires_in * 1000 - now) / 1000);
}

// Refresh ahead of expiry with the saved refresh token. Throws AuthRequired if that is impossible.
export async function ensureFresh({ minSeconds = 1800 } = {}) {
  const a = load();
  if (!a.tokens?.access_token) throw new AuthRequired('Not signed in to Robinhood yet. Run: node live-dip.mjs login');
  const left = tokenSecondsLeft(a);
  if (left != null && left > minSeconds) return { refreshed: false, seconds_left: left };
  if (!a.tokens.refresh_token) { if (left == null || left > 0) return { refreshed: false, seconds_left: left }; throw new AuthRequired('Robinhood token expired and there is no refresh token. Run login.'); }
  try {
    const info = await discoverOAuthServerInfo(RH_URL);
    const t = await refreshAuthorization(info.authorizationServerUrl, { metadata: info.authorizationServerMetadata, clientInformation: a.client_information, refreshToken: a.tokens.refresh_token, resource: new URL(RH_URL) });
    save({ ...a, tokens: { ...t, refresh_token: t.refresh_token || a.tokens.refresh_token }, saved_at: Date.now(), last_refresh: new Date().toISOString() });
    return { refreshed: true, seconds_left: t.expires_in ?? null };
  } catch (e) {
    if (left != null && left > 60) return { refreshed: false, seconds_left: left, refresh_error: String(e.message || e) };
    throw new AuthRequired('Robinhood token refresh failed (' + String(e.message || e).slice(0, 120) + '). Run login.');
  }
}

export async function connect({ interactive = false, onUrl } = {}) {
  const transport = new StreamableHTTPClientTransport(new URL(RH_URL), { authProvider: makeProvider({ interactive, onUrl }) });
  const client = new Client({ name: 'sentinel-live', version: '1.0.0' });
  await client.connect(transport);
  return { client, transport };
}

// Pull JSON out of an MCP tool result (structuredContent first, then text blocks).
export function parseResult(r) {
  if (r?.structuredContent) return r.structuredContent;
  const txt = (r?.content || []).filter((c) => c.type === 'text').map((c) => c.text).join('\n');
  try { return JSON.parse(txt); } catch { return txt; }
}

export async function call(client, name, args = {}) {
  const r = await client.callTool({ name, arguments: args });
  const data = parseResult(r);
  if (r?.isError) { const e = new Error(`${name} failed: ${typeof data === 'string' ? data.slice(0, 300) : JSON.stringify(data).slice(0, 300)}`); e.data = data; throw e; }
  return data;
}

// One-time interactive login. Run on the VM with an SSH tunnel: ssh -L 8765:localhost:8765 ubuntu@<vm-ip>
export async function login() {
  let url;
  const transport = new StreamableHTTPClientTransport(new URL(RH_URL), { authProvider: makeProvider({ interactive: true, onUrl: (u) => { url = u; } }) });
  const client = new Client({ name: 'sentinel-live', version: '1.0.0' });
  try { await client.connect(transport); console.log('Already signed in.'); return client; } catch (e) { if (!url) throw e; }
  console.log('\nOpen this link in the browser on your laptop (keep the SSH tunnel open):\n\n' + url + '\n');
  const code = await new Promise((resolve, reject) => {
    const srv = createServer((req, res) => {
      const u = new URL(req.url, `http://localhost:${PORT}`);
      if (u.pathname !== '/callback') { res.writeHead(404); res.end(); return; }
      const c = u.searchParams.get('code'), err = u.searchParams.get('error');
      res.writeHead(200, { 'content-type': 'text/plain' }); res.end(c ? 'Robinhood connected. You can close this tab.' : 'Login failed: ' + err);
      srv.close(); c ? resolve(c) : reject(new Error('login failed: ' + err));
    }).listen(PORT, '127.0.0.1');
    setTimeout(() => { srv.close(); reject(new Error('login timed out after 10 minutes')); }, 600e3).unref();
  });
  await transport.finishAuth(code);
  const t2 = new StreamableHTTPClientTransport(new URL(RH_URL), { authProvider: makeProvider({ interactive: false }) });
  const c2 = new Client({ name: 'sentinel-live', version: '1.0.0' });
  await c2.connect(t2);
  console.log('Signed in. Token valid for about', Math.round((tokenSecondsLeft() || 0) / 3600), 'hours; refreshed automatically.');
  return c2;
}
