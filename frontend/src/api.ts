const BASE = 'http://127.0.0.1:8000'

export type Stats = {
  total_clientes: number; riesgo_alto: number; riesgo_medio: number; riesgo_bajo: number
  pct_riesgo_alto: number; churn_esperado: number; acciones_registradas: number
}
export type ClientRow = {
  customer_id: string; churn_proba: number; riesgo: string
  territory_d: string; comercial_subchannel_d: string; rtm_customer_size_d: string
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
export const postAction = (a: { customer_id: string; accion: string; notas?: string }) =>
  j<{ ok: boolean; id: number }>('/actions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(a),
  })

export type SettingsState = Record<string, { set: boolean; masked: string }>
export const getSettings = () => j<SettingsState>('/settings')
export const postSettings = (s: Record<string, string>) =>
  j<{ ok: boolean }>('/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(s),
  })
