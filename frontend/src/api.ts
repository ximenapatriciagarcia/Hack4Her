const BASE = 'http://127.0.0.1:8000'

export type Stats = {
  total_clientes: number; riesgo_alto: number; riesgo_medio: number; riesgo_bajo: number
  pct_riesgo_alto: number; churn_esperado: number; acciones_registradas: number
}
export type ClientRow = {
  customer_id: string; churn_proba: number; riesgo: string
  territory_d: string; comercial_subchannel_d: string; rtm_customer_size_d: string
  tienda?: string; dueno?: string; telefono?: string
}
export type ClientDetail = {
  info: ClientRow
  historial_ventas: { mes: number; transacciones: number; cajas: number }[]
  historial_coolers: { mes: number; coolers: number; puertas: number }[]
}
export type Driver = { feature: string; label: string; importance: number }
export type SegItem = { grupo: string; riesgo_prom: number; n: number }
export type Segmentos = {
  rtm_customer_size_d: SegItem[]; comercial_subchannel_d: SegItem[]; territory_d: SegItem[]
}

async function j<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(BASE + url, opts)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json() as Promise<T>
}

export const getStats = () => j<Stats>('/stats')
export const getClients = (p: { riesgo?: string; limit?: number } = {}) => {
  const q = new URLSearchParams()
  if (p.riesgo) q.set('riesgo', p.riesgo)
  q.set('limit', String(p.limit ?? 25))
  return j<{ clients: ClientRow[] }>(`/clients?${q.toString()}`)
}
export const getClient = (id: string) => j<ClientDetail>(`/client/${id}`)
export const getDrivers = () => j<{ drivers_globales: Driver[] }>('/drivers')
export const getSegmentos = () => j<Segmentos>('/segmentos')
export const getTrend = () => j<{ trend: { mes: number; rate: number }[] }>('/trend')
export const postAction = (a: { customer_id: string; accion: string; notas?: string }) =>
  j<{ ok: boolean; id: number }>('/actions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(a),
  })

export const postAssistant = (message: string) =>
  j<{ reply: string }>('/assistant', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })

export async function fetchTTS(message: string): Promise<string> {
  const r = await fetch(BASE + '/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!r.ok) throw new Error('tts')
  return URL.createObjectURL(await r.blob())
}

export const postWebCall = (customer_id: string) =>
  j<{ access_token: string; call_id: string }>('/retention/webcall', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customer_id }),
  })

export const postPhoneCall = (customer_id: string, to_number: string) =>
  j<{ call_id: string; status: string }>('/retention/phonecall', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customer_id, to_number }),
  })

export const postRetentionLog = (customer_id: string) =>
  j<{ ok: boolean }>('/retention/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customer_id }),
  })

export const getCallResult = (callId: string) =>
  j<{ ready: boolean; summary: string; sentiment: string; status: string; duration_s: number; transcript: string }>(`/retention/result/${callId}`)

// Sigue una llamada telefónica hasta que cuelga; el backend persiste el resultado al estar lista (upsert por call_id).
export async function pollCallResult(callId: string, onDone?: (r: { summary: string; status: string; duration_s: number }) => void) {
  for (let i = 0; i < 18; i++) {
    await new Promise(r => setTimeout(r, 8000))
    try {
      const res = await getCallResult(callId)
      if (res.ready && (res.summary || res.status === 'ended')) { onDone?.(res); return }
    } catch { /* reintenta */ }
  }
}

export type CallLog = {
  customer_id: string; tienda?: string; dueno?: string
  guion: string; resultado: string; duracion_seg: number; created_at: string; call_id?: string
}
export const getCalls = () => j<{ calls: CallLog[] }>('/retention/calls')
// (pollCallResult definido arriba, junto a getCallResult)

export const testConnection = (tech: string) => j<{ ok: boolean; message: string }>(`/settings/test/${tech}`)

export const postDiagnostico = (cid: string) =>
  j<{ diagnostico: string; cached?: boolean; error?: string }>(`/retention/diagnostico/${cid}`, { method: 'POST' })

export type SettingsState = Record<string, { set: boolean; masked: string }>
export const getSettings = () => j<SettingsState>('/settings')
export const postSettings = (s: Record<string, string>) =>
  j<{ ok: boolean }>('/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(s),
  })
