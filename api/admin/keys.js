const { send, isAdmin, redis } = require('../../lib/common');
module.exports = async (req, res) => {
  if (!isAdmin(req)) return send(res, 401, { ok: false, message: 'admin token galat' });
  try {
    const keys = (await redis.smembers('keys')) || [];
    const out = [];
    for (const k of keys.slice(0, 200)) out.push(Object.assign({ key: k }, (await redis.getJson('key:' + k)) || {}));
    return send(res, 200, { ok: true, keys: out });
  } catch (e) { return send(res, 500, { ok: false, message: e.message }); }
};
