// Fitness & fatigue in detail: fitness (CTL), fatigue (ATL) and daily load, with form (fitness − fatigue,
// as % of fitness) and its zones underneath, a shared hover readout, and a projection from planned workouts.
import { useCallback, useState, type PointerEvent } from 'react'
import { Card, Loading, Seg, useApi } from '../components/ui'
import { fd, isoWeekNo, SPORT } from '../lib/util'

const ZONE_COLOR: Record<string, string> = {
  transition: '#8b8b97', fresh: '#5ec8f2', neutral: '#6b6b80', productive: '#5ef2c4', risk: '#ff7a7a',
}
const ZONE_SHORT: Record<string, string> = {
  transition: 'Transition', fresh: 'Fresh', neutral: 'Neutral', productive: 'Productive', risk: 'Overtraining risk',
}
const PAD = { l: 44, r: 128, t: 10 }

/** Width of an element; a callback ref, because the chart only mounts once the data has loaded. */
function useWidth() {
  const [w, setW] = useState(900)
  const ref = useCallback((el: HTMLDivElement | null) => {
    if (!el) return
    setW(Math.max(360, el.getBoundingClientRect().width))
    new ResizeObserver(([e]) => setW(Math.max(360, e.contentRect.width))).observe(el)
  }, [])
  return { ref, w }
}

