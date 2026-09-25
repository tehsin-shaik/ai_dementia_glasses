# Deploying the demo to Vercel

The demo runs as two Vercel projects from this one repository: the Next.js
frontend and the FastAPI backend. Both are free-tier friendly.

This is a hosted **demo**, not production hosting. Read the storage note at the
end before relying on it.

## 1. Backend project

1. Vercel → **Add New… → Project** → import `tehsin-shaik/ai_dementia_glasses`.
2. Set **Root Directory** to `apps/api`. Vercel detects FastAPI and loads
   `app/main.py`.
3. Add environment variables:

   | Name | Value |
   | --- | --- |
   | `DATABASE_URL` | `sqlite:////tmp/memorycue.db` (four slashes — absolute path) |
   | `MEDIA_DIR` | `/tmp/media` |
   | `SEED_ON_STARTUP` | `1` |
   | `ALLOWED_ORIGINS` | the frontend URL, e.g. `https://memorycue.vercel.app` |

4. Deploy, then check `https://<backend>.vercel.app/api/health` returns
   `{"status":"ok"}`.

## 2. Frontend project

The existing project that already builds pull-request previews. Add one
environment variable and redeploy:

| Name | Value |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | the backend URL, e.g. `https://memorycue-api.vercel.app` |

`NEXT_PUBLIC_API_URL` is read at build time, so a redeploy is required after
changing it.

Set `ALLOWED_ORIGINS` on the backend to the frontend's final domain, including
any custom domain; requests from an unlisted origin are rejected by CORS.

Both projects deploy their production URL from the repository's production
branch. The demo work lives on `demo`, so set **Settings → Git → Production
Branch** to `demo` in both projects (or merge `demo` into `main` first).

## Dependencies

`apps/api/requirements.txt` holds only what the API needs at runtime.
The local face-recognition stack (`dlib-bin`, `face-recognition-models`) is in
`apps/api/requirements-dev.txt`, because the pretrained models are far larger
than a serverless bundle allows. Face recognition therefore reports itself as
not configured on Vercel; every other surface — capture, review, save, query,
rewind, caregiver corrections — works.

## Storage on serverless

A Vercel function only has a writable `/tmp`, and that disk belongs to one
instance and disappears when the instance is recycled. So on the hosted demo:

- the demo profiles are seeded automatically on a cold start, meaning the demo
  is always immediately usable;
- moments and photos saved during a session are lost when the instance is
  recycled.

For a live pitch this is fine — rehearse and present within one session. For
data that has to survive, run the backend on a host with a persistent disk
(Render, Railway, Fly) and point `NEXT_PUBLIC_API_URL` at it instead; no code
change is needed.
