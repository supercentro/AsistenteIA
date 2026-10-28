# Step 7 Report - Manual Endpoint Testing with curl

- Date: 2026-10-28
- Change: subjects-and-enrollments
- Agent: Claude Code (Sonnet 5.5) - executed by the agent against the live compose stack

## Environment
- `docker compose up -d --build backend` (the image now includes migration `0003`; `alembic current` in the container: `0003 (head)`), health `{"status":"ok"}`, API on `http://127.0.0.1:8000/api/v1`.
- Accounts created for the test: two teachers through the CLI (`create-teacher --password-stdin`) and two students through `POST /auth/register`; all with the email suffix `.curl@example.com`. Tokens obtained with `POST /auth/login`.
- Script: `curl_run.sh` kept in the session scratchpad; output below (timestamps replaced by `<ts>`).

## Commands and responses (format: `[status] label :: body`)
```
== setup
Created teacher id=34295cc6-ac66-40c1-94bd-fffa2e1d41be email=t1.curl@example.com
Created teacher id=bec81e09-c1be-4068-96b0-b76a8b81b2f2 email=t2.curl@example.com
register s1 201
register s2 201
== subjects
[201] teacher creates (201) :: {"id":"81ce71a1-e3e5-4bee-9d6b-3d13f3d5006f","name":"Algebra","description":"Linear algebra","teacher_id":"34295cc6-ac66-40c1-94bd-fffa2e1d41be","<ts>"}
subject id: 81ce71a1-e3e5-4bee-9d6b-3d13f3d5006f
[409] duplicate name (409) :: {"code":"CONFLICT","message":"You already have a subject with this name"}
[422] invalid name blank (422) :: {"code":"VALIDATION_ERROR","message":"Request validation failed","details":{"errors":[{"field":"body.name","message":"String should have at least 1 character"}]}}
[422] NUL in name (422) :: {"code":"VALIDATION_ERROR","message":"Request validation failed","details":{"errors":[{"field":"body.name","message":"Value error, contains control or direction characters"}]}}
[403] student creates (403) :: {"code":"FORBIDDEN","message":"You do not have permission to perform this action"}
[401] no token create (401) :: {"code":"UNAUTHORIZED","message":"Invalid or expired token"}
[200] teacher lists :: [{"id":"81ce71a1-e3e5-4bee-9d6b-3d13f3d5006f","name":"Algebra","description":"Linear algebra","teacher_id":"34295cc6-ac66-40c1-94bd-fffa2e1d41be","<ts>"}]
[200] other teacher lists (empty) :: []
[200] student lists before enrollment (empty) :: []
[200] get as owner (200) :: {"id":"81ce71a1-e3e5-4bee-9d6b-3d13f3d5006f","name":"Algebra","description":"Linear algebra","teacher_id":"34295cc6-ac66-40c1-94bd-fffa2e1d41be","<ts>"}
[404] get as other teacher (404) :: {"code":"NOT_FOUND","message":"Subject not found"}
[404] get as non-enrolled student (404) :: {"code":"NOT_FOUND","message":"Subject not found"}
[404] get missing id (404, same body) :: {"code":"NOT_FOUND","message":"Subject not found"}
[422] get malformed id (422) :: {"code":"VALIDATION_ERROR","message":"Request validation failed","details":{"errors":[{"field":"path.subject_id","message":"Input should be a valid UUID, invalid character: found `n` at 0"}]}}
== enrollments
[201] enroll s1 (201) :: {"id":"73f632d6-b680-4676-bb60-13e4eb183546","subject_id":"81ce71a1-e3e5-4bee-9d6b-3d13f3d5006f","student_id":"7297cc00-809c-4717-8092-195cc3af5897","student_email":"s1.curl@example.com","<ts>"}
[409] duplicate (409) :: {"code":"CONFLICT","message":"Student is already enrolled in this subject"}
[404] unknown email (404) :: {"code":"NOT_FOUND","message":"Student not found"}
[404] teacher email (404 identical) :: {"code":"NOT_FOUND","message":"Student not found"}
[422] invalid email (422) :: {"code":"VALIDATION_ERROR","message":"Request validation failed","details":{"errors":[{"field":"body.student_email","message":"Value error, value is not a valid email address"}]}}
[403] student role enroll (403) :: {"code":"FORBIDDEN","message":"You do not have permission to perform this action"}
[404] other teacher enroll (404) :: {"code":"NOT_FOUND","message":"Subject not found"}
[200] list as owner :: [{"id":"73f632d6-b680-4676-bb60-13e4eb183546","subject_id":"81ce71a1-e3e5-4bee-9d6b-3d13f3d5006f","student_id":"7297cc00-809c-4717-8092-195cc3af5897","student_email":"s1.curl@example.com","<ts>"}]
[403] list as student (403) :: {"code":"FORBIDDEN","message":"You do not have permission to perform this action"}
[404] list as other teacher (404) :: {"code":"NOT_FOUND","message":"Subject not found"}
[200] student sees subject now (200) :: {"id":"81ce71a1-e3e5-4bee-9d6b-3d13f3d5006f","name":"Algebra","description":"Linear algebra","teacher_id":"34295cc6-ac66-40c1-94bd-fffa2e1d41be","<ts>"}
[200] student lists subjects (1) :: [{"id":"81ce71a1-e3e5-4bee-9d6b-3d13f3d5006f","name":"Algebra","description":"Linear algebra","teacher_id":"34295cc6-ac66-40c1-94bd-fffa2e1d41be","<ts>"}]
[422] malformed student id in path (422, label of the script said 404) :: {"code":"VALIDATION_ERROR","message":"Request validation failed","details":{"errors":[{"field":"path.student_id","message":"Input should be a valid UUID, invalid character: found `.` at 36"}]}}
[404] remove random student (404) :: {"code":"NOT_FOUND","message":"Enrollment not found"}
[404] other teacher removes (404) :: {"code":"NOT_FOUND","message":"Subject not found"}
[204] owner removes (204) :: 
[404] student lost access (404) :: {"code":"NOT_FOUND","message":"Subject not found"}
== delete subject
[201] re-enroll s2 for cascade :: {"id":"6f9afe22-eead-45ee-89b2-f493ca09320b","subject_id":"81ce71a1-e3e5-4bee-9d6b-3d13f3d5006f","student_id":"a839ccb2-6e45-4201-b736-cdbb69769438","student_email":"s2.curl@example.com","<ts>"}
[403] student deletes (403) :: {"code":"FORBIDDEN","message":"You do not have permission to perform this action"}
[404] other teacher deletes (404) :: {"code":"NOT_FOUND","message":"Subject not found"}
[204] owner deletes (204) :: 
[404] delete again (404) :: {"code":"NOT_FOUND","message":"Subject not found"}
== cleanup
DELETE 4
0|0|0
```

## Verification
- Every status matches the specs: 201/409/422/403/401 for creation, identical 404 bodies for missing and inaccessible subjects, the same 404 for unknown and teacher emails, 403 for students on every teacher operation, 204 on removal and deletion, and 404 on repeating them.
- The extra `.nope` suffix on the first "remove" request was a typo of the script (it checks a malformed student id: 422); the missing enrollment case is the next line (404 `Enrollment not found`).
- Cleanup: `delete from users where email like '%.curl@example.com'` removed 4 rows (subjects and enrollments had been deleted through the API / cascade). Final counts users | subjects | enrollments = `0|0|0`, equal to the pre-test state.

## Outcome
- Step 7 status: PASS
