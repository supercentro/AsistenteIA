// GENERATED from docs/api-spec.yml by scripts/api-types.mjs. Do not edit by hand.
// Regenerate with `npm run generate:api`.

export interface paths {
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Liveness and database connectivity check */
        get: {
            parameters: {
                query?: never;
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Service is healthy */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": {
                            /** @example ok */
                            status?: string;
                        };
                    };
                };
                /** @description Database is unreachable (code `SERVICE_UNAVAILABLE`; no connection details are exposed) */
                503: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
            };
        };
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Register a new student account
         * @description Public registration always creates role `student`. Teacher accounts are created out of band (seed/CLI command, see development guide) to prevent privilege escalation.
         */
        post: {
            parameters: {
                query?: never;
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody: {
                content: {
                    "application/json": components["schemas"]["RegisterRequest"];
                };
            };
            responses: {
                /** @description User created */
                201: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["User"];
                    };
                };
                409: components["responses"]["Conflict"];
                422: components["responses"]["ValidationError"];
                /** @description Too many registrations from this client address (code `RATE_LIMITED`). Configurable (`REGISTER_RATE_LIMIT`, default 5/minute); counters are in memory per process. */
                429: {
                    headers: {
                        /** @description Seconds until another attempt is allowed */
                        "Retry-After"?: number;
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                500: components["responses"]["InternalError"];
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Obtain an access token */
        post: {
            parameters: {
                query?: never;
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody: {
                content: {
                    "application/json": {
                        /**
                         * Format: email
                         * @description ASCII only; compared in lowercase
                         */
                        email: string;
                        /** Format: password */
                        password: string;
                    };
                };
            };
            responses: {
                /** @description Authenticated */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["TokenResponse"];
                    };
                };
                /** @description Unknown email or wrong password (identical response for both; code `INVALID_CREDENTIALS`) */
                401: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                422: components["responses"]["ValidationError"];
                /** @description Too many login attempts from this client address (code `RATE_LIMITED`). Limit is configurable (`LOGIN_RATE_LIMIT`, default 10/minute); counters are in memory per process. */
                429: {
                    headers: {
                        /** @description Seconds until another attempt is allowed */
                        "Retry-After"?: number;
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                /** @description Database unreachable (code `SERVICE_UNAVAILABLE`; no connection details) */
                503: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
            };
        };
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/users/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Current user profile */
        get: {
            parameters: {
                query?: never;
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Current user */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["User"];
                    };
                };
                401: components["responses"]["Unauthorized"];
            };
        };
        put?: never;
        post?: never;
        /** Delete the account and all associated personal data (right to erasure) */
        delete: {
            parameters: {
                query?: never;
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Account and data deleted */
                204: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content?: never;
                };
                401: components["responses"]["Unauthorized"];
                /** @description A teacher must delete or reassign their subjects first */
                409: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
            };
        };
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/users/me/consent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Record acceptance of the privacy policy */
        post: {
            parameters: {
                query?: never;
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody: {
                content: {
                    "application/json": {
                        /** @example 2026-10-v1 */
                        consent_version: string;
                    };
                };
            };
            responses: {
                /** @description Consent recorded (version and date updated, also on re-acceptance) */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["User"];
                    };
                };
                401: components["responses"]["Unauthorized"];
                /**
                 * @description Validation failed. A version that is not the currently configured policy version returns code
                 *     `INVALID_CONSENT_VERSION` with `details.current_version`; an empty or over-long value returns `VALIDATION_ERROR`.
                 */
                422: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                500: components["responses"]["InternalError"];
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/users/me/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete all of the current student's conversations (right to erasure)
         * @description Role student. Permanent and irreversible.
         */
        delete: {
            parameters: {
                query?: never;
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description All conversations deleted */
                204: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content?: never;
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                500: components["responses"]["InternalError"];
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/subjects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List subjects visible to the caller (teacher - taught subjects; student - enrolled subjects) */
        get: {
            parameters: {
                query?: never;
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Subjects */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Subject"][];
                    };
                };
                401: components["responses"]["Unauthorized"];
            };
        };
        put?: never;
        /** Create a subject (role teacher) */
        post: {
            parameters: {
                query?: never;
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody: {
                content: {
                    "application/json": components["schemas"]["SubjectCreate"];
                };
            };
            responses: {
                /** @description Subject created */
                201: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Subject"];
                    };
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                409: components["responses"]["Conflict"];
                422: components["responses"]["ValidationError"];
                500: components["responses"]["InternalError"];
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/subjects/{subject_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                subject_id: components["parameters"]["SubjectId"];
            };
            cookie?: never;
        };
        /** Get a subject (owner teacher or enrolled student; any other caller gets 404) */
        get: {
            parameters: {
                query?: never;
                header?: never;
                path: {
                    subject_id: components["parameters"]["SubjectId"];
                };
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Subject */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Subject"];
                    };
                };
                401: components["responses"]["Unauthorized"];
                404: components["responses"]["NotFound"];
                422: components["responses"]["ValidationError"];
            };
        };
        put?: never;
        post?: never;
        /** Delete a subject with its documents, chunks, enrollments and conversations (role teacher, owner; another teacher gets 404) */
        delete: {
            parameters: {
                query?: never;
                header?: never;
                path: {
                    subject_id: components["parameters"]["SubjectId"];
                };
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Subject deleted */
                204: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content?: never;
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
                422: components["responses"]["ValidationError"];
                500: components["responses"]["InternalError"];
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/subjects/{subject_id}/enrollments": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                subject_id: components["parameters"]["SubjectId"];
            };
            cookie?: never;
        };
        /** List enrolled students, ordered by creation time (role teacher, owner) */
        get: {
            parameters: {
                query?: never;
                header?: never;
                path: {
                    subject_id: components["parameters"]["SubjectId"];
                };
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Enrollments */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Enrollment"][];
                    };
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
                422: components["responses"]["ValidationError"];
            };
        };
        put?: never;
        /**
         * Enroll a registered student by email (role teacher, owner)
         * @description An email that belongs to no account, or to a teacher, answers the same 404 (no pre-enrollment).
         *     Enrolling a student twice answers 409.
         */
        post: {
            parameters: {
                query?: never;
                header?: never;
                path: {
                    subject_id: components["parameters"]["SubjectId"];
                };
                cookie?: never;
            };
            requestBody: {
                content: {
                    "application/json": {
                        /**
                         * Format: email
                         * @description ASCII only (non-ASCII is rejected with 422); stored and matched in lowercase
                         */
                        student_email: string;
                    };
                };
            };
            responses: {
                /** @description Student enrolled */
                201: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Enrollment"];
                    };
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
                409: components["responses"]["Conflict"];
                422: components["responses"]["ValidationError"];
                500: components["responses"]["InternalError"];
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/subjects/{subject_id}/enrollments/{student_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove a student from a subject (role teacher, owner) */
        delete: {
            parameters: {
                query?: never;
                header?: never;
                path: {
                    subject_id: components["parameters"]["SubjectId"];
                    student_id: string;
                };
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Enrollment removed */
                204: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content?: never;
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
                422: components["responses"]["ValidationError"];
                500: components["responses"]["InternalError"];
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/subjects/{subject_id}/activity": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                subject_id: components["parameters"]["SubjectId"];
            };
            cookie?: never;
        };
        /**
         * Aggregate activity of a subject for its owning teacher (disabled by default)
         * @description Aggregate figures only: numbers, dates and the file names of the documents of the subject. Never
         *     the text of a question or an answer, and never an identifier, name, e-mail or figure of a student.
         *     Only the teacher who owns the subject reads it; another teacher's subject and an unknown subject
         *     answer the same 404, and a student or an anonymous caller is refused (403, 401) before the
         *     capability is looked at.
         *
         *     The capability is switched off by the setting `TEACHER_ACTIVITY_ENABLED` (default `false`): while it
         *     is off a teacher gets 404. It stays off until the privacy text, the legal review and the consent
         *     version are in place.
         *
         *     Rules: a figure that comes from fewer than `minimum_group` (5) distinct students is `null`,
         *     including a figure with no student at all; a subject with fewer than `minimum_group` active
         *     students shows only `enrolled_students`. The window is aligned to whole weeks (Monday to Sunday,
         *     UTC) and covers at most 12 weeks (84 days); `start` and `end` are widened to those weeks and the
         *     response states the window actually computed. Only students currently enrolled count, and only the
         *     data that exists when the request is made (deleting a conversation, or unenrolling a student,
         *     lowers the next result); nothing is stored. `no_material_rate` is the share of answers that stored
         *     no source; `no_cited_source_rate` the share of answers that do not cite any of their sources (it
         *     includes the answers with no material) and is never a measure of quality. `cited_appearances` is
         *     the number of answers that cite the document: it is not semantic support and not proof that the
         *     material was used. Both rates are `null` below the minimum group.
         */
        get: {
            parameters: {
                query?: {
                    /** @description First day of the window (default, 12 weeks ending with the week of `end`) */
                    start?: string;
                    /** @description Last day of the window (default, today in UTC) */
                    end?: string;
                    granularity?: "week";
                };
                header?: never;
                path: {
                    subject_id: components["parameters"]["SubjectId"];
                };
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Aggregate activity */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["ActivityResponse"];
                    };
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
                422: components["responses"]["ValidationError"];
                500: components["responses"]["InternalError"];
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/subjects/{subject_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                subject_id: components["parameters"]["SubjectId"];
            };
            cookie?: never;
        };
        /** List documents of a subject with processing status (owner teacher) */
        get: {
            parameters: {
                query?: never;
                header?: never;
                path: {
                    subject_id: components["parameters"]["SubjectId"];
                };
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Documents */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Document"][];
                    };
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
            };
        };
        put?: never;
        /**
         * Upload course material (owner teacher)
         * @description Accepts PDF, plain text (`.txt`) or Markdown (`.md`) up to `MAX_UPLOAD_MB` (10 MB by default, measured on
         *     the bytes actually received). The type is decided from the extension and the content, never from the
         *     client `Content-Type`; the file name is cleaned (last path component, no control or bidirectional
         *     characters, at most 255 characters).
         *
         *     The `202` is a promise: the document (`status: pending`), its processing job and the uploaded bytes are
         *     committed together before the response is sent. A separate worker then extracts, chunks and embeds the
         *     text; the client polls `GET /subjects/{subject_id}/documents` until the document is `ready` or `failed`.
         *     A failed document carries a stable `error_code` and a fixed `error_message`. The original file is never
         *     kept after processing.
         *
         *     Authentication, role and ownership are decided before the body is read. Errors: `413` as soon as more than
         *     the limit has been received (also without `Content-Length`); `415` for a type that is not allowed or does
         *     not match its content (including invalid UTF-8 or NUL bytes in text); `422` with
         *     `details.reason` = `MALFORMED_MULTIPART`, `FILE_PART_MISSING`, `UNEXPECTED_FIELDS`, `EMPTY_FILE` or
         *     `INVALID_FILENAME`; `408` when a client that stays connected does not send the body in time (nothing can
         *     be promised to a client that has already closed the connection; in that case nothing is stored);
         *     `409` when the subject already holds `MAX_DOCUMENTS_PER_SUBJECT` documents; `429` above the upload rate
         *     limit; `503` when the ingestion queue is full, too many uploads are being received, or the upload cannot be
         *     stored (all with a fixed message).
         */
        post: {
            parameters: {
                query?: never;
                header?: never;
                path: {
                    subject_id: components["parameters"]["SubjectId"];
                };
                cookie?: never;
            };
            requestBody: {
                content: {
                    "multipart/form-data": {
                        /**
                         * Format: binary
                         * @description Exactly one non-empty file part named `file`; no other fields are accepted
                         */
                        file: string;
                    };
                };
            };
            responses: {
                /** @description Upload accepted; the document is durable and `pending` */
                202: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Document"];
                    };
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
                /** @description A client that stayed connected did not send the body in time (error code `REQUEST_TIMEOUT`); nothing was stored */
                408: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                /** @description The subject already holds the maximum number of documents (error code `DOCUMENT_QUOTA_EXCEEDED`) */
                409: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                /** @description File too large (error code `PAYLOAD_TOO_LARGE`) */
                413: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                /** @description Unsupported file type or content that does not match the type (error code `UNSUPPORTED_MEDIA_TYPE`) */
                415: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                /**
                 * @description Invalid multipart request (error code `VALIDATION_ERROR`). `details.reason` is one of
                 *     `MALFORMED_MULTIPART`, `FILE_PART_MISSING`, `UNEXPECTED_FIELDS`, `EMPTY_FILE`, `INVALID_FILENAME`.
                 */
                422: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                /** @description Upload rate limit exceeded (error code `RATE_LIMITED`) */
                429: {
                    headers: {
                        /** @description Seconds to wait before retrying */
                        "Retry-After"?: number;
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                /** @description The ingestion queue is full or too many uploads are in progress (error code `INGESTION_QUEUE_FULL`), or the upload could not be stored (error code `SERVICE_UNAVAILABLE`) */
                503: {
                    headers: {
                        /** @description Seconds to wait before retrying */
                        "Retry-After"?: number;
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
            };
        };
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/subjects/{subject_id}/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete a document and its chunks (owner teacher)
         * @description Also valid while the document is being processed; the job and any temporary bytes are removed with it
         */
        delete: {
            parameters: {
                query?: never;
                header?: never;
                path: {
                    subject_id: components["parameters"]["SubjectId"];
                    document_id: string;
                };
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Document deleted */
                204: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content?: never;
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
                500: components["responses"]["InternalError"];
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/chat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ask the assistant a question about a subject (role student, enrolled, consent recorded)
         * @description Retrieval is restricted to chunks of `subject_id`. If `conversation_id` is given it must belong to the
         *     caller AND to the same `subject_id`. When no chunk reaches the relevance threshold the response has
         *     `no_material=true`, empty `sources`, and the LLM is not called.
         *     A subject that does not exist is 404 and a subject the student is not enrolled in is 403, so a
         *     student can learn whether a subject identifier exists (accepted, TD-061).
         */
        post: {
            parameters: {
                query?: never;
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody: {
                content: {
                    /**
                     * @example {
                     *       "subject_id": "b2c3d4e5-1111-2222-3333-abcdef123456",
                     *       "message": "What is the difference between RAG and fine-tuning?"
                     *     }
                     */
                    "application/json": {
                        /** Format: uuid */
                        subject_id: string;
                        /** Format: uuid */
                        conversation_id?: string | null;
                        message: string;
                    };
                };
            };
            responses: {
                /** @description Assistant answer */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["ChatResponse"];
                    };
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
                422: components["responses"]["ValidationError"];
                /** @description Chat rate limit exceeded (error code `RATE_LIMITED`) */
                429: {
                    headers: {
                        /** @description Seconds to wait before retrying */
                        "Retry-After"?: number;
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                500: components["responses"]["InternalError"];
                /** @description LLM provider failed or blocked the answer (retryable) */
                502: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List the caller's conversations, optionally filtered by subject (role student) */
        get: {
            parameters: {
                query?: {
                    subject_id?: string;
                };
                header?: never;
                path?: never;
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Conversations */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Conversation"][];
                    };
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
            };
        };
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/conversations/{conversation_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Messages of one of the caller's conversations, with sources */
        get: {
            parameters: {
                query?: never;
                header?: never;
                path: {
                    conversation_id: components["parameters"]["ConversationId"];
                };
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Messages ordered by creation time */
                200: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Message"][];
                    };
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
            };
        };
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Permanently delete one of the caller's conversations and its messages */
        delete: {
            parameters: {
                query?: never;
                header?: never;
                path: {
                    conversation_id: components["parameters"]["ConversationId"];
                };
                cookie?: never;
            };
            requestBody?: never;
            responses: {
                /** @description Conversation deleted */
                204: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content?: never;
                };
                401: components["responses"]["Unauthorized"];
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
                500: components["responses"]["InternalError"];
                503: components["responses"]["ServiceUnavailable"];
            };
        };
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        Error: {
            /**
             * @description Stable machine-readable code. Generic codes: UNAUTHORIZED, FORBIDDEN, NOT_FOUND, METHOD_NOT_ALLOWED,
             *     CONFLICT, VALIDATION_ERROR, INTERNAL_ERROR, SERVICE_UNAVAILABLE. Authentication adds INVALID_CREDENTIALS,
             *     RATE_LIMITED and INVALID_CONSENT_VERSION. Feature changes add their own (e.g. CONSENT_REQUIRED, LLM_UNAVAILABLE).
             *     Document upload adds PAYLOAD_TOO_LARGE (413), UNSUPPORTED_MEDIA_TYPE (415), REQUEST_TIMEOUT (408),
             *     DOCUMENT_QUOTA_EXCEEDED (409) and INGESTION_QUEUE_FULL (503); its 422 keeps VALIDATION_ERROR and puts a
             *     fixed reason in `details.reason`. The failure codes of a document (`Document.error_code`) are a separate,
             *     closed list.
             * @example CONSENT_REQUIRED
             */
            code: string;
            message: string;
            details?: {
                [key: string]: unknown;
            } | null;
        };
        RegisterRequest: {
            name: string;
            /**
             * Format: email
             * @description ASCII only (non-ASCII is rejected with 422; use punycode for internationalised domains); stored in lowercase
             */
            email: string;
            /** Format: password */
            password: string;
        };
        TokenResponse: {
            access_token: string;
            /** @example bearer */
            token_type: string;
            /** @description Seconds */
            expires_in: number;
        };
        User: {
            /** Format: uuid */
            id: string;
            name: string;
            /** Format: email */
            email: string;
            /** @enum {string} */
            role: "teacher" | "student";
            consent_version: string | null;
            /** Format: date-time */
            consent_accepted_at: string | null;
        };
        SubjectCreate: {
            /** @description Trimmed single-line text without control or direction characters; unique per teacher (case-sensitive) */
            name: string;
            /** @description Plain text */
            description?: string | null;
        };
        Subject: components["schemas"]["SubjectCreate"] & {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            teacher_id: string;
            /** Format: date-time */
            created_at: string;
        };
        Enrollment: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            subject_id: string;
            /** Format: uuid */
            student_id: string;
            /** Format: email */
            student_email: string;
            /** Format: date-time */
            created_at: string;
        };
        Document: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            subject_id: string;
            /** @description Cleaned file name (never used as a path) */
            filename: string;
            /** @description Decided from the content: application/pdf, text/plain or text/markdown */
            content_type: string;
            /** @description Number of bytes received */
            size_bytes: number;
            /**
             * @description `pending` and `processing` until a worker finishes; `ready` (searchable, with chunks) or `failed` (final)
             * @enum {string}
             */
            status: "pending" | "processing" | "ready" | "failed";
            /**
             * @description Stable reason of a `failed` document; null otherwise. Clients translate by code and must not depend on `error_message`. The list is closed; adding a code is a contract change.
             * @enum {string|null}
             */
            error_code?: "NO_EXTRACTABLE_TEXT" | "ENCRYPTED_PDF" | "CORRUPT_FILE" | "TOO_MANY_PAGES" | "TEXT_TOO_LARGE" | "TOO_MANY_CHUNKS" | "PROCESSING_TIMEOUT" | "RESOURCE_LIMIT_EXCEEDED" | "EMBEDDING_FAILED" | "PROCESSING_INTERRUPTED" | "JOB_EXPIRED" | "PROCESSING_FAILED" | null;
            /** @description Fixed English sentence per `error_code`; never contains parser */
            error_message?: string | null;
            chunks_count: number;
            /** Format: date-time */
            created_at: string;
        };
        /**
         * @description Citation of a chunk used for an answer: the chunks whose `[n]` marker the answer contains (a list such as `[1, 2]` or adjacent markers `[1][2]` cite each rank; a range such as `[1-3]` cites none), with
         *     `rank` the retrieval rank of the chunk (ranks can have gaps). An answer with no valid marker lists
         *     every retrieved chunk of its context.
         */
        Source: {
            /** Format: uuid */
            chunk_id?: string | null;
            /** Format: uuid */
            document_id?: string | null;
            filename?: string;
            page_number?: number | null;
            rank?: number;
            /** @description Short excerpt of the chunk */
            snippet?: string;
        };
        /**
         * @example {
         *       "conversation_id": "9a8b7c6d-4444-5555-6666-abcdef123456",
         *       "message_id": "1f2e3d4c-7777-8888-9999-abcdef123456",
         *       "answer": "According to unit 1, RAG retrieves context at query time without changing model weights...",
         *       "no_material": false,
         *       "sources": [
         *         {
         *           "chunk_id": "3f1a9c2e-1234-4a5b-8c9d-abcdef123456",
         *           "document_id": "7c6b5a49-0000-1111-2222-abcdef123456",
         *           "filename": "unit1-introduction.pdf",
         *           "page_number": 4,
         *           "rank": 1,
         *           "snippet": "RAG combines retrieval with generation..."
         *         }
         *       ]
         *     }
         */
        ChatResponse: {
            /** Format: uuid */
            conversation_id: string;
            /** Format: uuid */
            message_id: string;
            answer: string;
            no_material: boolean;
            sources: components["schemas"]["Source"][];
            /**
             * @description Whether the sources were cited by the answer (`cited`: they are the chunks whose valid marker the answer contains) or are only the retrieved chunks because the answer holds no valid marker (`retrieved`). Null when there are no sources. It says nothing about whether a source supports a statement. Optional: clients that do not know it still receive the same `sources`.
             * @enum {string|null}
             */
            attribution?: "cited" | "retrieved" | null;
        };
        ActivityWindow: {
            /**
             * Format: date
             * @description Monday of the first week
             */
            start: string;
            /**
             * Format: date
             * @description Sunday of the last week
             */
            end: string;
            /** @enum {string} */
            granularity: "week";
            weeks: number;
        };
        ActivityPeriod: {
            /**
             * Format: date
             * @description Monday of the week
             */
            period_start: string;
            /** @description Questions of the week; null when fewer than the minimum group of students asked */
            count: number | null;
        };
        ActivityDocument: {
            /**
             * Format: uuid
             * @description Null once the document was deleted
             */
            document_id: string | null;
            filename: string;
            /** @description Answers that cite the document (not semantic support, not proof that the material was used); null below the minimum group of students */
            cited_appearances: number | null;
        };
        ActivityResponse: {
            window: components["schemas"]["ActivityWindow"];
            /** @description Fewest distinct students behind a figure that is shown (5) */
            minimum_group: number;
            enrolled_students: number;
            /** @description Distinct students who asked in the window; null below the minimum group */
            active_students: number | null;
            questions: components["schemas"]["ActivityPeriod"][];
            /** @description Share of answers that stored no source; null below the minimum group */
            no_material_rate: number | null;
            /** @description Share of answers that cite none of their sources, including the answers with no material; null below the minimum group */
            no_cited_source_rate: number | null;
            documents: components["schemas"]["ActivityDocument"][];
            /** @description True when at least one figure is null */
            suppressed: boolean;
        };
        Conversation: {
            /** Format: uuid */
            id?: string;
            /** Format: uuid */
            subject_id?: string;
            /** Format: date-time */
            created_at?: string;
            last_message_preview?: string | null;
        };
        Message: {
            /** Format: uuid */
            id?: string;
            /** @enum {string} */
            role?: "user" | "assistant";
            content?: string;
            /** Format: date-time */
            created_at?: string;
            sources?: components["schemas"]["Source"][];
            /**
             * @description Whether the sources were cited by the answer (`cited`: they are the chunks whose valid marker the answer contains) or are only the retrieved chunks because the answer holds no valid marker (`retrieved`). Null when there are no sources. It says nothing about whether a source supports a statement. Optional: clients that do not know it still receive the same `sources`.
             * @enum {string|null}
             */
            attribution?: "cited" | "retrieved" | null;
        };
    };
    responses: {
        /** @description Missing or invalid token */
        Unauthorized: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Authenticated but not allowed (wrong role; for chat also not enrolled or consent missing) */
        Forbidden: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Resource does not exist or is not visible to the caller (including another user's resources); the body is identical in both cases */
        NotFound: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Resource already exists or state conflict */
        Conflict: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description Request validation failed */
        ValidationError: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /**
         * @description Unexpected server error (code `INTERNAL_ERROR`, no details). When the cause is a write that the
         *     database refused at commit, the transaction was rolled back and nothing was stored or removed.
         *     An error raised after a successful commit is reported the same way, so a client that must be
         *     sure reads the resource before it repeats a request that is not idempotent.
         */
        InternalError: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /**
         * @description The database could not be reached or the connection was lost (code `SERVICE_UNAVAILABLE`, no details,
         *     no connection data). When the connection was lost while the write was being committed, the outcome is
         *     uncertain: the change may or may not be stored, so read the resource before repeating the request
         *     (a creation that was in fact stored answers 409 when it is repeated).
         */
        ServiceUnavailable: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
    };
    parameters: {
        SubjectId: string;
        ConversationId: string;
    };
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export type operations = Record<string, never>;
