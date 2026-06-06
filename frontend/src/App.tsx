import { useEffect, useState, useCallback } from 'react'
import { sileo } from 'sileo'
import {
  getStats, getClients, getClient, getDrivers, getSegmentos, postAction,
  getSettings, postSettings, postAssistant, fetchTTS,
  type Stats, type ClientRow, type ClientDetail, type Driver, type Segmentos, type SettingsState,
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

function DashboardView() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [rows, setRows] = useState<ClientRow[]>([])
  const [riesgo, setRiesgo] = useState<string | null>('alto')
  const [drivers, setDrivers] = useState<Driver[]>([])
  const [seg, setSeg] = useState<Segmentos | null>(null)
  const [sel, setSel] = useState<ClientDetail | null>(null)
  const [loadingSel, setLoadingSel] = useState(false)

  useEffect(() => {
    getStats().then(setStats).catch(() => {})
    getDrivers().then(d => setDrivers(d.drivers_globales)).catch(() => {})
    getSegmentos().then(setSeg).catch(() => {})
  }, [])
  useEffect(() => {
    getClients({ riesgo: riesgo || undefined, limit: 25 }).then(d => setRows(d.clients)).catch(() => {})
  }, [riesgo])

  const openClient = useCallback(async (id: string) => {
    setLoadingSel(true); setSel(null)
    try { setSel(await getClient(id)) } finally { setLoadingSel(false) }
  }, [])

  const registrarAccion = async (id: string) => {
    try {
      await postAction({ customer_id: id, accion: 'Contacto de retención', notas: 'Generado desde el radar' })
      sileo.success({ title: 'Acción registrada', description: 'Cliente añadido a la cola de retención' })
      getStats().then(setStats)
    } catch {
      sileo.error({ title: 'No se pudo registrar', description: 'Revisa la conexión con el backend' })
    }
  }

  const sizeSeg = (seg?.rtm_customer_size_d ?? []).filter(s => s.grupo !== 'Desconocido').slice(0, 6)
  const segMax = Math.max(...sizeSeg.map(s => s.riesgo_prom), 1)

  return (
    <>
      <main className="container">
        <section className="section">
          <div className="section-label">Panorama</div>
          <div className="kpi-grid">
            <div className="kpi"><div className="kpi-label">Clientes</div><div className="kpi-value mono">{stats ? fmt(stats.total_clientes) : '—'}</div><div className="kpi-sub">en cartera activa</div></div>
            <div className="kpi"><div className="kpi-label">Riesgo alto</div><div className="kpi-value mono accent">{stats ? fmt(stats.riesgo_alto) : '—'}</div><div className="kpi-sub">{stats ? `${stats.pct_riesgo_alto}% de la cartera` : ''}</div></div>
            <div className="kpi"><div className="kpi-label">Churn esperado</div><div className="kpi-value mono">{stats ? fmt(stats.churn_esperado) : '—'}</div><div className="kpi-sub">próximo mes · feb-2026</div></div>
            <div className="kpi"><div className="kpi-label">Acciones</div><div className="kpi-value mono">{stats ? fmt(stats.acciones_registradas) : '—'}</div><div className="kpi-sub">de retención</div></div>
          </div>
        </section>

        <section className="section">
          <div className="section-label">Radar de clientes</div>
          <div className="filters">
            {(['alto', 'medio', 'bajo', null] as (string | null)[]).map(r => (
              <button key={r ?? 'todos'} className={`chip ${riesgo === r ? 'active' : ''}`} onClick={() => setRiesgo(r)}>
                {r ?? 'Todos'}
              </button>
            ))}
          </div>
          <table className="table">
            <thead>
              <tr><th>Cliente</th><th>Territorio</th><th>Canal</th><th>Tamaño</th><th>Riesgo</th><th className="num">Probabilidad</th></tr>
            </thead>
            <tbody>
              {rows.map(c => (
                <tr key={c.customer_id} onClick={() => openClient(c.customer_id)}>
                  <td className="cust-id">{c.customer_id.slice(0, 10)}…</td>
                  <td>{c.territory_d}</td>
                  <td>{c.comercial_subchannel_d}</td>
                  <td>{c.rtm_customer_size_d}</td>
                  <td><RiskBadge r={c.riesgo} /></td>
                  <td className="num proba">{(c.churn_proba * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="section">
          <div className="section-label">Causa raíz · por tamaño de tienda</div>
          <div className="bars">
            {sizeSeg.map(s => (
              <div className="bar-row" key={s.grupo}>
                <div className="bar-label">{s.grupo}</div>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${(s.riesgo_prom / segMax) * 100}%` }} /></div>
                <div className="bar-val">{s.riesgo_prom}%</div>
              </div>
            ))}
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
                <h2>Probabilidad de fuga</h2>
                <div className="big accent">{(sel.info.churn_proba * 100).toFixed(1)}%</div>
                <RiskBadge r={sel.info.riesgo} />
                <div className="attrs">
                  <div className="attr"><div className="k">Territorio</div><div className="v">{sel.info.territory_d}</div></div>
                  <div className="attr"><div className="k">Canal</div><div className="v">{sel.info.comercial_subchannel_d}</div></div>
                  <div className="attr"><div className="k">Tamaño</div><div className="v">{sel.info.rtm_customer_size_d}</div></div>
                  <div className="attr"><div className="k">ID cliente</div><div className="v cust-id">{sel.info.customer_id.slice(0, 12)}…</div></div>
                </div>
                <h2>Trayectoria · cajas vendidas / mes</h2>
                <div style={{ color: 'var(--fg)', margin: '14px 0 30px' }}>
                  <Sparkline values={sel.historial_ventas.map(h => h.cajas)} />
                </div>
                <button className="btn-primary" onClick={() => registrarAccion(sel.info.customer_id)}>
                  Registrar acción de retención
                </button>
              </>
            )}
          </aside>
        </>
      )}
    </>
  )
}

const FIELDS = [
  { k: 'gemini_api_key', label: 'Gemini API Key', hint: 'Google AI Studio — motor del agente IA' },
  { k: 'elevenlabs_api_key', label: 'ElevenLabs API Key', hint: 'Voz del agente y de las llamadas' },
  { k: 'retell_api_key', label: 'Retell API Key', hint: 'Llamadas automáticas de retención' },
  { k: 'elevenlabs_voice_id', label: 'ElevenLabs Voice ID', hint: 'Voz de Sara (Jessica por defecto)' },
] as const

function SettingsView() {
  const [s, setS] = useState<SettingsState>({})
  const [form, setForm] = useState<Record<string, string>>({})

  useEffect(() => { getSettings().then(setS).catch(() => {}) }, [])

  const save = async () => {
    try {
      await postSettings(form)
      sileo.success({ title: 'Ajustes guardados', description: 'Las API keys quedaron configuradas' })
      setForm({}); getSettings().then(setS)
    } catch {
      sileo.error({ title: 'No se pudo guardar', description: 'Revisa la conexión con el backend' })
    }
  }

  return (
    <main className="container">
      <section className="section">
        <div className="section-label">Ajustes · API Keys</div>
        <div className="form">
          {FIELDS.map(f => (
            <div className="field" key={f.k}>
              <label>{f.label}</label>
              <span className="hint">{f.hint}</span>
              <input
                type="password"
                placeholder={s[f.k]?.set ? `configurada · ${s[f.k].masked}` : 'pegar aquí…'}
                value={form[f.k] ?? ''}
                onChange={e => setForm(v => ({ ...v, [f.k]: e.target.value }))}
              />
              <span className={`status ${s[f.k]?.set ? 'on' : ''}`}>
                {s[f.k]?.set ? '● configurada' : '○ sin configurar'}
              </span>
            </div>
          ))}
          <button className="btn-primary" onClick={save}>Guardar ajustes</button>
        </div>
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

function AgentView() {
  const [log, setLog] = useState<{ role: 'user' | 'bot'; text: string }[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [speaking, setSpeaking] = useState<number | null>(null)

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
          <div className="chat-log">
            {log.length === 0 && (
              <div className="chat-empty">
                <p className="mono" style={{ color: 'var(--fg-faint)', fontSize: 13 }}>
                  Pregúntame sobre el churn de tus clientes.
                </p>
                <div className="suggest">
                  {SUGERENCIAS.map(s => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}
                </div>
              </div>
            )}
            {log.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                {m.role === 'bot' && (
                  <div className="who">
                    Centinela
                    <button className={`speak ${speaking === i ? 'on' : ''}`} onClick={() => speak(i, m.text)}>
                      {speaking === i ? '◼ sonando' : '▶ voz'}
                    </button>
                  </div>
                )}
                {m.text}
              </div>
            ))}
            {busy && (
              <div className="msg bot"><div className="who">Centinela</div>
                <span className="mono" style={{ color: 'var(--fg-faint)' }}>pensando…</span></div>
            )}
          </div>
          <div className="chat-input">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') send() }}
              placeholder="Escribe tu pregunta…"
            />
            <button className="chat-send" onClick={() => send()} disabled={busy}>Enviar</button>
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

type View = 'dashboard' | 'agent' | 'settings'
const MODULES: { id: View; label: string; icon: string }[] = [
  { id: 'dashboard', label: 'Radar', icon: 'target' },
  { id: 'agent', label: 'Agente', icon: 'bot' },
  { id: 'settings', label: 'Ajustes', icon: 'sliders' },
]

export default function App() {
  const { theme, toggle } = useTheme()
  const [view, setView] = useState<View>('dashboard')

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1>Centinela</h1>
          <span className="tag">Arca · Retención</span>
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
        {view === 'dashboard' ? <DashboardView /> : view === 'agent' ? <AgentView /> : <SettingsView />}
      </div>
    </div>
  )
}
