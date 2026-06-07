import { useEffect, useState, useCallback, useRef } from 'react'
import { sileo } from 'sileo'
import { RetellWebClient } from 'retell-client-js-sdk'
import {
  getStats, getClients, getClient, getDrivers, getSegmentos, getTrend, postAction,
  getSettings, postSettings, testConnection, postAssistant, fetchTTS, postWebCall, postPhoneCall, getCallResult, pollCallResult, getCalls, postDiagnostico,
  type Stats, type ClientRow, type ClientDetail, type Driver, type Segmentos, type SettingsState, type CallLog,
} from './api'

function useTheme() {
  const [theme, setTheme] = useState<'light' | 'dark'>(
    () => (localStorage.getItem('theme') as 'light' | 'dark') || 'light')
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])
  return { theme, toggle: () => setTheme(t => (t === 'light' ? 'dark' : 'light')) }
}

const fmt = (n: number) => n.toLocaleString('es-MX')

function RiskBadge({ r }: { r: string }) {
  return <span className={`risk ${r}`}><span className="dot" />{r}</span>
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null
  const w = 460, h = 70
  const max = Math.max(...values, 1), min = Math.min(...values, 0)
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w
    const y = h - ((v - min) / Math.max(max - min, 1)) * h
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: 'block', overflow: 'visible' }}>
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5"
        vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  )
}

