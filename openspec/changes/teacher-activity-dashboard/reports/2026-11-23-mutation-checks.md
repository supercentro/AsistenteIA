# Mutation checks (task 2.6)

Date: 2026-11-23. Each row changes one line of the frontend implementation, runs `src/pages/TeacherActivityPage.test.tsx`, `src/hooks/useActivity.test.tsx`, `src/services/activityService.test.ts`, `src/lib/features.test.ts` and `src/tests/copy.test.ts` (stopping at the first failure) and restores the files. The script compares a digest of every non-test source file before and after, so the final tree equals the tested one. Fictitious data only.

| # | Mutation | Result |
|---|---|---|
| 1 | a withheld figure rendered as `0` | killed (`reads «Datos insuficientes» for a withheld figure`) |
| 2 | a query parameter added to the request | killed (`activityService.get asks once ... no query parameter`) |
| 3 | refetch on window focus | killed (`does not ask again when the window regains focus`) |
| 4 | the response kept after leaving (`gcTime` 300000) | killed (`does not keep the response`) |
| 5 | automatic retry of a failure | killed (`does not retry a failure by itself`) |
| 6 | the link moved out of the header | killed (`links from the header ... outside the enrolments`) |
| 7 | bars visible to assistive technology | killed (`hides every bar from assistive technology`) |
| 8 | a judgement word in a label | killed (`uses no judgement word in any label or heading`) |
| 9 | the route registered with the flag off | killed (`with the frontend switch off there is no route`) |
| 10 | a rate of 0% treated as withheld | killed (`shows a rate of 0% as a real figure`) |
| 11 | the flag accepting any value but `false` | killed (`features.test` off for `""`) |
| 12 | a bar drawn for a withheld week | killed (`reads «Datos insuficientes» ... no bar`) |

Twelve of twelve killed, none survived. A first run stopped at mutation 4 because its pattern also matched a comment; the script was corrected and all twelve were run again.
