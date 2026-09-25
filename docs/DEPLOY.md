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
   | `DATABASE_URL` | a Postgres URL, e.g. `postgresql://user:pw@host/db` (see below) |
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
instance and disappears when the instance is recycled. A SQLite file there is
therefore per-instance: a caregiver correction can land on one instance while
the next question is answered by another that never saw it.

So the hosted demo uses a hosted Postgres database instead. Any provider works
(Neon and Supabase both have a free tier); `DATABASE_URL` accepts the
`postgres://` or `postgresql://` URL they hand out and the app routes it to the
`psycopg` driver itself. The demo profiles are seeded on the first cold start
against an empty database, and everything written afterwards — saved moments,
caregiver corrections — is shared by every instance and survives redeploys.

Setting `DATABASE_URL` to `sqlite:////tmp/memorycue.db` still works for a
throwaway deploy, with the caveat above.

Photos are the remaining exception: `MEDIA_DIR` is a plain directory, so images
saved on the hosted demo still live in `/tmp` and disappear with the instance
while their text records remain.
