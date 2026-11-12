const { send, body, isAdmin, newKey, redis, DAY } = require('../../lib/common');
// POST {type:'lifetime'|'monthly'|'yearly', days?, key?} -> creates a key
module.exports = async (req, res) => {
  if (!isAdmin(req)) return send(res, 401, { ok: false, message: 'admin token galat' });
  try {
    const b = await body(req);
    const key = (b.key && String(b.key).toUpperCase()) || newKey();
    const type = b.type || 'lifetime';
    const rec = { type, days: Number(b.days) || (type === 'yearly' ? 365 : 30), bound: null, revoked: false, created_at: Date.now() };
    await redis.setJson('key:' + key, rec);
    await redis.sadd('keys', key);
    return send(res, 200, { ok: true, key, rec });
  } catch (e) { return send(res, 500, { ok: false, message: e.message }); }
};
