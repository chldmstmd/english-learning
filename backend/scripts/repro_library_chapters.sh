#!/usr/bin/env bash
# Reproduction / verification for the library-book chapter defects.
# Requires: backend running on :8000, docker db up.
# Usage: bash scripts/repro_library_chapters.sh
set -uo pipefail
cd "$(dirname "$0")/.."

API=http://localhost:8000/api/v1
ADMIN_ID=838d664d-e02a-4adf-ab80-028fcebd02f2
USER_ID=31e1213f-28b0-416f-89f0-5245891e44c5

ADMIN=$(.venv/bin/python -c "from app.services.auth_service import create_access_token; print(create_access_token('$ADMIN_ID'))")
USER=$(.venv/bin/python -c "from app.services.auth_service import create_access_token; print(create_access_token('$USER_ID'))")

# Pick the first library book.
BOOK=$(docker compose -f ../docker-compose.yml exec -T db psql -U postgres -d english_learning -tA \
  -c "select id from books where is_library=true order by created_at limit 1;" 2>/dev/null | tr -d '[:space:]')
echo "library book: $BOOK"

echo "--- admin creates a library chapter ---"
CH=$(curl -s -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d '{"title":"Repro Chapter","raw_text":"The cat sat on the mat. It was warm."}' \
  "$API/admin/library/books/$BOOK/chapters" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "new chapter: $CH"

echo "--- [A] is the new chapter marked is_library? ---"
docker compose -f ../docker-compose.yml exec -T db psql -U postgres -d english_learning -tA \
  -c "select 'is_library='||is_library from articles where id='$CH';" 2>/dev/null | tr -d '[:space:]'; echo

echo "--- [D] admin chapter-list endpoint returns chapters? ---"
curl -s -o /dev/null -w "GET /admin/library/books/{id}/chapters -> %{http_code}\n" \
  -H "Authorization: Bearer $ADMIN" "$API/admin/library/books/$BOOK/chapters"

echo "--- [Read] can a regular user open the new chapter via /library/{id}? ---"
curl -s -o /dev/null -w "user GET /library/{ch} -> %{http_code}\n" \
  -H "Authorization: Bearer $USER" "$API/library/$CH"

echo "--- [B] can the admin add a chapter to the library book via the USER endpoint? (should be blocked) ---"
curl -s -o /dev/null -w "admin POST /books/{id}/chapters -> %{http_code}\n" \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d '{"title":"Sneaky","raw_text":"Should not be allowed."}' \
  "$API/books/$BOOK/chapters"

echo "--- [C] does /books/{id} expose is_library? ---"
curl -s -H "Authorization: Bearer $ADMIN" "$API/books/$BOOK" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('is_library=',d.get('is_library','MISSING'),'is_owner=',d.get('is_owner'))"

echo "--- cleanup: remove the repro chapter(s) ---"
docker compose -f ../docker-compose.yml exec -T db psql -U postgres -d english_learning \
  -c "delete from articles where book_id='$BOOK' and title in ('Repro Chapter','Sneaky');" 2>/dev/null
