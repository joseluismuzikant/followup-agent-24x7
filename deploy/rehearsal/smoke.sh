#!/usr/bin/env bash
# End-to-end checks against a running rehearsal (rehearsal.sh up first). Each line says what
# it proved; the first failure stops with a non-zero exit.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
export COMPOSE_FILES="compose.prod.yml rehearsal/compose.rehearsal.yml"
export ENV_FILE="rehearsal/.env.rehearsal"
export COMPOSE_PROJECT="inmo24x7-rehearsal"
env_path="$here/.env.rehearsal"
# shellcheck source=SCRIPTDIR/../lib.sh
source "$here/../lib.sh"

[[ -f "$env_path" ]] || {
	echo "Run 'rehearsal.sh up' first." >&2
	exit 1
}
setting() { sed -n "s/^$1=//p" "$env_path" | head -n 1; }
ok() { printf '  ok   %s\n' "$*"; }
fail() {
	printf '  FAIL %s\n' "$*" >&2
	exit 1
}
json() { python3 -c "import json, sys; data = json.load(sys.stdin); print($1)"; }
https() { curl -ksS --max-time 20 "$@"; }
psql_db() { compose exec -T db psql -U postgres -d postgres -Atc "$1"; }

supabase_url="$(setting SUPABASE_URL)"
anon_key="$(setting SUPABASE_ANON_KEY)"
service_key="$(cd "$root" && npx --yes supabase@2 status -o env 2>/dev/null |
	sed -n 's/^SERVICE_ROLE_KEY="\(.*\)"$/\1/p')"
[[ -n "$service_key" ]] || fail "the local Supabase stack is not running"
deployed="$(cat "$DEPLOY_DIR/state-rehearsal/deployed_tag")"
run_id="$(date +%s)"

say "HTTPS, version and headers"
ready="$(https https://api.localhost/health/ready)"
[[ "$(json 'data["commit"]' <<<"$ready")" == "${deployed#sha-}" ]] ||
	fail "/health/ready reports another commit: $ready"
ok "https://api.localhost/health/ready → ${deployed}"
app_headers="$(https -D - -o /dev/null https://app.localhost/)"
grep -qi '^content-security-policy:.*connect.facebook.net' <<<"$app_headers" ||
	fail "the panel has no CSP allowing the Facebook SDK"
grep -qi '^strict-transport-security:' <<<"$app_headers" || fail "no HSTS on the panel"
https https://app.localhost/ | grep -q '<div id="root">' || fail "the panel did not load"
https https://admin.localhost/ | grep -q '<div id="root">' || fail "the backoffice did not load"
ok "panel and backoffice load, with HSTS and the CSP"

say "Database"
[[ "$(psql_db "SELECT count(*) FROM pg_tables t JOIN pg_class c ON c.relname = t.tablename
	JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = t.schemaname
	WHERE t.schemaname = 'public' AND NOT c.relrowsecurity")" == "0" ]] ||
	fail "tables without row level security"
ok "row level security on every table ($(psql_db "SELECT version_num FROM alembic_version"))"

say "Auth with Supabase (JWKS, issuer, confirmed emails)"
new_user() { # email confirmed(true|false) → access token
	https -X POST "$supabase_url/auth/v1/admin/users" -H "apikey: $service_key" \
		-H "Authorization: Bearer $service_key" -H "Content-Type: application/json" \
		-d "{\"email\":\"$1\",\"password\":\"Rehearsal-$run_id!\",\"email_confirm\":$2}" >/dev/null
	https -X POST "$supabase_url/auth/v1/token?grant_type=password" -H "apikey: $anon_key" \
		-H "Content-Type: application/json" \
		-d "{\"email\":\"$1\",\"password\":\"Rehearsal-$run_id!\"}" | json 'data.get("access_token", "")'
}
sign_up() { # token business → the business name the account landed in
	https -X POST https://api.localhost/me/sign-up -H "Authorization: Bearer $1" \
		-H "Content-Type: application/json" \
		-d "{\"business_name\":\"$2\",\"business_type\":\"inmobiliaria\"}" | json 'data["tenant"]["name"]'
}
owner_email="dueno-$run_id@rehearsal.test"
owner="$(new_user "$owner_email" true)"
[[ -n "$owner" ]] || fail "Supabase gave no token"
[[ "$(sign_up "$owner" "Ensayo $run_id")" == "Ensayo $run_id" ]] || fail "sign-up failed"
ok "a Supabase token signs up (ES256 via JWKS, issuer $supabase_url/auth/v1)"
compose run --rm -T api python scripts/make_admin.py "$owner_email" >/dev/null
ok "make_admin.py ran in the API container"

