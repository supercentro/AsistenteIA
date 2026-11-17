"""End-to-end check run INSIDE the isolated backend container (plain urllib, no extra packages).

The LLM is the fake backend (no Gemini call); the embedder is the real local model and the worker is
the real worker, so ingestion and retrieval use real embeddings.
"""

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"
TEACHER = ("round4.teacher@example.com", sys.argv[1])
STUDENT = ("round4.student@example.com", "a-student-password-123")


def call(method, path, token=None, body=None, raw=None, content_type="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", content_type)
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
            return response.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as error:
        payload = error.read()
        return error.code, (json.loads(payload) if payload else None)


def login(email, password):
    status, body = call("POST", "/auth/login", body={"email": email, "password": password})
    assert status == 200, (status, body)
    return body["access_token"]


def check(label, condition, detail=""):
    print(("PASS " if condition else "FAIL ") + label + (f" -> {detail}" if detail else ""), flush=True)
    if not condition:
        raise SystemExit(1)


status, body = call("GET", "/health")
check("GET /health", status == 200, body)

teacher = login(*TEACHER)
status, subject = call("POST", "/subjects", teacher, {"name": "Calculo"})
check("teacher creates a subject", status == 201, status)
subject_id = subject["id"]

status, body = call("POST", "/auth/register", body={"name": "Round Four", "email": STUDENT[0], "password": STUDENT[1]})
check("student registers", status == 201, status)
student = login(*STUDENT)
status, body = call("POST", f"/subjects/{subject_id}/enrollments", teacher, {"student_email": STUDENT[0]})
check("teacher enrols the student", status == 201, status)

status, body = call("POST", "/chat", student, {"subject_id": subject_id, "message": "hola"})
check("chat without consent is 403 CONSENT_REQUIRED", status == 403 and body["code"] == "CONSENT_REQUIRED", (status, body))
status, body = call("POST", "/users/me/consent", student, {"consent_version": "2026-10-v1"})
check("student gives the current consent", status == 200, status)

text = (
    "La derivada de una funcion mide su tasa de cambio instantanea. "
    "El limite del cociente incremental cuando h tiende a cero define la derivada en un punto. "
    "La integral definida calcula el area bajo una curva."
).encode()
boundary = "----round4boundary"
multipart = (
    f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"derivadas.txt\"\r\n"
    "Content-Type: text/plain\r\n\r\n"
).encode() + text + f"\r\n--{boundary}--\r\n".encode()
status, document = call("POST", f"/subjects/{subject_id}/documents", teacher, raw=multipart, content_type=f"multipart/form-data; boundary={boundary}")
check("teacher uploads a document (202)", status == 202, (status, document))

deadline = time.time() + 240
state = None
while time.time() < deadline:
    status, listed = call("GET", f"/subjects/{subject_id}/documents", teacher)
    state = listed[0]["status"] if status == 200 and listed else None
    if state in ("ready", "failed"):
        break
    time.sleep(3)
check("the real worker ingests it with real embeddings (ready)", state == "ready", state)

status, answer = call("POST", "/chat", student, {"subject_id": subject_id, "message": "Que es la derivada de una funcion?"})
check("chat on the material is 200 with sources", status == 200 and not answer["no_material"] and answer["sources"], (status, answer.get("no_material"), len(answer.get("sources", []))))
source = answer["sources"][0]
check("source follows the canonical contract", set(source) == {"chunk_id", "document_id", "filename", "page_number", "rank", "snippet"} and source["filename"] == "derivadas.txt", source["filename"])
conversation = answer["conversation_id"]

status, off_topic = call("POST", "/chat", student, {"subject_id": subject_id, "message": "Receta de pizza napolitana con masa madre"})
print("INFO off-topic question: status", status, "no_material", off_topic and off_topic.get("no_material"))

status, follow = call("POST", "/chat", student, {"subject_id": subject_id, "conversation_id": conversation, "message": "Y la integral?"})
check("follow-up in the same conversation", status == 200 and follow["conversation_id"] == conversation, status)

status, history = call("GET", f"/conversations/{conversation}/messages", student)
check("history has 4 messages with sources on answers", status == 200 and len(history) == 4 and any(m["sources"] for m in history), (status, len(history or [])))

status, listing = call("GET", "/conversations", student)
check("conversation list shows it", status == 200 and any(c["id"] == conversation for c in listing), status)

student_id = call("GET", "/users/me", student)[1]["id"]
status, body = call("DELETE", f"/subjects/{subject_id}/enrollments/{student_id}", teacher)
check("teacher unenrols the student", status == 204, status)
status, listing = call("GET", "/conversations", student)
check("unenrolled student no longer sees the conversation", status == 200 and not any(c["id"] == conversation for c in listing), listing)
status, body = call("GET", f"/conversations/{conversation}/messages", student)
check("unenrolled student gets 404 for the messages", status == 404, status)
status, body = call("POST", "/chat", student, {"subject_id": subject_id, "message": "hola"})
check("unenrolled student gets 403 on chat", status == 403, status)
status, body = call("DELETE", f"/conversations/{conversation}", student)
check("unenrolled student can still erase the conversation", status == 204, status)
print("E2E DONE")