function LineChart({ data }: { data: { mes: number; rate: number }[] }) {
  if (data.length < 2) return <div className="chart" style={{ height: 120 }}><span className="skeleton" style={{ width: '100%', height: 120 }} /></div>
  const w = 900, h = 150, pad = 10
  const max = Math.max(...data.map(d => d.rate)), min = Math.min(...data.map(d => d.rate))
  const pts = data.map((d, i) => [(i / (data.length - 1)) * w,
    h - pad - ((d.rate - min) / Math.max(max - min, 0.01)) * (h - pad * 2)] as [number, number])
  const line = pts.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const last = pts[pts.length - 1]
  const fmt = (m: number) => `${String(m).slice(4, 6)}/${String(m).slice(2, 4)}`
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${w} ${h + 18}`} preserveAspectRatio="none">
        <polygon className="area" points={`0,${h} ${line} ${w},${h}`} />
        <polyline className="line" points={line} />
        <circle className="dot-last" cx={last[0]} cy={last[1]} r="4" />
        {data.map((d, i) => (i % 4 === 0 || i === data.length - 1) && (
          <text key={i} className="axis" x={(i / (data.length - 1)) * w} y={h + 13} textAnchor="middle">{fmt(d.mes)}</text>
        ))}
      </svg>
    </div>
  )
}

function DashboardView({ onGoToCalls }: { onGoToCalls?: () => void }) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [rows, setRows] = useState<ClientRow[]>([])
  const [riesgo, setRiesgo] = useState<string | null>('alto')
  const [q, setQ] = useState('')
  const [sortKey, setSortKey] = useState<'proba' | 'tienda' | 'territory_d' | 'rtm_customer_size_d'>('proba')
  const [sortDir, setSortDir] = useState<1 | -1>(-1)
  const [limit, setLimit] = useState(25)
  const [trend, setTrend] = useState<{ mes: number; rate: number }[]>([])
  const [drivers, setDrivers] = useState<Driver[]>([])
  const [seg, setSeg] = useState<Segmentos | null>(null)
  const [sel, setSel] = useState<ClientDetail | null>(null)
  const [loadingSel, setLoadingSel] = useState(false)
  const [callState, setCallState] = useState<'idle' | 'connecting' | 'live'>('idle')
  const webClient = useRef<RetellWebClient | null>(null)
  const [diag, setDiag] = useState('')
  const [diagBusy, setDiagBusy] = useState(false)

  const startCall = async (id: string) => {
    setCallState('connecting')
    try {
      const { access_token, call_id } = await postWebCall(id)
      const client = new RetellWebClient()
      webClient.current = client
      client.on('call_started', () => setCallState('live'))
      client.on('call_ended', () => {
        setCallState('idle')
        sileo.success({ title: 'Llamada finalizada', description: 'Analizando la conversación…' })
        setTimeout(() => {
          getCallResult(call_id).then(res => {
            if (res.ready && res.summary)
              sileo.success({ title: `Resultado · ${res.sentiment || 'registrado'}`, description: res.summary.slice(0, 130) })
          }).catch(() => {})
        }, 6000)
      })
      client.on('error', () => { setCallState('idle'); sileo.error({ title: 'Error en la llamada' }) })
      await client.startCall({ accessToken: access_token })
    } catch {
      setCallState('idle')
      sileo.error({ title: 'No se pudo iniciar la llamada', description: 'Revisa la key de Retell en Ajustes' })
    }
  }
  const hangup = () => { webClient.current?.stopCall(); setCallState('idle') }

  const [phoneNum, setPhoneNum] = useState('')
  const callPhone = async (id: string) => {
    if (!phoneNum.trim()) { sileo.warning({ title: 'Escribe un número a marcar' }); return }
    const req = postPhoneCall(id, phoneNum.trim())
    sileo.promise(req, {
      loading: { title: 'Conectando llamada…', description: `Marcando a ${phoneNum}` },
      success: { title: 'Llamada en curso', description: `Se registrará al colgar · ${phoneNum}` },
      error: { title: 'No se pudo llamar', description: 'Configura el número Retell (from) en Ajustes' },
    })
    try {
      const { call_id } = await req
      pollCallResult(call_id, r => sileo.action({
        title: 'Llamada registrada',
        description: r.summary?.slice(0, 120) || 'Resultado guardado en Llamadas',
        button: { title: 'Ver cola', onClick: () => onGoToCalls?.() },
      }))
    } catch { /* el toast de error ya salió */ }
  }

  useEffect(() => {
    getStats().then(setStats).catch(() => {})
    getDrivers().then(d => setDrivers(d.drivers_globales)).catch(() => {})
    getSegmentos().then(setSeg).catch(() => {})
    getTrend().then(d => setTrend(d.trend)).catch(() => {})
  }, [])
  useEffect(() => {
    getClients({ riesgo: riesgo || undefined, limit }).then(d => setRows(d.clients)).catch(() => {})
  }, [riesgo, limit])

  const toggleSort = (k: typeof sortKey) => {
    if (sortKey === k) setSortDir(d => (d === 1 ? -1 : 1))
    else { setSortKey(k); setSortDir(k === 'proba' ? -1 : 1) }
  }
  const viewRows = [...rows]
    .filter(c => {
      if (!q.trim()) return true
      const t = `${c.tienda} ${c.territory_d} ${c.comercial_subchannel_d} ${c.rtm_customer_size_d}`.toLowerCase()
      return t.includes(q.trim().toLowerCase())
    })
    .sort((a, b) => {
      const va = sortKey === 'proba' ? a.churn_proba : String((a as Record<string, unknown>)[sortKey] ?? '')
      const vb = sortKey === 'proba' ? b.churn_proba : String((b as Record<string, unknown>)[sortKey] ?? '')
      return va < vb ? -sortDir : va > vb ? sortDir : 0
    })

  const openClient = useCallback(async (id: string) => {
    setLoadingSel(true); setSel(null); setDiag('')
    try { setSel(await getClient(id)) } finally { setLoadingSel(false) }
  }, [])

  const generarDiag = async (id: string) => {
    setDiagBusy(true)
    try {
      const r = await postDiagnostico(id)
      if (r.diagnostico) setDiag(r.diagnostico)
      else sileo.error({ title: 'No se pudo generar', description: r.error || 'Revisa la API key de Gemini' })
    } catch {
      sileo.error({ title: 'No se pudo generar el diagnóstico' })
    } finally { setDiagBusy(false) }
  }

  const registrarAccion = async (id: string) => {
    try {
      await postAction({ customer_id: id, accion: 'Contacto de retención', notas: 'Generado desde el radar' })
      sileo.action({
        title: 'Acción registrada',
        description: 'Cliente añadido a la cola de retención',
        button: { title: 'Ver cola', onClick: () => onGoToCalls?.() },
      })
      getStats().then(setStats)
    } catch {
      sileo.error({ title: 'No se pudo registrar', description: 'Revisa la conexión con el backend' })
    }
  }

  const sizeSeg = (seg?.rtm_customer_size_d ?? []).filter(s => s.grupo !== 'Desconocido').slice(0, 6)
  const segMax = Math.max(...sizeSeg.map(s => s.riesgo_prom), 1)
  const terrSeg = (seg?.territory_d ?? []).slice(0, 6)
  const terrMax = Math.max(...terrSeg.map(s => s.riesgo_prom), 1)

  return (
    <>
      <main className="container">
        <section className="section">
          <div className="section-label">Panorama</div>
          <div className="kpi-grid">
            <div className="kpi"><div className="kpi-label">Clientes</div><div className="kpi-value mono">{stats ? fmt(stats.total_clientes) : <span className="skeleton sk-kpi" />}</div><div className="kpi-sub">en cartera activa</div></div>
            <div className="kpi"><div className="kpi-label">Riesgo alto</div><div className="kpi-value mono accent">{stats ? fmt(stats.riesgo_alto) : <span className="skeleton sk-kpi" />}</div><div className="kpi-sub">{stats ? `${stats.pct_riesgo_alto}% de la cartera` : ' '}</div></div>
            <div className="kpi"><div className="kpi-label">Churn esperado</div><div className="kpi-value mono">{stats ? fmt(stats.churn_esperado) : <span className="skeleton sk-kpi" />}</div><div className="kpi-sub">próximo mes · feb-2026</div></div>
            <div className="kpi"><div className="kpi-label">Acciones</div><div className="kpi-value mono">{stats ? fmt(stats.acciones_registradas) : <span className="skeleton sk-kpi" />}</div><div className="kpi-sub">de retención</div></div>
          </div>
        </section>

        <section className="section enter">
          <div className="section-label">Tendencia de churn · histórico mensual</div>
          <LineChart data={trend} />
        </section>

        <section className="section">
          <div className="section-label">Radar de clientes</div>
          <div className="search">
            <svg className="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
            <input placeholder="Buscar tiendita, territorio o canal…" value={q} onChange={e => setQ(e.target.value)} />
          </div>
          <div className="filters">
            {(['alto', 'medio', 'bajo', null] as (string | null)[]).map(r => (
              <button key={r ?? 'todos'} className={`chip ${riesgo === r ? 'active' : ''}`} onClick={() => setRiesgo(r)}>
                {r ?? 'Todos'}
              </button>
            ))}
          </div>
          <table className="table">
            <thead>
              <tr>
                <th className="sortable" onClick={() => toggleSort('tienda')}>Cliente {sortKey === 'tienda' && <span className="th-arrow">{sortDir === 1 ? '↑' : '↓'}</span>}</th>
                <th className="sortable" onClick={() => toggleSort('territory_d')}>Territorio {sortKey === 'territory_d' && <span className="th-arrow">{sortDir === 1 ? '↑' : '↓'}</span>}</th>
                <th>Canal</th>
                <th className="sortable" onClick={() => toggleSort('rtm_customer_size_d')}>Tamaño {sortKey === 'rtm_customer_size_d' && <span className="th-arrow">{sortDir === 1 ? '↑' : '↓'}</span>}</th>
                <th>Riesgo</th>
                <th className="num sortable" onClick={() => toggleSort('proba')}>Probabilidad {sortKey === 'proba' && <span className="th-arrow">{sortDir === 1 ? '↑' : '↓'}</span>}</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0
                ? Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}><td colSpan={6}><span className="skeleton sk-line" /></td></tr>
                ))
                : viewRows.map((c, i) => (
                  <tr key={c.customer_id} className="enter" style={{ animationDelay: `${Math.min(i, 14) * 28}ms` }} onClick={() => openClient(c.customer_id)}>
                    <td><div className="tienda-name">{c.tienda}</div><div className="cust-id">{c.customer_id.slice(0, 8)}…</div></td>
                    <td>{c.territory_d}</td>
                    <td>{c.comercial_subchannel_d}</td>
                    <td>{c.rtm_customer_size_d}</td>
                    <td><RiskBadge r={c.riesgo} /></td>
                    <td className="num proba">{(c.churn_proba * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              {rows.length > 0 && viewRows.length === 0 && (
                <tr><td colSpan={6} className="mono" style={{ color: 'var(--fg-faint)', textAlign: 'center', padding: '24px' }}>Sin coincidencias para “{q}”.</td></tr>
              )}
            </tbody>
          </table>
          {rows.length > 0 && !q && <button className="load-more" onClick={() => setLimit(l => l + 25)}>Cargar más clientes</button>}
        </section>

        <section className="section">
          <div className="section-label">Causa raíz · dónde se concentra la fuga</div>
          <div className="causa-grid">
            <div className="causa-col">
              <div className="bars-title">Por tamaño de tienda</div>
              <div className="bars">
                {sizeSeg.map(s => (
                  <div className="bar-row" key={s.grupo}>
                    <div className="bar-label">{s.grupo}</div>
                    <div className="bar-track"><div className="bar-fill" style={{ width: `${(s.riesgo_prom / segMax) * 100}%` }} /></div>
                    <div className="bar-val">{s.riesgo_prom}%</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="causa-col">
              <div className="bars-title">Por territorio (top)</div>
              <div className="bars">
                {terrSeg.map(s => (
                  <div className="bar-row" key={s.grupo}>
                    <div className="bar-label">{s.grupo}</div>
                    <div className="bar-track"><div className="bar-fill" style={{ width: `${(s.riesgo_prom / terrMax) * 100}%` }} /></div>
                    <div className="bar-val">{s.riesgo_prom}%</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="section">
          <div className="section-label">Qué dispara la fuga · modelo</div>
          <div className="drivers">
            {drivers.slice(0, 8).map((d, i) => (
              <div className="driver" key={d.feature}><span className="rank">{String(i + 1).padStart(2, '0')}</span>{d.label}</div>
            ))}
          </div>
        </section>
      </main>

      {(sel || loadingSel) && (
        <>
          <div className="scrim" onClick={() => setSel(null)} />
          <aside className="drawer">
            <button className="drawer-close mono" onClick={() => setSel(null)}>✕ cerrar</button>
            {loadingSel && <p className="mono" style={{ color: 'var(--fg-muted)' }}>Cargando…</p>}
            {sel && (
              <>
                <div className="ficha-head">
                  <div className="ficha-tienda">{sel.info.tienda}</div>
                  <div className="ficha-contacto mono">{sel.info.dueno} · {sel.info.telefono}</div>
                </div>
                <h2>Probabilidad de fuga</h2>
                <div className="big accent">{(sel.info.churn_proba * 100).toFixed(1)}%</div>
                <RiskBadge r={sel.info.riesgo} />
                <div className="attrs">
                  <div className="attr"><div className="k">Territorio</div><div className="v">{sel.info.territory_d}</div></div>
                  <div className="attr"><div className="k">Canal</div><div className="v">{sel.info.comercial_subchannel_d}</div></div>
                  <div className="attr"><div className="k">Tamaño</div><div className="v">{sel.info.rtm_customer_size_d}</div></div>
                  <div className="attr"><div className="k">Dueño</div><div className="v">{sel.info.dueno}</div></div>
                </div>
                <h2>Trayectoria · cajas vendidas / mes</h2>
                <div style={{ color: 'var(--fg)', margin: '14px 0 26px' }}>
                  <Sparkline values={sel.historial_ventas.map(h => h.cajas)} />
                </div>
                <div className="diag">
                  <div className="diag-head">
                    <span className="diag-title"><span className="glyph-dot" />Diagnóstico IA · Gemini</span>
                    <button className="btn-test" onClick={() => generarDiag(sel.info.customer_id)} disabled={diagBusy}>
                      {diagBusy ? 'Analizando…' : diag ? 'Regenerar' : 'Generar'}
                    </button>
                  </div>
                  {diag
                    ? <p className="diag-text">{diag}</p>
                    : <p className="diag-empty">Gemini interpreta las señales de este negocio + el contexto del churn: por qué está en riesgo y qué ofrecerle. Es lo que Sofía usa en la llamada.</p>}
                </div>
                <button className="btn-primary" onClick={() => registrarAccion(sel.info.customer_id)}>
                  Registrar acción de retención
                </button>
                {callState === 'idle' ? (
                  <button className="btn-call" onClick={() => startCall(sel.info.customer_id)}>
                    Llamada de retención con IA
                  </button>
                ) : callState === 'connecting' ? (
                  <button className="btn-call" disabled>Conectando…</button>
                ) : (
                  <button className="btn-call live" onClick={hangup}>
                    <span className="live-dot" /> En llamada — Colgar
                  </button>
                )}
                <div className="phone-call">
                  <input className="phone-input" placeholder="+52 55 1234 5678"
                    value={phoneNum} onChange={e => setPhoneNum(e.target.value)} />
                  <button className="btn-call" onClick={() => callPhone(sel.info.customer_id)}>Llamar al teléfono</button>
                </div>
              </>
            )}
          </aside>
        </>
      )}
    </>
  )
}

const FIELDS = [
  { k: 'supabase_url', label: 'Supabase URL', hint: 'Project URL — https://xxxxx.supabase.co' },
  { k: 'supabase_anon_key', label: 'Supabase anon key', hint: 'Clave publishable (lectura del frontend)' },
  { k: 'supabase_service_key', label: 'Supabase service_role', hint: 'Clave secreta (acceso del backend)' },
  { k: 'supabase_db_url', label: 'Supabase Connection String', hint: 'postgresql://postgres:…@db…supabase.co:5432/postgres' },
  { k: 'gemini_api_key', label: 'Gemini API Key', hint: 'Google AI Studio — motor del agente IA' },
  { k: 'elevenlabs_api_key', label: 'ElevenLabs API Key', hint: 'Voz del agente y de las llamadas' },
  { k: 'elevenlabs_voice_id', label: 'ElevenLabs Voice ID', hint: 'Voz de Sara (Jessica por defecto)' },
  { k: 'retell_api_key', label: 'Retell API Key', hint: 'Llamadas automáticas de retención' },
  { k: 'retell_from_number', label: 'Retell Número (from)', hint: 'Número saliente — formato +1… o +52…' },
] as const

const FIELD_MAP: Record<string, { k: string; label: string; hint: string }> =
  Object.fromEntries(FIELDS.map(f => [f.k, f]))

const GROUPS = [
  { tech: 'supabase', title: 'Supabase', desc: 'Base de datos · scores de churn e historial de llamadas', keys: ['supabase_url', 'supabase_anon_key', 'supabase_service_key', 'supabase_db_url'] },
  { tech: 'gemini', title: 'Gemini', desc: 'Motor del agente IA conversacional', keys: ['gemini_api_key'] },
  { tech: 'elevenlabs', title: 'ElevenLabs', desc: 'Voz del agente (texto a voz)', keys: ['elevenlabs_api_key', 'elevenlabs_voice_id'] },
  { tech: 'retell', title: 'Retell', desc: 'Llamadas telefónicas de retención con Sofía', keys: ['retell_api_key', 'retell_from_number'] },
] as const

function SettingsView() {
  const [s, setS] = useState<SettingsState>({})
  const [form, setForm] = useState<Record<string, string>>({})
  const [tests, setTests] = useState<Record<string, { ok?: boolean; msg?: string; loading?: boolean }>>({})
  const [calling, setCalling] = useState(false)
  const [lada, setLada] = useState('+52')
  const [num, setNum] = useState('')
  const webRef = useRef<RetellWebClient | null>(null)
  const [testCli, setTestCli] = useState<ClientRow | null>(null)
  const [testDiag, setTestDiag] = useState('')
  const [testDiagBusy, setTestDiagBusy] = useState(false)

  useEffect(() => { getSettings().then(setS).catch(() => {}) }, [])
  useEffect(() => { getClients({ limit: 1 }).then(d => setTestCli(d.clients[0] || null)).catch(() => {}) }, [])

  const verTestDiag = async () => {
    if (!testCli) return
    setTestDiagBusy(true)
    try {
      const r = await postDiagnostico(testCli.customer_id)
      setTestDiag(r.diagnostico || r.error || '—')
    } catch { setTestDiag('No se pudo generar el diagnóstico') }
    finally { setTestDiagBusy(false) }
  }

  const save = async () => {
    try {
      await sileo.promise(postSettings(form), {
        loading: { title: 'Guardando ajustes…' },
        success: { title: 'Ajustes guardados', description: 'Las API keys quedaron configuradas' },
        error: { title: 'No se pudo guardar', description: 'Revisa la conexión con el backend' },
      })
      setForm({}); getSettings().then(setS)
    } catch { /* el toast de error ya lo muestra el promise */ }
  }

  const testTech = async (tech: string) => {
    setTests(t => ({ ...t, [tech]: { loading: true } }))
    try {
      if (Object.keys(form).length) { await postSettings(form); setForm({}); getSettings().then(setS) }
      const r = await testConnection(tech)
      setTests(t => ({ ...t, [tech]: { ok: r.ok, msg: r.message } }))
    } catch {
      setTests(t => ({ ...t, [tech]: { ok: false, msg: 'Error de conexión con el backend' } }))
    }
  }

  const testWebCall = async () => {
    setCalling(true)
    try {
      const cl = await getClients({ limit: 1 })
      const cid = cl.clients[0]?.customer_id
      if (!cid) throw new Error('sin clientes')
      const { access_token } = await postWebCall(cid)
      const client = new RetellWebClient(); webRef.current = client
      client.on('call_ended', () => setCalling(false))
      client.on('error', () => setCalling(false))
      await client.startCall({ accessToken: access_token })
    } catch {
      setCalling(false)
      sileo.error({ title: 'No se pudo iniciar la web call', description: 'Revisa la API key de Retell' })
    }
  }
  const stopWebCall = () => { webRef.current?.stopCall(); setCalling(false) }
  const testPhoneCall = async () => {
    if (!num.trim()) { sileo.warning({ title: 'Escribe el número a marcar' }); return }
    const cl = await getClients({ limit: 1 })
    const req = postPhoneCall(cl.clients[0]?.customer_id || '', (lada + num).replace(/\s/g, ''))
    sileo.promise(req, {
      loading: { title: 'Conectando llamada…', description: `Marcando a ${lada} ${num}` },
      success: { title: 'Llamada en curso', description: `Se registrará al colgar · ${lada} ${num}` },
      error: { title: 'No se pudo llamar', description: 'Falta el número Retell (from) o el billing está pendiente' },
    })
    try {
      const { call_id } = await req
      pollCallResult(call_id, r => sileo.success({ title: 'Llamada registrada en historial', description: r.summary?.slice(0, 120) || 'Resultado guardado' }))
    } catch { /* ya notificado por el promise */ }
  }

  return (
    <main className="container">
      <div className="section-label" style={{ marginBottom: 6 }}>Ajustes · Conexiones</div>
      {GROUPS.map(g => {
        const r = tests[g.tech]
        return (
          <section className="section" key={g.tech}>
            <div className="tech-head">
              <div>
                <div className="chat-name" style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                  <span className={`led ${g.keys.every(k => s[k]?.set) ? 'green' : 'red'}`} />{g.title}
                </div>
                <span className="hint">{g.desc}</span>
              </div>
              <button className="btn-test" onClick={() => testTech(g.tech)} disabled={r?.loading}>
                {r?.loading ? 'Probando…' : 'Probar conexión'}
              </button>
            </div>
            {r && !r.loading && r.msg && (
              <div className={`test-result ${r.ok ? 'ok' : 'fail'}`}><span>{r.ok ? '✓' : '✗'}</span>{r.msg}</div>
            )}
            <div className="form">
              {g.keys.map(k => {
                const f = FIELD_MAP[k]
                return (
                  <div className="field" key={k}>
                    <label>{f.label}</label>
                    <span className="hint">{f.hint}</span>
                    <input
                      type="password"
                      placeholder={s[k]?.set ? `configurada · ${s[k].masked}` : 'pegar aquí…'}
                      value={form[k] ?? ''}
                      onChange={e => setForm(v => ({ ...v, [k]: e.target.value }))}
                    />
                    <span className="status">
                      <span className={`led ${s[k]?.set ? 'green' : 'red'}`} />
                      {s[k]?.set ? 'configurada' : 'sin configurar'}
                    </span>
                  </div>
                )
              })}
            </div>
          </section>
        )
      })}
      <button className="btn-primary" onClick={save} style={{ marginBottom: 28 }}>Guardar ajustes</button>

      <section className="section">
        <div className="section-label">Probar llamada</div>
        <div className="form">
          {testCli && (
            <div className="diag">
              <div className="diag-head">
                <span className="diag-title"><span className="glyph-dot" />Prueba con · {testCli.tienda} ({testCli.dueno})</span>
                <button className="btn-test" onClick={verTestDiag} disabled={testDiagBusy}>
                  {testDiagBusy ? 'Analizando…' : 'Ver diagnóstico'}
                </button>
              </div>
              {testDiag
                ? <p className="diag-text">{testDiag}</p>
                : <p className="diag-empty">La llamada de prueba lleva el diagnóstico IA de este cliente — Sofía hablará de sus problemas concretos, no genérico.</p>}
            </div>
          )}
          {calling ? (
            <button className="btn-call live" onClick={stopWebCall}>
              <span className="live-dot" /> Web call en curso — habla con el agente · Colgar
            </button>
          ) : (
            <button className="btn-primary" onClick={testWebCall}>▶ Probar Web Call (por el navegador)</button>
          )}
          <div className="field">
            <label>Llamada telefónica de prueba</label>
            <span className="hint">El agente marca a este número (requiere número Retell + billing activo)</span>
            <div className="phone-call">
              <input className="phone-input" style={{ maxWidth: 92 }} value={lada} onChange={e => setLada(e.target.value)} placeholder="+52" />
              <input className="phone-input" value={num} onChange={e => setNum(e.target.value)} placeholder="55 1234 5678" />
              <button className="btn-call" onClick={testPhoneCall}>Llamar</button>
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}

function CallsView() {
  const [calls, setCalls] = useState<CallLog[]>([])
  const [refreshing, setRefreshing] = useState(false)

  const tick = useCallback(async () => {
    const d = await getCalls().catch(() => null)
    if (!d) return
    setCalls(d.calls)
    // Reconciliar SOLO las "en curso" recientes (<15 min). Las viejas el backend ya
    // las cierra como "Sin completar" → nunca se reconsultan en bucle.
    const reciente = (iso: string) => Date.now() - Date.parse(iso.replace(' ', 'T')) < 15 * 60 * 1000
    const pend = d.calls.filter(c => c.call_id && /en curso/i.test(c.resultado || '') && reciente(c.created_at))
    if (pend.length) {
      await Promise.all(pend.map(c => getCallResult(c.call_id as string).catch(() => {})))
      const d2 = await getCalls().catch(() => null)
      if (d2) setCalls(d2.calls)
    }
  }, [])

  useEffect(() => {
    tick()
    const id = setInterval(tick, 8000)   // auto-refresco ligado a esta vista; se DETIENE al salir de Llamadas
    return () => clearInterval(id)
  }, [tick])

  const manual = async () => { setRefreshing(true); await tick(); setRefreshing(false) }

  return (
    <main className="container">
      <section className="section">
        <div className="calls-head">
          <div className="section-label" style={{ marginBottom: 0 }}>Historial de llamadas de retención</div>
          <button className="btn-test" onClick={manual} disabled={refreshing}>{refreshing ? 'Actualizando…' : '↻ Actualizar'}</button>
        </div>
        {calls.length === 0 ? (
          <p className="mono" style={{ color: 'var(--fg-faint)', fontSize: 13, lineHeight: 1.7 }}>
            Aún no hay llamadas registradas.<br />Haz una desde la ficha de un cliente (Radar) y aquí verás el resumen y el sentimiento de la conversación.
          </p>
        ) : (
          <div className="calls">
            {calls.map((c, i) => {
              const enCurso = /en curso/i.test(c.resultado || '')
              return (
                <div className="call-row" key={c.call_id || i}>
                  <div>
                    <div className="tienda-name">{c.tienda || c.customer_id.slice(0, 10)}</div>
                    <div className="call-when">{c.dueno} · {c.created_at.slice(0, 16)}{c.duracion_seg ? ` · ${c.duracion_seg}s` : ''}</div>
                  </div>
                  <div className="call-summary">{c.guion || '—'}</div>
                  <div className={`sent ${enCurso ? 'pending' : c.resultado}`}>{enCurso ? '⏳ en curso' : c.resultado}</div>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </main>
  )
}

const SUGERENCIAS = [
  '¿Quiénes son mis 10 clientes más en riesgo?',
  '¿Por qué se van las tienditas Mini?',
  '¿Qué territorio pierde más clientes?',
  '¿Qué acción tomo esta semana?',
]

const Glyph = () => (
  <svg className="glyph" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 2.2l1.9 6.4a3 3 0 0 0 1.5 1.5l6.4 1.9-6.4 1.9a3 3 0 0 0-1.5 1.5L12 21.8l-1.9-6.4a3 3 0 0 0-1.5-1.5L2.2 12l6.4-1.9a3 3 0 0 0 1.5-1.5z" />
  </svg>
)

function AgentView() {
  const [log, setLog] = useState<{ role: 'user' | 'bot'; text: string }[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [speaking, setSpeaking] = useState<number | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [log, busy])

  const speak = async (i: number, text: string) => {
    if (speaking !== null) return
    setSpeaking(i)
    try {
      const url = await fetchTTS(text)
      const audio = new Audio(url)
      audio.onended = () => setSpeaking(null)
      audio.onerror = () => setSpeaking(null)
      await audio.play()
    } catch {
      setSpeaking(null)
      sileo.error({ title: 'No se pudo generar la voz', description: 'Revisa la API key de ElevenLabs en Ajustes' })
    }
  }

  const send = async (msg?: string) => {
    const m = (msg ?? input).trim()
    if (!m || busy) return
    setLog(l => [...l, { role: 'user', text: m }])
    setInput(''); setBusy(true)
    try {
      const r = await postAssistant(m)
      setLog(l => [...l, { role: 'bot', text: r.reply }])
    } catch {
      setLog(l => [...l, { role: 'bot', text: 'No pude responder. Revisa la API key de Gemini en Ajustes.' }])
    } finally { setBusy(false) }
  }

  return (
    <main className="container">
      <section className="section" style={{ marginBottom: 0 }}>
        <div className="section-label">Agente · Centinela</div>
        <div className="chat">
          <div className="chat-head">
            <div className="avatar"><Glyph /></div>
            <div>
              <div className="chat-name">Centinela</div>
              <div className="chat-status"><span className="dot-live" />Analista de retención · en línea</div>
            </div>
          </div>
          <div className="chat-log">
            {log.length === 0 && (
              <div className="chat-empty">
                <div className="avatar lg"><Glyph /></div>
                <div className="empty-title">Hola, soy Centinela</div>
                <p className="empty-sub">Tu analista de retención. Pregúntame sobre el churn de tus tienditas y qué hacer para retenerlas.</p>
                <div className="suggest">
                  {SUGERENCIAS.map(s => <button key={s} className="suggest-card" onClick={() => send(s)}>{s}</button>)}
                </div>
              </div>
            )}
            {log.map((m, i) => (
              <div key={i} className={`row ${m.role} enter`}>
                {m.role === 'bot' && <div className="avatar sm"><Glyph /></div>}
                <div className="bubble-wrap">
                  {m.role === 'bot' && (
                    <div className="who">
                      Centinela
                      <button className={`speak ${speaking === i ? 'on' : ''}`} onClick={() => speak(i, m.text)}>
                        {speaking === i ? (
                          <><svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>sonando</>
                        ) : (
                          <><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 5 6 9H2v6h4l5 4z" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /></svg>voz</>
                        )}
                      </button>
                    </div>
                  )}
                  <div className={`msg ${m.role}`}>{m.text}</div>
                </div>
              </div>
            ))}
            {busy && (
              <div className="row bot enter">
                <div className="avatar sm"><Glyph /></div>
                <div className="bubble-wrap">
                  <div className="msg bot typing"><span /><span /><span /></div>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
          <div className="chat-input">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') send() }}
              placeholder="Escribe tu pregunta…"
            />
            <button className="chat-send" onClick={() => send()} disabled={busy} aria-label="Enviar">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m22 2-7 20-4-9-9-4z" /><path d="M22 2 11 13" /></svg>
            </button>
          </div>
        </div>
      </section>
    </main>
  )
}

const ICONS: Record<string, string> = {
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.6"/>',
  sliders: '<line x1="4" y1="8" x2="20" y2="8"/><circle cx="9" cy="8" r="2.3"/><line x1="4" y1="16" x2="20" y2="16"/><circle cx="15" cy="16" r="2.3"/>',
  bot: '<rect x="4" y="8" width="16" height="11" rx="2"/><path d="M12 4v4"/><circle cx="9" cy="13.5" r="1"/><circle cx="15" cy="13.5" r="1"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 005 5L16 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2z"/>',
}
function Icon({ name }: { name: string }) {
  return (
    <svg className="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: ICONS[name] || '' }} />
  )
}

type View = 'dashboard' | 'agent' | 'calls' | 'settings'
const MODULES: { id: View; label: string; icon: string }[] = [
  { id: 'dashboard', label: 'Radar', icon: 'target' },
  { id: 'agent', label: 'Agente', icon: 'bot' },
  { id: 'calls', label: 'Llamadas', icon: 'phone' },
  { id: 'settings', label: 'Ajustes', icon: 'sliders' },
]

export default function App() {
  const { theme, toggle } = useTheme()
  const [view, setView] = useState<View>('dashboard')

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <img src="/arca-logo.png" className="brand-logo" alt="Arca Continental" />
          <div className="brand-text">
            <h1>Centinela</h1>
            <span className="tag">Arca Continental · Retención</span>
          </div>
        </div>
        <nav className="side-nav">
          {MODULES.map(m => (
            <button key={m.id} className={view === m.id ? 'active' : ''} onClick={() => setView(m.id)}>
              <Icon name={m.icon} /><span className="label">{m.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <button className="toggle" onClick={toggle} aria-label="Cambiar tema">
            {theme === 'light' ? '◐  Dark' : '◑  Light'}
          </button>
        </div>
      </aside>

      <div className="content">
        {view === 'dashboard' ? <DashboardView onGoToCalls={() => setView('calls')} /> : view === 'agent' ? <AgentView /> : view === 'calls' ? <CallsView /> : <SettingsView />}
      </div>
    </div>
  )
}
