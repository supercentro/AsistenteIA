import { apiClient } from '../lib/apiClient'
import type { ActivityResponse } from '../types/api'

export const activityService = {
  /** One request for the window the API chooses: no date, granularity or any other parameter. */
  async get(subjectId: string): Promise<ActivityResponse> {
    const { data } = await apiClient.get<ActivityResponse>(
      `/subjects/${encodeURIComponent(subjectId)}/activity`,
    )
    return data
  },
}
