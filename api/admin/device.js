const { send, body, isAdmin, redis, validHwid, DAY } = require('../../lib/common');
// POST {hwid, action: reset_trial | grant_days | revoke | unrevoke, days?}
module.exports = async (req, res) => {
  if (!isAdmin(req)) return send(res, 401, { ok: false, message: 'admin token galat' });
  try {
    const b = await body(req);
    if (!validHwid(b.hwid)) return send(res, 400, { ok: false, message: 'hwid galat' });
    if (b.action === 'reset_trial') await redis.set('trial:' + b.hwid, 0);
    else if (b.action === 'grant_days') {
      const dev = (await redis.getJson('dev:' + b.hwid)) || {};
      const base = dev.expires_at && dev.expires_at > Date.now() ? dev.expires_at : Date.now();
      await redis.setJson('dev:' + b.hwid, Object.assign(dev, { premium: true, revoked: false, type: dev.type || 'manual', expires_at: base + (Number(b.days) || 30) * DAY }));
    } else if (b.action === 'revoke') {
      const dev = (await redis.getJson('dev:' + b.hwid)) || {};
      await redis.setJson('dev:' + b.hwid, Object.assign(dev, { revoked: true, premium: false }));
    } else if (b.action === 'unrevoke') {
      const dev = (await redis.getJson('dev:' + b.hwid)) || {};
      await redis.setJson('dev:' + b.hwid, Object.assign(dev, { revoked: false }));
    } else return send(res, 400, { ok: false, message: 'action galat' });
    return send(res, 200, { ok: true });
  } catch (e) { return send(res, 500, { ok: false, message: e.message }); }
};
