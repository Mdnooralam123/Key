const { send, body, validHwid, status, remember, redis } = require('../lib/common');
// Client sends the milliseconds it actually used (max 30 s per call). Server adds them to the device trial.
module.exports = async (req, res) => {
  try {
    if (req.method !== 'POST') return send(res, 405, { ok: false });
    const b = await body(req);
    if (!validHwid(b.hwid)) return send(res, 400, { ok: false, message: 'hwid galat' });
    await remember(b.hwid);
    const ms = Math.max(0, Math.min(Number(b.ms) || 0, 30000));
    const st = await status(b.hwid);
    if (!st.premium && ms > 0) await redis.incrby('trial:' + b.hwid, ms);
    return send(res, 200, Object.assign({ ok: true }, await status(b.hwid)));
  } catch (e) { return send(res, 500, { ok: false, message: 'server error: ' + e.message }); }
};
