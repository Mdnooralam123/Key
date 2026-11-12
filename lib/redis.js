// Upstash Redis over REST (no npm packages needed).
// Vercel dashboard me Upstash Redis add karo; env vars: UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
const URL_ = process.env.UPSTASH_REDIS_REST_URL;
const TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN;

async function cmd(args) {
  if (!URL_ || !TOKEN) throw new Error('Redis env vars set nahi hain');
  const r = await fetch(URL_, {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify(args)
  });
  const j = await r.json();
  if (j.error) throw new Error(j.error);
  return j.result;
}

module.exports = {
  get: (k) => cmd(['GET', k]),
  set: (k, v) => cmd(['SET', k, v]),
  incrby: (k, n) => cmd(['INCRBY', k, n]),
  sadd: (k, v) => cmd(['SADD', k, v]),
  smembers: (k) => cmd(['SMEMBERS', k]),
  del: (k) => cmd(['DEL', k]),
  async getJson(k) { const v = await cmd(['GET', k]); return v ? JSON.parse(v) : null; },
  async setJson(k, o) { return cmd(['SET', k, JSON.stringify(o)]); }
};