export default function Fitness({ refresh }: { refresh: number }) {
  const [days, setDays] = useState<'90' | '180' | '365' | '620'>('180')
  const { data: f, error } = useApi(`/fitness?days=${days}`, `${days}-${refresh}`)
  const { ref, w } = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  if (!f) return <Loading error={error} />

  const S = f.series as any[], P = f.projection as any[]
  const all = [...S, ...P.map(p => ({ ...p, projected: true }))]
  const n = all.length, now = S[S.length - 1]
  const iw = w - PAD.l - PAD.r
  const X = (i: number) => PAD.l + (i / Math.max(1, n - 1)) * iw

  // top chart: fitness, fatigue, daily load
  const H1 = 260, ih1 = H1 - PAD.t - 8
  const yMax = Math.ceil(Math.max(...all.map(r => Math.max(r.fitness, r.fatigue))) / 10) * 10 + 10
  const Y1 = (v: number) => PAD.t + (1 - v / yMax) * ih1
  const loadMax = Math.max(...all.map(r => r.load || 0), 1)
  const line = (key: string, rows: any[], offset = 0) =>
    rows.map((r, i) => `${i ? 'L' : 'M'}${X(i + offset).toFixed(1)} ${Y1(r[key]).toFixed(1)}`).join('')

  // bottom chart: form as % of fitness, with fixed zone bands
  const H2 = 200, ih2 = H2 - 34
  const fLo = -50, fHi = 35
  const Y2 = (v: number) => 6 + (1 - (Math.max(fLo, Math.min(fHi, v)) - fLo) / (fHi - fLo)) * ih2
  const formPath = (rows: any[], offset = 0) =>
    rows.map((r, i) => r.form_pct == null ? '' : `${i ? 'L' : 'M'}${X(i + offset).toFixed(1)} ${Y2(r.form_pct).toFixed(1)}`).join('')

  // month ticks
  const ticks = all.map((r, i) => [r.date, i] as [string, number]).filter(([d], i) => i === 0 || d.endsWith('-01'))

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const i = Math.round(((e.clientX - r.left - PAD.l) / iw) * (n - 1))
    setHover(i >= 0 && i < n ? i : null)
  }
  const h = hover != null ? all[hover] : null
  const zoneNow = now.zone

  return <>
    <div className="ph">
      <div><h1>Fitness & form</h1><p>Fitness is your 6-week training load, fatigue the last week; form is the difference, as % of fitness.</p></div>
      <div className="row" style={{ gap: 10 }}>
        <Seg value={days} options={[['90', '3 months'], ['180', '6 months'], ['365', '1 year'], ['620', 'All']]} onChange={v => { setDays(v); setHover(null) }} />
        <button className="btn" onClick={() => (location.hash = 'today')}>‹ Today</button>
      </div>
    </div>

    <div className="grid" style={{ marginBottom: 14 }}>
      {[
        ['Fitness', now.fitness.toFixed(0), 'CTL · 42-day load', '#5ef2c4'],
        ['Fatigue', now.fatigue.toFixed(0), 'ATL · 7-day load', '#ff8fb1'],
        ['Form', `${now.form >= 0 ? '+' : ''}${now.form.toFixed(0)}`, `${now.form_pct >= 0 ? '+' : ''}${now.form_pct?.toFixed(0)}% of fitness · ${ZONE_SHORT[zoneNow] ?? ''}`, ZONE_COLOR[zoneNow]],
        ['Ramp rate', f.ramp_rate != null ? `${f.ramp_rate >= 0 ? '+' : ''}${f.ramp_rate.toFixed(1)}` : '–', 'fitness change per week', '#f7c76a'],
      ].map(([k, v, sub, c]) => (
        <Card key={k} span={3}><div className="muted" style={{ fontSize: 12 }}>{k}</div>
          <div className="big" style={{ color: c, marginTop: 4 }}>{v}</div><div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{sub}</div></Card>
      ))}
    </div>

    <Card title="Fitness, fatigue & form" right={<>
      <span style={{ color: '#5ef2c4' }}>━</span> fitness <span style={{ color: '#ff8fb1' }}>┅</span> fatigue <span style={{ color: 'rgba(255,255,255,.35)' }}>▮</span> daily load
      {P.length > 0 && <> · <span style={{ color: '#5ef2c4', opacity: .6 }}>╌</span> planned</>} · hover for a day</>}>
      <div ref={ref} style={{ position: 'relative' }} onPointerLeave={() => setHover(null)}>
        <svg width={w} height={H1 + H2 + 26} style={{ display: 'block', cursor: 'crosshair', touchAction: 'none' }} onPointerMove={onMove}>
          {/* ---- top: fitness & fatigue ---- */}
          {[0, .25, .5, .75, 1].map(q => <g key={q}>
            <line x1={PAD.l} x2={PAD.l + iw} y1={Y1(yMax * q)} y2={Y1(yMax * q)} stroke="rgba(255,255,255,.05)" />
            <text x={PAD.l - 8} y={Y1(yMax * q) + 4} textAnchor="end" fontSize={11} fontFamily="Geist Mono" fill="#8b8b97">{Math.round(yMax * q)}</text></g>)}
          {all.map((r, i) => r.load > 0 && <rect key={i} x={X(i) - 1.5} y={PAD.t + ih1 - (r.load / loadMax) * ih1 * .35} width={3}
            height={(r.load / loadMax) * ih1 * .35} fill={r.projected ? 'rgba(255,255,255,.12)' : 'rgba(255,255,255,.2)'} rx={1} />)}
          {P.length > 0 && <rect x={X(S.length - 1)} y={PAD.t} width={X(n - 1) - X(S.length - 1)} height={ih1} fill="rgba(255,255,255,.025)" />}
          <path d={line('fitness', S) + ` L${X(S.length - 1)} ${Y1(0)} L${X(0)} ${Y1(0)}Z`} fill="rgba(94,242,196,.08)" />
          <path d={line('fitness', S)} stroke="#5ef2c4" strokeWidth={2} fill="none" />
          <path d={line('fatigue', S)} stroke="#ff8fb1" strokeWidth={1.5} fill="none" strokeDasharray="3 3" />
          {P.length > 0 && <>
            <path d={line('fitness', [now, ...P], S.length - 1)} stroke="#5ef2c4" strokeWidth={2} fill="none" strokeDasharray="5 4" opacity={.6} />
            <path d={line('fatigue', [now, ...P], S.length - 1)} stroke="#ff8fb1" strokeWidth={1.5} fill="none" strokeDasharray="2 4" opacity={.6} />
            <text x={X(S.length - 1) + 6} y={PAD.t + 12} fontSize={10.5} fontFamily="Geist" fill="#8b8b97">planned</text>
          </>}
          <text x={PAD.l + iw + 10} y={Y1(now.fitness) + 4} fontSize={11} fontFamily="Geist" fill="#5ef2c4">fitness {now.fitness.toFixed(0)}</text>
          <text x={PAD.l + iw + 10} y={Y1(now.fatigue) + (now.fatigue > now.fitness ? -6 : 16)} fontSize={11} fontFamily="Geist" fill="#ff8fb1">fatigue {now.fatigue.toFixed(0)}</text>

          {/* ---- bottom: form % with zones ---- */}
          <g transform={`translate(0 ${H1 + 8})`}>
            {f.zones.map((z: any) => {
              const top = Y2(Math.min(z.to, fHi)), bot = Y2(Math.max(z.from, fLo))
              return <g key={z.key}>
                <rect x={PAD.l} y={top} width={iw} height={bot - top} fill={ZONE_COLOR[z.key]} opacity={h?.zone === z.key ? .2 : .09} />
                <text x={PAD.l + iw + 10} y={(top + bot) / 2 + 4} fontSize={11} fontFamily="Geist" fill={ZONE_COLOR[z.key]}>{ZONE_SHORT[z.key]}</text>
              </g>
            })}
            {[-30, -10, 0, 5, 20].map(v => <text key={v} x={PAD.l - 8} y={Y2(v) + 4} textAnchor="end" fontSize={10.5} fontFamily="Geist Mono" fill="#8b8b97">{v > 0 ? '+' : ''}{v}%</text>)}
            <line x1={PAD.l} x2={PAD.l + iw} y1={Y2(0)} y2={Y2(0)} stroke="rgba(255,255,255,.18)" />
            <path d={formPath(S)} stroke="#fff" strokeWidth={1.8} fill="none" strokeLinejoin="round" />
            {P.length > 0 && <path d={formPath([now, ...P], S.length - 1)} stroke="#fff" strokeWidth={1.8} fill="none" strokeDasharray="5 4" opacity={.55} />}
            <text x={PAD.l + 4} y={14} fontSize={11} fontFamily="Geist" fill="#8b8b97">form, % of fitness</text>
            {ticks.map(([d, i]) => <text key={d} x={X(i)} y={ih2 + 24} textAnchor={i === 0 ? 'start' : 'middle'} fontSize={11} fontFamily="Geist" fill="#8b8b97">
              {fd(d, { month: 'short', ...(d.slice(5, 7) === '01' || i === 0 ? { year: '2-digit' } : {}) })}</text>)}
          </g>

          {h && <g pointerEvents="none">
            <line x1={X(hover!)} x2={X(hover!)} y1={PAD.t} y2={H1 + 8 + ih2 + 6} stroke="rgba(255,255,255,.5)" strokeDasharray="2 3" />
            <circle cx={X(hover!)} cy={Y1(h.fitness)} r={4.5} fill="#07070a" stroke="#5ef2c4" strokeWidth={2} />
            <circle cx={X(hover!)} cy={Y1(h.fatigue)} r={4} fill="#07070a" stroke="#ff8fb1" strokeWidth={2} />
            {h.form_pct != null && <circle cx={X(hover!)} cy={H1 + 8 + Y2(h.form_pct)} r={4.5} fill="#07070a" stroke={ZONE_COLOR[h.zone]} strokeWidth={2.5} />}
          </g>}
        </svg>

        {h && (() => {
          const left = X(hover!), flip = left > w - 270
          const items = h.projected ? h.planned : h.activities
          return (
            <div style={{ position: 'absolute', top: 8, left: flip ? left - 252 : left + 14, width: 238, pointerEvents: 'none', padding: '10px 12px',
              borderRadius: 12, background: 'rgba(12,12,16,.94)', border: '1px solid rgba(255,255,255,.12)', fontSize: 12.5, lineHeight: 1.6 }}>
              <div className="muted" style={{ fontSize: 11.5 }}>{fd(h.date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })} · week {isoWeekNo(h.date)}{h.projected ? ' · planned' : ''}</div>
              <div className="row" style={{ gap: 14, margin: '4px 0' }}>
                <span><span className="muted">Fitness</span> <b className="mono" style={{ color: '#5ef2c4' }}>{h.fitness.toFixed(1)}</b></span>
                <span><span className="muted">Fatigue</span> <b className="mono" style={{ color: '#ff8fb1' }}>{h.fatigue.toFixed(1)}</b></span>
              </div>
              <div><span className="muted">Form</span> <b className="mono">{h.form >= 0 ? '+' : ''}{h.form.toFixed(1)}</b>
                {h.form_pct != null && <span className="muted"> ({h.form_pct >= 0 ? '+' : ''}{h.form_pct.toFixed(0)}%)</span>}
                {h.zone && <span style={{ color: ZONE_COLOR[h.zone] }}> · {ZONE_SHORT[h.zone]}</span>}</div>
              <div style={{ marginTop: 4 }}><span className="muted">{h.projected ? 'Planned load' : 'Load'}</span> <b className="mono">{Math.round(h.load)}</b></div>
              {items?.length > 0 && <div style={{ marginTop: 2 }}>{items.map((a: any, i: number) => (
                <div key={i} className="muted" style={{ fontSize: 11.5 }}>{a.sport && <span className="dot" style={{ background: SPORT[a.sport]?.[1], marginRight: 6, width: 6, height: 6 }} />}{a.name} · {a.load}</div>))}</div>}
            </div>)
        })()}
      </div>
    </Card>

    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 14, marginTop: 14 }}>
      {f.zones.map((z: any) => (
        <Card key={z.key}>
          <div className="row" style={{ gap: 8 }}><span className="dot" style={{ background: ZONE_COLOR[z.key] }} /><b style={{ fontSize: 13 }}>{ZONE_SHORT[z.key]}</b></div>
          <div className="mono muted" style={{ fontSize: 11.5, margin: '4px 0' }}>{z.from <= -999 ? `below ${z.to}%` : z.to >= 999 ? `above +${z.from}%` : `${z.from > 0 ? '+' : ''}${z.from}% to ${z.to > 0 ? '+' : ''}${z.to}%`}</div>
          <div className="muted" style={{ fontSize: 12, lineHeight: 1.45 }}>{{
            transition: 'Training too little to hold fitness: fine after a race, not for long.',
            fresh: 'Rested and sharp: where you want to be on race day.',
            neutral: 'Maintaining: not much stimulus, not much fatigue.',
            productive: 'Fitness is being built: where most training weeks should sit.',
            risk: 'Fatigue far above fitness: recover before adding more.',
          }[z.key as string]}</div>
        </Card>
      ))}
      <Card><div className="muted" style={{ fontSize: 12, lineHeight: 1.5 }}>Zones as defined by intervals.icu, using your intervals.icu training load. The dashed part is a projection from the workouts in your calendar.</div></Card>
    </div>
  </>
}
