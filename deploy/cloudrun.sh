#!/usr/bin/env bash
# Build the Docker image in Google Cloud and run it on Cloud Run, then point the Vercel proxy at it.
# Easiest place to run this: Google Cloud Shell (console.cloud.google.com, the ">_" button). It already has gcloud and git.
#   git clone https://github.com/KOLLIVENNELACHOWDARY/NoteGenius.git && cd NoteGenius
#   PROJECT=your-gcp-project-id bash deploy/cloudrun.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-asia-south1}"      # Mumbai. Other options: asia-southeast1, us-central1, europe-west1
SERVICE="${SERVICE:-notegenius}"
[ -n "$PROJECT" ] || { echo "Set PROJECT=your-gcp-project-id first."; exit 1; }

echo "Enabling Google Cloud services (first time only)..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project "$PROJECT"

COMMON="COOKIE_SECURE=1,QA_BACKEND=search,DATA_DIR=/tmp/notegenius"
if gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" >/dev/null 2>&1; then
  ENVFLAG=(--update-env-vars "$COMMON")            # keep the existing SECRET_KEY on redeploys
else
  KEY="${SECRET_KEY:-$(python3 -c 'import secrets;print(secrets.token_hex(32))')}"
  ENVFLAG=(--set-env-vars "SECRET_KEY=$KEY,$COMMON")
fi

echo "Building and deploying (about 5 to 10 minutes the first time)..."
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source . --quiet \
  --allow-unauthenticated --memory 1Gi --cpu 1 --cpu-boost \
  --min-instances 0 --max-instances 1 --concurrency 8 --timeout 120 \
  "${ENVFLAG[@]}"

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')"
HOST="${URL#https://}"
sed "s#BACKEND_HOST#${HOST}#" vercel-proxy/vercel.json.template > vercel-proxy/vercel.json

cat <<MSG

Done. The app is live at: $URL
Test it:        bash deploy/check.sh $URL
Vercel config:  vercel-proxy/vercel.json now points at $HOST

Next (Vercel):
  1. git add vercel-proxy/vercel.json && git commit -m "Point Vercel at Cloud Run" && git push
  2. Vercel > Add New > Project > import the repo > Root Directory: vercel-proxy > Deploy
MSG
