#!/usr/bin/env bash
# Smoke test for a deployed service (step 3d): the three questions to ask after every deploy.
#   1. Is the process alive?          GET /health  -> 200
#   2. Can it answer?                 GET /ready   -> 200 (DB reachable, index not empty)
#   3. Does a real question work?     POST /ask with a key -> 200, cited sources, cost
# And one negative check: /ask WITHOUT a key must be 401, or the service is open to everyone.
#
#   API_KEY=... scripts/smoke.sh https://rag-api-xxxx.europe-west3.run.app
#   API_KEY=... make smoke          (finds the URL with gcloud)
set -euo pipefail

URL="${1:?usage: API_KEY=... $0 <service url>}"
: "${API_KEY:?set API_KEY to one of the keys in the api-keys secret}"
Q='{"question": "How do I make a query parameter optional?"}'

step() { printf '\n== %s\n' "$1"; }

step "GET /health (liveness)"
curl -sS --fail-with-body "$URL/health"; echo

step "GET /ready (readiness)"
curl -sS --fail-with-body "$URL/ready"; echo

step "POST /ask without a key (must be 401)"
code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$URL/ask" \
  -H 'Content-Type: application/json' -d "$Q")
echo "$code"
[ "$code" = "401" ] || { echo "FAIL: /ask is not protected"; exit 1; }

step "POST /ask with a key (one real question, costs about \$0.008)"
curl -sS --fail-with-body -X POST "$URL/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" -d "$Q" -D - \
  | grep -iE '^x-request-id|"answer"|"cost_usd"' | cut -c1-300

printf '\nOK: all smoke checks passed\n'
