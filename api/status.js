const { send, validHwid, status, remember } = require('../lib/common');
module.exports = async (req, res) => {
  try {
    const hwid = String((req.query && req.query.hwid) || '');
    if (!validHwid(hwid)) return send(res, 400, { ok: false, message: 'hwid galat' });
    await remember(hwid);
    return send(res, 200, Object.assign({ ok: true }, await status(hwid)));
  } catch (e) { return send(res, 500, { ok: false, message: 'server error: ' + e.message }); }
};
