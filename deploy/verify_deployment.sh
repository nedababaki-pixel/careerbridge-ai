#!/usr/bin/env bash
# CareerBridge AI - READ-ONLY check of a deployed site, run from your own computer:
#     bash deploy/verify_deployment.sh careerbridge.example.com
#
# It only sends normal web requests (no CV data) and changes nothing.
# Exit code 0 = all checks passed, 1 = at least one check failed.
set -u
HOST="${1:?Usage: verify_deployment.sh <domain or IP>}"
PASS=0; FAIL=0
ok()   { printf '  PASS  %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

echo "Checking https://$HOST"

# 1. HTTP must redirect to HTTPS (no app content over plain HTTP)
code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "http://$HOST/")
loc=$(curl -s -m 10 -o /dev/null -w '%{redirect_url}' "http://$HOST/")
check "HTTP / redirects to HTTPS (got $code -> $loc)" '[ "$code" = 301 ] || [ "$code" = 308 ]; [[ "$loc" == https://* ]]'
api=$(curl -s -m 10 -o /dev/null -w '%{http_code}' -X POST "http://$HOST/api/analyze")
check "HTTP API call is redirected, not answered (got $api)" '[ "$api" = 301 ] || [ "$api" = 308 ]'

# 2. HTTPS works with a valid, trusted certificate
code=$(curl -s -m 15 -o /dev/null -w '%{http_code}' "https://$HOST/")
check "HTTPS page loads with a trusted certificate (got $code)" '[ "$code" = 200 ]'
health=$(curl -s -m 10 "https://$HOST/health")
check "Health check answers ok ($health)" '[[ "$health" == *ok* ]]'

# 3. Security headers
headers=$(curl -s -m 10 -D - -o /dev/null "https://$HOST/" | tr -d '\r')
for h in "strict-transport-security" "content-security-policy" "x-content-type-options: nosniff" "x-frame-options: deny" "referrer-policy"; do
  check "Header present: $h" 'grep -qi "^$h" <<<"$headers"'
done
check "Server version is hidden" '! grep -qiE "^server: .*[0-9]" <<<"$headers"'

# 4. TLS versions and certificate expiry
if command -v openssl >/dev/null; then
  check "TLS 1.2 or 1.3 is offered" 'echo | openssl s_client -connect "$HOST:443" -servername "$HOST" 2>/dev/null | grep -qE "Protocol *: TLSv1\.[23]|TLSv1\.[23],"'
  check "Old TLS 1.0 is refused" '! echo | openssl s_client -connect "$HOST:443" -servername "$HOST" -tls1 2>/dev/null | grep -q "BEGIN CERTIFICATE"'
  end=$(echo | openssl s_client -connect "$HOST:443" -servername "$HOST" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
  if [ -n "$end" ]; then
    days=$(( ( $(date -d "$end" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "$end" +%s) - $(date +%s) ) / 86400 ))
    echo "        certificate expires: $end ($days days left)"
    check "Certificate is valid for more than 1 day" '[ "$days" -gt 1 ]'
  else
    bad "Could not read the certificate"
  fi
fi

# 5. The app server must not be reachable directly from the internet
for port in 8000 5000 5055; do
  check "Port $port is not open to the internet" '! curl -s -m 5 -o /dev/null "http://$HOST:$port/health"'
done

echo; echo "Result: $PASS passed, $FAIL failed."
[ "$FAIL" -eq 0 ]
