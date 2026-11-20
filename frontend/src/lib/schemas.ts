import { z } from 'zod'
import { strings } from './strings.es'

/**
 * Client-side validation that mirrors the limits of docs/api-spec.yml without being stricter or
 * looser: the server stays the authority and a 422 is still handled. Passwords are never trimmed.
 */
const { validation } = strings.auth

const MAX_EMAIL_LENGTH = 255
const MAX_NAME_LENGTH = 100
const MIN_REGISTER_PASSWORD_LENGTH = 10
const MAX_PASSWORD_LENGTH = 128

const isAscii = (value: string) => Array.from(value).every((ch) => (ch.codePointAt(0) ?? 0) < 128)
const looksLikeEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)

const email = z
  .string()
  .trim()
  .min(1, validation.required)
  .refine(isAscii, validation.emailAscii)
  .refine((value) => value.length <= MAX_EMAIL_LENGTH, validation.emailTooLong)
  .refine(looksLikeEmail, validation.emailInvalid)

export const loginSchema = z.object({
  email,
  password: z
    .string()
    .min(1, validation.required)
    .max(MAX_PASSWORD_LENGTH, validation.passwordTooLong),
})

export const registerSchema = z.object({
  name: z.string().trim().min(1, validation.required).max(MAX_NAME_LENGTH, validation.nameTooLong),
  email,
  password: z
    .string()
    .min(1, validation.required)
    .min(MIN_REGISTER_PASSWORD_LENGTH, validation.passwordTooShort)
    .max(MAX_PASSWORD_LENGTH, validation.passwordTooLong),
})

const MAX_SUBJECT_NAME_LENGTH = 150
const MAX_SUBJECT_DESCRIPTION_LENGTH = 2000
const { validation: subjectValidation } = strings.subjects.create

/** Mirrors POST /subjects without being stricter: control characters are left to the server. */
export const subjectSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, subjectValidation.nameRequired)
    .max(MAX_SUBJECT_NAME_LENGTH, subjectValidation.nameTooLong),
  description: z
    .string()
    .trim()
    .max(MAX_SUBJECT_DESCRIPTION_LENGTH, subjectValidation.descriptionTooLong),
})

/** The e-mail of a student to enroll: exactly the rule of the registration e-mail. */
export const enrollmentSchema = z.object({ studentEmail: email })

const MAX_QUESTION_LENGTH = 2000
const { box: questionMessages } = strings.chat

/** Mirrors POST /chat (1 to 2000 characters) without being stricter. */
export const questionSchema = z.object({
  message: z
    .string()
    .trim()
    .min(1, questionMessages.required)
    .max(MAX_QUESTION_LENGTH, questionMessages.tooLong),
})

export type LoginValues = z.infer<typeof loginSchema>
export type RegisterValues = z.infer<typeof registerSchema>
export type SubjectValues = z.infer<typeof subjectSchema>
export type EnrollmentValues = z.infer<typeof enrollmentSchema>
export type QuestionValues = z.infer<typeof questionSchema>
