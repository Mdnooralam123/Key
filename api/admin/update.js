const { send, body, isAdmin, redis } = require('../../lib/common');
// POST {version: 34, apk_url: 'https://...apk', notes: '...'} -> phone me update dikhega
module.exports = async (req, res) => {
  if (!isAdmin(req)) return send(res, 401, { ok: false, message: 'admin token galat' });
  try {
    const b = await body(req);
    const u = { version: Number(b.version) || 0, apk_url: String(b.apk_url || ''), notes: String(b.notes || '') };
    await redis.setJson('cfg:update', u);
    return send(res, 200, { ok: true, update: u });
  } catch (e) { return send(res, 500, { ok: false, message: e.message }); }
};
