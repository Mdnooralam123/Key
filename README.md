# Maya License Server

## Required Vercel configuration

This project stores license keys, device HWIDs, trial usage, and update metadata in Redis. It cannot persist this data without a real Redis database.

1. Create an Upstash Redis database (or connect an existing Vercel KV/Upstash database).
2. In Vercel, open **Project → Settings → Environment Variables**.
3. Add these variables for **Production**, **Preview**, and **Development** as needed:
   - `UPSTASH_REDIS_REST_URL` = the database REST URL
   - `UPSTASH_REDIS_REST_TOKEN` = the database REST token
   - `ADMIN_TOKEN` = `khan123` (change this to a strong private token for a public production deployment)
4. If Vercel provides `KV_REST_API_URL` and `KV_REST_API_TOKEN` instead, the server supports those names too. Do not add placeholder values.
5. Save the variables and **Redeploy** the project. Existing deployments do not automatically receive newly added environment variables.
6. Open `/admin.html`, enter the deployed server URL, enter admin token `khan123`, then use the admin actions.

Never put the Redis REST token in frontend HTML, APK code, screenshots, or public source control. It must remain a server-side environment variable.

## Troubleshooting

- `Redis configuration missing`: one or both Redis environment variables are absent or named incorrectly.
- Redis HTTP 401/403: REST token is invalid or belongs to another database.
- Redis network/invalid response: check the REST URL and database status.
- After changing environment variables, redeploy the Vercel project.
