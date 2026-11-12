const redis = require('./redis');

const TRIAL_MS = 10 * 60 * 1000;
const DAY = 86400000;

function send(res, code, obj) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(obj));
}

function body(req) {
  if (req.body && typeof req.body === 'object') return Promise.resolve(req.body);
  return new Promise((resolve) => {
    let d = '';
    req.on('data', (c) => (d += c));
    req.on('end', () => { try { resolve(JSON.parse(d || '{}')); } catch (e) { resolve({}); } });
  });
}

function validHwid(h) { return typeof h === 'string' && h.length >= 8 && h.length <= 128 && /^[A-Za-z0-9_-]+$/.test(h); }

async function status(hwid) {
  const dev = (await redis.getJson('dev:' + hwid)) || {};
  const used = Number((await redis.get('trial:' + hwid)) || 0);
  let premium = false, type = '', remaining = '';
  if (dev.premium && !dev.revoked) {
    if (dev.type === 'lifetime') { premium = true; type = 'lifetime'; remaining = 'Lifetime'; }
    else if (dev.expires_at && Date.now() < dev.expires_at) {
      premium = true; type = dev.type || 'premium';
      const d = Math.ceil((dev.expires_at - Date.now()) / DAY);
      remaining = d + ' din';
    }
  }
  return {
    premium, type, remaining,
    left_ms: premium ? 999999999 : Math.max(0, TRIAL_MS - used),
    used_ms: used, hwid
  };
}

async function remember(hwid) {
  await redis.sadd('devices', hwid);
}

function isAdmin(req) {
  const t = process.env.ADMIN_TOKEN || 'khan123';
  return !!t && req.headers['x-admin-token'] === t;
}

function newKey() {
  const c = require('crypto');
  const part = () => c.randomBytes(2).toString('hex').toUpperCase().slice(0, 4);
  return 'KHAN-' + part() + '-' + part() + '-' + part();
}

module.exports = { TRIAL_MS, DAY, send, body, validHwid, status, remember, isAdmin, newKey, redis };
