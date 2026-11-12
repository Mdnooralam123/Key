const { send, body, validHwid, status, remember, redis, DAY } = require('../lib/common');
// Key is bound to the first device that activates it. Same device can activate again after reinstall (same HWID).
module.exports = async (req, res) => {
  try {
    if (req.method !== 'POST') return send(res, 405, { ok: false });
    const b = await body(req);
    if (!validHwid(b.hwid)) return send(res, 400, { ok: false, message: 'hwid galat' });
    const key = String(b.key || '').trim().toUpperCase();
    const rec = key ? await redis.getJson('key:' + key) : null;
    if (!rec || rec.revoked) return send(res, 200, { ok: false, message: 'Key galat hai ya band ho chuki hai' });
    if (rec.bound && rec.bound !== b.hwid) return send(res, 200, { ok: false, message: 'Ye key kisi aur device par lock hai' });
    if (rec.expires_at && Date.now() > rec.expires_at) return send(res, 200, { ok: false, message: 'Ye key expire ho chuki hai' });
    rec.bound = b.hwid;
    rec.bound_at = rec.bound_at || Date.now();
    await redis.setJson('key:' + key, rec);
    const dev = { premium: true, revoked: false, type: rec.type, key, expires_at: rec.type === 'lifetime' ? null : (rec.expires_at || Date.now() + (rec.days || 30) * DAY) };
    await redis.setJson('dev:' + b.hwid, dev);
    await remember(b.hwid);
    return send(res, 200, Object.assign({ ok: true, message: 'Premium chalu ho gaya' }, await status(b.hwid)));
  } catch (e) { return send(res, 500, { ok: false, message: 'server error: ' + e.message }); }
};