claimed_email="invitada-$run_id@rehearsal.test"
https -X POST https://api.localhost/admin/tenants -H "Authorization: Bearer $owner" \
	-H "Content-Type: application/json" \
	-d "{\"business_name\":\"Alta $run_id\",\"owner_email\":\"$claimed_email\"}" >/dev/null
claimed="$(new_user "$claimed_email" true)"
[[ "$(sign_up "$claimed" "Otro nombre")" == "Alta $run_id" ]] ||
	fail "a confirmed email did not join the business created for it"
ok "a confirmed email joins the business an admin created for it"

unconfirmed_email="sinconfirmar-$run_id@rehearsal.test"
https -X POST https://api.localhost/admin/tenants -H "Authorization: Bearer $owner" \
	-H "Content-Type: application/json" \
	-d "{\"business_name\":\"Reservado $run_id\",\"owner_email\":\"$unconfirmed_email\"}" >/dev/null
unconfirmed="$(new_user "$unconfirmed_email" false)"
if [[ -z "$unconfirmed" ]]; then
	ok "Supabase refuses to sign in an unconfirmed email (the API check is covered by tests)"
elif [[ "$(sign_up "$unconfirmed" "Propio $run_id")" == "Propio $run_id" ]]; then
	ok "an unconfirmed email gets its own business, never the reserved one"
else
	fail "an unconfirmed email joined a business created for it"
fi

say "WhatsApp: signed webhook → worker → agent reply (log sender, fake model)"
tenant_id="$(https https://api.localhost/me -H "Authorization: Bearer $claimed" | json 'data["tenant"]["id"]')"
phone="rehearsal-$run_id"
https -X PUT "https://api.localhost/admin/tenants/$tenant_id/whatsapp" \
	-H "Authorization: Bearer $owner" -H "Content-Type: application/json" \
	-d "{\"phone_number_id\":\"$phone\",\"waba_id\":\"waba-$run_id\",\"access_token\":\"x\",\"sender\":\"log\"}" >/dev/null
body_file="$(mktemp)"
trap 'rm -f "$body_file"' EXIT
signature="$(cd "$root" && META_APP_SECRET="$(setting META_APP_SECRET)" uv run --all-packages python -c "
import os, sys
sys.path.insert(0, 'scripts')
import simulate_whatsapp as s
body = s.encode(s.message_payload('Hola, busco un 2 ambientes', phone_number_id='$phone'))
open('$body_file', 'wb').write(body)
print(s.sign(body, os.environ['META_APP_SECRET']))
")"
status="$(https -o /dev/null -w '%{http_code}' -X POST https://api.localhost/webhooks/whatsapp \
	-H "Content-Type: application/json" -H "X-Hub-Signature-256: $signature" \
	--data-binary "@$body_file")"
[[ "$status" == "200" ]] || fail "the webhook answered $status"
for _ in $(seq 1 30); do
	replies="$(psql_db "SELECT count(*) FROM conversation_messages m
		JOIN conversation_threads t ON t.id = m.thread_id
		WHERE t.tenant_id = '$tenant_id' AND m.author = 'agent'")"
	((replies > 0)) && break
	sleep 1
done
((replies > 0)) || fail "the worker did not answer within 30 s"
sent="$(psql_db "SELECT count(*) FROM whatsapp_outbound WHERE wamid IS NOT NULL")"
ok "the webhook went through Caddy and the worker answered ($replies replies, $sent parts sent)"
bad="$(https -o /dev/null -w '%{http_code}' -X POST https://api.localhost/webhooks/whatsapp \
	-H "Content-Type: application/json" -H "X-Hub-Signature-256: sha256=00" \
	--data-binary "@$body_file")"
[[ "$bad" == "401" ]] || fail "a bad signature got $bad"
ok "a bad signature is refused (401)"

say "Backup and restore"
backup_log="$("$DEPLOY_DIR/backup-now.sh" 2>&1)" || fail "backup failed: $backup_log"
grep -q 'status=ok' <<<"$backup_log" || fail "no status=ok line: $backup_log"
ok "$(grep -o 'status=ok.*' <<<"$backup_log")"
restore_log="$("$DEPLOY_DIR/restore.sh" latest "$here/backup.agekey" 2>&1)" ||
	fail "restore failed: $restore_log"
grep -q '^restore ok' <<<"$restore_log" || fail "restore did not finish: $restore_log"
ok "restored into a scratch database: $(grep -E '^(tenants|leads) ' <<<"$restore_log" | tr '\n' ' ')"

say "Rehearsal passed."
