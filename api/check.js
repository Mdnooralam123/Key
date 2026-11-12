// Old link compatibility: /check?key=KHAN-XXXX-XXXX-XXXX&hwid=...
const { send, validHwid, status, remember, redis, DAY } = require('../lib/common');
module.exports = async (req, res) => {
  try {
    const key = String((req.query && req.query.key) || '').trim().toUpperCase();
    const hwid = String((req.query && req.query.hwid) || '');
    const rec = key ? await redis.getJson('key:' + key) : null;
    if (!rec) return send(res, 200, { valid: false, status: 'fail', message: 'Key galat hai', real: false });
    if (rec.bound && hwid && rec.bound !== hwid) return send(res, 200, { valid: false, status: 'fail', message: 'Key kisi aur device par lock hai', real: true });
    const st = hwid && validHwid(hwid) ? await status(hwid) : { premium: false };
    return send(res, 200, { valid: true, status: 'success', real: true, expired: false, type: rec.type, remaining: rec.type === 'lifetime' ? 'Lifetime' : (st.remaining || ''), message: rec.bound ? 'Key device par lock hai' : 'Key valid hai' });
  } catch (e) { return send(res, 500, { valid: false, status: 'error', message: e.message }); }
};
