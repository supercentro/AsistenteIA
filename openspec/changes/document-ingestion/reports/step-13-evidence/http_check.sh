#!/bin/bash
# Group 13.1: HTTP verification with curl against the real API (127.0.0.1:18080).
S="$1"; . "$S/g13.env"; B=http://127.0.0.1:18080/api/v1; F="$S/g13_files"
j() { python -c "import sys,json;d=json.load(sys.stdin);print(d$1)"; }
# req LABEL curl-args... -> prints "LABEL | HTTP status | error code/reason | status"
req() { L="$1"; shift; R=$(curl -s -m 60 -o "$S/g13_body.json" -w '%{http_code}' "$@"); printf '%s | %s | ' "$L" "$R"; python - "$S/g13_body.json" <<'PY'
import json,sys
raw=open(sys.argv[1],'rb').read()
try:
    d=json.loads(raw) if raw else None
except Exception:
    print("non-json body"); sys.exit()
if d is None: print("(empty body)")
elif isinstance(d,dict) and "error" in d:
    e=d["error"]; print("code=%s details=%s msg=%s"%(e.get("code"),e.get("details"),e.get("message")))
elif isinstance(d,dict): print("status=%s error_code=%s chunks=%s"%(d.get("status"),d.get("error_code"),d.get("chunks_count")))
else: print("list of %d"%len(d))
PY
}
login() { curl -s -m 20 -X POST $B/auth/login -H 'content-type: application/json' -d "{\"email\":\"$1\",\"password\":\"$2\"}" | j "['access_token']"; }
T1=$(login docente1@example.com "$TP"); T2=$(login docente2@example.com "$TP")
SP=$(curl -s -X POST $B/subjects -H "authorization: Bearer $T1" -H 'content-type: application/json' -d '{"name":"Verificacion G13","description":"Materia desechable"}' | j "['id']")
curl -s -o /dev/null -X POST $B/auth/register -H 'content-type: application/json' -d '{"name":"Alumna Uno","email":"alumna1@example.com","password":"$STUDENT_A_PW"}'
curl -s -o /dev/null -X POST $B/auth/register -H 'content-type: application/json' -d '{"name":"Alumno Dos","email":"alumno2@example.com","password":"$STUDENT_B_PW"}'
TA=$(login alumna1@example.com "$STUDENT_A_PW"); TB=$(login alumno2@example.com "$STUDENT_B_PW")
curl -s -o /dev/null -w 'enroll alumna1: %{http_code}\n' -X POST $B/subjects/$SP/enrollments -H "authorization: Bearer $T1" -H 'content-type: application/json' -d '{"student_email":"alumna1@example.com"}'
echo "SP=$SP" > "$S/g13.ids"
up() { curl -s -m 60 -o "$S/g13_body.json" -w '%{http_code}' -X POST $B/subjects/$SP/documents -H "authorization: Bearer $1" -F "file=@$F/$2;type=$3"; }
poll() { for i in $(seq 1 120); do st=$(curl -s $B/subjects/$SP/documents -H "authorization: Bearer $T1" | python -c "import sys,json;print({d['id']:d['status'] for d in json.load(sys.stdin)}.get('$1'))"); case "$st" in ready|failed) echo "$st after ~$((i/2))s"; return;; esac; sleep 0.5; done; echo "timeout"; }
echo "=== valid uploads (teacher 1) ==="
for spec in "apuntes.pdf application/pdf" "apuntes.txt text/plain" "apuntes.md text/markdown"; do
  set -- $spec; C=$(up "$T1" $1 $2); ID=$(j "['id']" < "$S/g13_body.json"); ST=$(j "['status']" < "$S/g13_body.json")
  echo "upload $1 | $C | status=$ST | id=$ID"; echo "$1=$ID" >> "$S/g13.ids"; echo "   -> $(poll $ID)"
