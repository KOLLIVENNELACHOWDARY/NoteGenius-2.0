# Vercel front door for NoteGenius

This folder is a tiny Vercel project with no code. Its `vercel.json` forwards every request to the NoteGenius Docker container running on Google Cloud Run, so visitors use your Vercel address (and any custom domain you add there).

1. Deploy the container first: `bash deploy/cloudrun.sh` (it writes `vercel.json` here).
2. In Vercel: **Add New > Project**, import this GitHub repo, set **Root Directory** to `vercel-proxy`, leave everything else empty, **Deploy**.
   Or with the CLI: `cd vercel-proxy && npx vercel --prod`.

Do not deploy the repo root to Vercel: it would try to build the Python app as a serverless function.
