const { send, isAdmin, status, redis } = require('../../lib/common');
module.exports = async (req, res) => {
  if (!isAdmin(req)) return send(res, 401, { ok: false, message: 'admin token galat' });
  try {
    const hs = (await redis.smembers('devices')) || [];
    const out = [];
    for (const h of hs.slice(0, 300)) {
      const st = await status(h);
      const dev = (await redis.getJson('dev:' + h)) || {};
      out.push({ hwid: h, premium: st.premium, type: st.type, remaining: st.remaining, used_min: Math.round(st.used_ms / 60000 * 10) / 10, key: dev.key || '', revoked: !!dev.revoked });
    }
    return send(res, 200, { ok: true, devices: out });
  } catch (e) { return send(res, 500, { ok: false, message: e.message }); }
};
