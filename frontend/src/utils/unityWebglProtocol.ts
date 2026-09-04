export type UnityWindowMessage = {
  type: string
  requestId?: string
  timestamp?: number
  payload?: Record<string, unknown>
}

export function parseUnityWindowMessage(data: unknown): UnityWindowMessage | null {
  if (!data) return null
  if (typeof data === 'string') {
    try {
      return JSON.parse(data) as UnityWindowMessage
    } catch {
      return { type: 'raw', payload: { value: data } }
    }
  }
  if (typeof data !== 'object') return null
  const candidate = data as {
    source?: string
    message?: UnityWindowMessage
    type?: string
    requestId?: string
    timestamp?: number
    payload?: Record<string, unknown>
  }
  if (candidate.source === 'unity-webgl' && candidate.message) return candidate.message
  if (!candidate.type) return null
  return {
    type: candidate.type,
    requestId: candidate.requestId,
    timestamp: candidate.timestamp,
    payload: candidate.payload,
  }
}

export function appendUnityRuntimeParams(
  source: string,
  params: Record<string, string | number | null | undefined>,
) {
  const separator = source.includes('?') ? '&' : '?'
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  return `${source}${separator}${query.toString()}`
}

export function cloneUnityPayload(payload: Record<string, unknown> = {}) {
  return JSON.parse(JSON.stringify(payload)) as Record<string, unknown>
}
