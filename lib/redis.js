// Upstash Redis REST client. Supports both Upstash and Vercel KV env names.
// Required on Vercel:
// UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN
// OR KV_REST_API_URL + KV_REST_API_TOKEN
function getConfig() {
  const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN;
  if (!url || !token) {
    const missing = [];
    if (!url) missing.push('UPSTASH_REDIS_REST_URL (or KV_REST_API_URL)');
    if (!token) missing.push('UPSTASH_REDIS_REST_TOKEN (or KV_REST_API_TOKEN)');
    const err = new Error('Redis configuration missing. Vercel Project Settings > Environment Variables me set karein: ' + missing.join(', '));
    err.code = 'REDIS_ENV_MISSING';
    throw err;
  }
  return { url, token };
}

async function cmd(args) {
  const { url, token } = getConfig();
  let response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify(args)
    });
  } catch (e) {
    throw new Error('Redis network connection failed: ' + e.message);
  }
  let data;
  try { data = await response.json(); }
  catch (_) { throw new Error('Redis returned an invalid response (HTTP ' + response.status + ')'); }
  if (!response.ok || data.error) {
    throw new Error('Redis request failed (HTTP ' + response.status + '): ' + (data.error || response.statusText));
  }
  return data.result;
}

module.exports = {
  get: (k) => cmd(['GET', k]),
  set: (k, v) => cmd(['SET', k, v]),
  incrby: (k, n) => cmd(['INCRBY', k, n]),
  sadd: (k, v) => cmd(['SADD', k, v]),
  smembers: (k) => cmd(['SMEMBERS', k]),
  del: (k) => cmd(['DEL', k]),
  async getJson(k) { const v = await cmd(['GET', k]); return v ? JSON.parse(v) : null; },
  async setJson(k, o) { return cmd(['SET', k, JSON.stringify(o)]); },
  // Safe diagnostic: never returns credentials.
  configStatus() {
    const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
    const token = process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN;
    return { configured: !!(url && token), url_present: !!url, token_present: !!token };
  }
};
