import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { startSession } from '../lib/session'
import { activity } from '../tests/activity'
import { API, TOKEN_VALUE } from '../tests/api'
import { server } from '../tests/server'
import { activityService } from './activityService'

const ID = '33333333-3333-4333-8333-333333333333'

describe('activityService.get', () => {
  beforeEach(() => {
    startSession(TOKEN_VALUE, 3600)
  })

  it('asks once for the subject with no query parameter and returns the body as received', async () => {
    const urls: string[] = []
    server.use(
      http.get(`${API}/subjects/${ID}/activity`, ({ request }) => {
        urls.push(request.url)
        return HttpResponse.json(activity())
      }),
    )

    const body = await activityService.get(ID)

    expect(urls).toEqual([`${API}/subjects/${ID}/activity`])
    expect(body).toEqual(activity())
  })

  it('encodes the subject identifier in the path', async () => {
    server.use(http.get(`${API}/subjects/a%2Fb/activity`, () => HttpResponse.json(activity())))

    await expect(activityService.get('a/b')).resolves.toBeTruthy()
  })
})
