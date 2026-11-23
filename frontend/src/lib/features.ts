/**
 * Build-time switch of the teacher activity page (change `teacher-activity-dashboard`).
 *
 * It only hides the entry point: it is public and is not a security control, because the backend
 * (`TEACHER_ACTIVITY_ENABLED`) decides. Anything but the exact value `true` keeps it off.
 */
export function teacherActivityEnabled(): boolean {
  return import.meta.env.VITE_TEACHER_ACTIVITY_ENABLED === 'true'
}
