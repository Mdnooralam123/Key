const { send, redis } = require('../lib/common');
module.exports = async (req, res) => {
  try {
    const u = (await redis.getJson('cfg:update')) || { version: 0, apk_url: '', notes: '' };
    return send(res, 200, u);
  } catch (e) { return send(res, 500, { ok: false, message: e.message }); }
};