done
echo "=== list ==="
curl -s $B/subjects/$SP/documents -H "authorization: Bearer $T1" | python -c "import sys,json;[print(' ',d['filename'],d['status'],d['chunks_count'],d['error_code']) for d in json.load(sys.stdin)]"
echo "=== authorization ==="
PDFID=$(grep '^apuntes.pdf=' "$S/g13.ids" | cut -d= -f2)
req "teacher2 upload (not owner)" -X POST $B/subjects/$SP/documents -H "authorization: Bearer $T2" -F "file=@$F/apuntes.txt;type=text/plain"
req "teacher2 list (not owner)" $B/subjects/$SP/documents -H "authorization: Bearer $T2"
req "teacher2 delete (not owner)" -X DELETE $B/subjects/$SP/documents/$PDFID -H "authorization: Bearer $T2"
req "student upload (enrolled)" -X POST $B/subjects/$SP/documents -H "authorization: Bearer $TA" -F "file=@$F/apuntes.txt;type=text/plain"
req "student list (enrolled)" $B/subjects/$SP/documents -H "authorization: Bearer $TA"
req "student delete (enrolled)" -X DELETE $B/subjects/$SP/documents/$PDFID -H "authorization: Bearer $TA"
req "no token upload" -X POST $B/subjects/$SP/documents -F "file=@$F/apuntes.txt;type=text/plain"
req "no token list" $B/subjects/$SP/documents
req "bad token upload" -X POST $B/subjects/$SP/documents -H "authorization: Bearer xxx" -F "file=@$F/apuntes.txt;type=text/plain"
req "unknown subject (teacher1)" -X POST $B/subjects/00000000-0000-4000-8000-000000000000/documents -H "authorization: Bearer $T1" -F "file=@$F/apuntes.txt;type=text/plain"
req "malformed subject id" -X POST $B/subjects/not-a-uuid/documents -H "authorization: Bearer $T1" -F "file=@$F/apuntes.txt;type=text/plain"
req "delete unknown document" -X DELETE $B/subjects/$SP/documents/00000000-0000-4000-8000-000000000000 -H "authorization: Bearer $T1"
echo "=== rejected at upload (teacher 1) ==="
req "exe" -X POST $B/subjects/$SP/documents -H "authorization: Bearer $T1" -F "file=@$F/virus.exe;type=application/octet-stream"
req "pdf with .exe name sent as pdf type" -X POST $B/subjects/$SP/documents -H "authorization: Bearer $T1" -F "file=@$F/virus.exe;filename=falso.pdf;type=application/pdf"
req "oversized 11 MB" -X POST $B/subjects/$SP/documents -H "authorization: Bearer $T1" -F "file=@$F/grande.pdf;type=application/pdf"
req "empty file" -X POST $B/subjects/$SP/documents -H "authorization: Bearer $T1" -F "file=@$F/vacio.txt;type=text/plain"
req "no file part" -X POST $B/subjects/$SP/documents -H "authorization: Bearer $T1" -F "otro=hola"
echo "=== accepted then failed (teacher 1) ==="
for spec in "escaneado.pdf application/pdf" "cifrado.pdf application/pdf" "corrupto.pdf application/pdf"; do
  set -- $spec; C=$(up "$T1" $1 $2); ID=$(j "['id']" < "$S/g13_body.json")
  echo "upload $1 | $C | id=$ID"; echo "$1=$ID" >> "$S/g13.ids"; echo "   -> $(poll $ID)"
  curl -s $B/subjects/$SP/documents -H "authorization: Bearer $T1" | python -c "import sys,json;[print('     ',d['filename'],d['status'],'|',d['error_code'],'|',d['error_message']) for d in json.load(sys.stdin) if d['id']=='$ID']"
done
echo "=== delete (owner) ==="
TXTID=$(grep '^apuntes.txt=' "$S/g13.ids" | cut -d= -f2)
req "owner deletes txt" -X DELETE $B/subjects/$SP/documents/$TXTID -H "authorization: Bearer $T1"
req "owner deletes txt again" -X DELETE $B/subjects/$SP/documents/$TXTID -H "authorization: Bearer $T1"
