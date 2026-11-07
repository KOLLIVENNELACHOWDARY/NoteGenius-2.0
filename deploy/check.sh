#!/usr/bin/env bash
# Quick health check: bash deploy/check.sh https://your-app.vercel.app
set -u
URL="${1:?usage: check.sh https://your-url}"
URL="${URL%/}"
ok() { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; FAILED=1; }
FAILED=0
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 "$URL/healthz"); [ "$code" = 200 ] && ok "healthz ($code)" || bad "healthz ($code)"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 "$URL/"); [ "$code" = 200 ] && ok "home page ($code)" || bad "home page ($code)"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 "$URL/static/vendor/katex/katex.min.js"); [ "$code" = 200 ] && ok "formula library ($code)" || bad "formula library ($code)"
cc=$(curl -sI --max-time 60 "$URL/" | tr -d '\r' | grep -i '^cache-control:' || true)
case "$cc" in *no-store*) ok "pages are not cached";; *) bad "pages may be cached by a CDN: $cc";; esac
[ "$FAILED" = 0 ] && echo "All good." || { echo "Something failed. The first request after idle can take 10 to 30 seconds: run again."; exit 1; }
