const BASE = '/api'

export interface StatusResponse {
  current: string | null
  queue: string[]
  running: boolean
  path: string
}

export interface LogsResponse {
  lines: string[]
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  const text = await res.text()
  let data: any = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      // Non-JSON body (e.g. backend down / proxy error page).
      throw new Error(`Risposta non valida dal server (${res.status}). Il backend (server.py) e' avviato?`)
    }
  }

  if (!res.ok) {
    throw new Error(data?.error || `Richiesta fallita (${res.status})`)
  }
  return data as T
}

export function fetchStatus() {
  return request<StatusResponse>('/status')
}

export function addToQueue(url: string) {
  return request<{ ok: boolean }>('/queue', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

export function fetchConfig() {
  return request<{ path: string }>('/config')
}

export function saveConfig(path: string) {
  return request<{ ok: boolean; path: string }>('/config', {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
}

export function fetchLogs(lines = 300) {
  return request<LogsResponse>(`/logs?lines=${lines}`)
}
