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
            };
        };
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
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
            };
        };
        put?: never;
        /**
         * Upload course material (owner teacher)
         * @description Accepts PDF, plain text or Markdown up to `MAX_UPLOAD_MB`. Processing (extraction, chunking, embeddings)
         *     runs in a background task; the document is returned with `status` pending/processing and the client polls
         *     `GET /subjects/{subject_id}/documents`. Unsupported type -> 415; too large -> 413; PDF without extractable
         *     text -> document ends in `failed` with a clear `error_message`.
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
                        /** Format: binary */
                        file: string;
                    };
                };
            };
            responses: {
                /** @description Upload accepted, processing started */
                202: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Document"];
                    };
                };
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
                /** @description File too large */
                413: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                /** @description Unsupported file type */
                415: {
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
        /** Delete a document and its chunks (owner teacher) */
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
                403: components["responses"]["Forbidden"];
                404: components["responses"]["NotFound"];
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
                /** @description Rate limit exceeded */
                429: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                /** @description LLM provider failed or blocked the answer (retryable) */
                502: {
                    headers: {
                        [name: string]: unknown;
                    };
                    content: {
                        "application/json": components["schemas"]["Error"];
                    };
                };
                /** @description Vector search unavailable */
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
                404: components["responses"]["NotFound"];
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
            id?: string;
            /** Format: uuid */
            subject_id?: string;
            filename?: string;
            content_type?: string;
            size_bytes?: number;
            /** @enum {string} */
            status?: "pending" | "processing" | "ready" | "failed";
            error_message?: string | null;
            chunks_count?: number;
            /** Format: date-time */
            created_at?: string;
        };
        /** @description Citation of a chunk used for an answer */
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
