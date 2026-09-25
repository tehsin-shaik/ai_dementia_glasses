# Deploying the demo to Vercel

The Next.js frontend and the FastAPI backend deploy together as one Vercel
project on a single domain, using [Vercel Services](https://vercel.com/docs/services).
The root `vercel.json` builds each app separately and routes `/api/*` to the
API and everything else to the web app, so the browser only ever talks to its
own origin.

This is a hosted **demo**, not production hosting. Read the storage note at the
end before relying on it.

## Project settings

1. Vercel → **Add New… → Project** → import `tehsin-shaik/ai_dementia_glasses`.
2. Leave **Root Directory** empty (the repository root) and the framework
   preset on **Other**; `vercel.json` drives both builds.
3. Add environment variables:

   | Name | Value |
   | --- | --- |
   | `DATABASE_URL` | `sqlite:////tmp/memorycue.db` (four slashes — absolute path) |
   | `MEDIA_DIR` | `/tmp/media` |
   | `SEED_ON_STARTUP` | `1` |
   | `NEXT_PUBLIC_API_URL` | the project's own URL, e.g. `https://memorycue.vercel.app` |

4. Deploy, then check `https://<project>.vercel.app/api/health` returns
   `{"status":"ok"}` and that `/`, `/app`, and `/caregiver` load.

`NEXT_PUBLIC_API_URL` is read at build time, so a redeploy is required after
changing it. `ALLOWED_ORIGINS` is only needed when the frontend runs on a
different origin than the API (for example a locally run web app pointed at the
hosted API); requests from an unlisted origin are rejected by CORS.

The production URL is built from the repository's production branch. The demo
work lives on `demo`, so set **Settings → Git → Production Branch** to `demo`
(or merge `demo` into `main` first).

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
