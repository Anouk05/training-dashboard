// Strength views: the weights phase, a card per exercise with its max, last session, next target and chart
// (Progress → Strength), and the session card on a gym workout. Data: Notion strength log + coach/strength.md, via /api/strength.
import { useState } from 'react'
import { Card, Loading, Seg, useApi } from './ui'
import { scale } from './charts'
import { fd } from '../lib/util'

const repsText = (r: any) => r.reps?.length ? (new Set(r.reps).size === 1 ? `${r.reps.length} × ${r.reps[0]}` : r.reps.join(', ')) : r.reps_text || '–'

export function StrengthPanel({ refresh }: { refresh: number }) {
  const { data: s, error } = useApi('/strength', refresh)
  if (!s) return <Card span={12} title="Strength"><Loading error={error} /></Card>
  const ph = s.phase
  return <>
    <Card span={12} className="sphase" title={ph ? <>Phase now · <b>{ph.code}</b> {ph.name}</> : 'Weights phase'}
      right={<>guide in <span className="mono">{s.guide_file}</span></>}>
      {ph ? <>
        <div className="sguide">
          {[['Sessions', `${s.sessions_in_phase} of ${ph.total}`], ['Per week', ph.per_week], ['Load', `${ph.load}% of max`],
            ['Sets × reps', `${ph.sets} × ${ph.reps}`], ['Rest', `${ph.rest} min`]].map(([k, v]) =>
            <div key={k}><div className="muted">{k}</div><b className="mono">{v}</b></div>)}
        </div>
        <details className="sall"><summary>All phases</summary>
          <table className="stab">
            <thead><tr><th>Phase</th><th>Period</th><th>Sessions</th><th>Per week</th><th>% of max</th><th>Sets</th><th>Reps</th><th>Rest</th></tr></thead>
            <tbody>{s.phases.map((p: any) => <tr key={p.code} className={p.code === ph.code ? 'on' : ''}>
              <td><b className="mono">{p.code}</b> <span className="muted">{p.name}</span></td><td className="muted">{p.period}</td><td>{p.total}</td>
              <td>{p.per_week}</td><td>{p.load}</td><td>{p.sets}</td><td>{p.reps}</td><td>{p.rest}</td></tr>)}</tbody>
          </table>
        </details>
      </> : <div className="muted">No weights phase in the annual plan for this week.</div>}
    </Card>

    <Card span={12} title="Your exercises" right="max: yours where you entered it, otherwise estimated from your sets · dashed = max over time">
      {s.exercises.length ? <div className="sexs">{s.exercises.map((e: any) => <ExerciseCard key={e.exercise} e={e} />)}</div>
        : <div className="muted" style={{ fontSize: 13, lineHeight: 1.6 }}>Nothing logged yet. Tick your exercises on the session's
          checklist in Notion (Gym sessions), then press Sync; each exercise gets its own card here.</div>}
    </Card>

    {s.sessions.length > 0 && <Card span={12} title="Sessions" right={`${s.sessions.length} most recent`}>
      {s.sessions.map((d: any) => <SessionTable key={d.date} d={d} title />)}
    </Card>}
  </>
}

/** One exercise in the spotlight: its max, last session, next target and a chart over time. */
function ExerciseCard({ e }: { e: any }) {
  const h = e.history as any[]
  const [what, setWhat] = useState<'kg' | 'volume'>(h.some(x => x.kg) ? 'kg' : 'volume')
  const vals = h.map(x => (what === 'kg' ? x.kg : x.volume) ?? 0)
  const maxes = h.map(x => x.e1rm ?? null)
  const hi = Math.max(1, ...vals, ...(what === 'kg' ? [...maxes.filter(Boolean) as number[], e.best_1rm || 0] : []))
  const W = 300, H = 80
  const sc = scale(vals, W, H, 8, 0, hi * 1.1)
  const maxLine = what === 'kg' ? maxes.map((v, i) => v == null ? '' : `${i && maxes[i - 1] != null ? 'L' : 'M'}${sc.sx(i)} ${sc.sy(v)}`).join('') : ''
  const last = e.last, pct = e.best_1rm && last.kg ? Math.round(last.kg / e.best_1rm * 100) : null
  return <div className="sex">
    <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <div><b className="nm">{e.exercise}</b>
        <div className="smax">{e.best_1rm ? <><span className="mono">{e.max_source === 'yours' ? '' : '~'}{e.best_1rm}</span> kg max
          <span className="muted"> · {e.max_source === 'yours' ? 'yours' : 'estimated'}</span></> : <span className="muted">bodyweight / no max yet</span>}</div></div>
      {h.length > 1 && <Seg small value={what} options={[['kg', 'Load'], ['volume', 'Volume']]} onChange={setWhat} />}
    </div>
    {h.length > 1 ? <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', height: H, margin: '8px 0 4px' }}>
      {maxLine && <path d={maxLine} stroke="rgba(255,255,255,.35)" strokeWidth={1.2} strokeDasharray="3 3" fill="none" />}
      <path d={sc.d} stroke="#c79bff" strokeWidth={2} fill="none" />
      {vals.map((v, i) => <circle key={i} cx={sc.sx(i)} cy={sc.sy(v)} r={3} fill="#07070a" stroke="#c79bff" strokeWidth={1.5} />)}
    </svg> : <div className="sone muted">First session logged; the chart starts with the next one.</div>}
    <div className="srow"><span className="muted">Last · {fd(last.date, { day: 'numeric', month: 'short' })}</span>
      <span className="mono">{repsText(last)}{last.kg ? ` @ ${last.kg} kg` : ''}{last.rpe ? ` · RPE ${last.rpe}` : ''}{pct ? ` · ${pct}%` : ''}</span></div>
    {e.next && <div className="srow next"><span className="muted">Next</span><span className="mono">{e.next.text}</span></div>}
    {e.next?.why && <div className="swhy muted">{e.next.why}</div>}
  </div>
}

export function SessionTable({ d, title = false }: { d: any; title?: boolean }) {
  return <div className="ssess">
    {title && <div className="hd"><b>{fd(d.date, { weekday: 'short', day: 'numeric', month: 'short' })}</b>
      <span className="muted">{d.phase ?? ''}{d.minutes ? ` · ${d.minutes}′` : ''} · {d.sets} sets · {d.volume.toLocaleString('en')} kg volume</span>
      {d.activity_id && <a className="muted" href={`#workouts/${d.activity_id}`}>open ›</a>}</div>}
    <table className="stab">
      <thead><tr><th>Exercise</th><th>Sets × reps</th><th>Load</th><th>RPE</th><th>Volume</th><th>Est. max</th><th /></tr></thead>
      <tbody>{d.exercises.map((r: any) => <tr key={r.exercise}><td>{r.exercise}</td><td className="mono">{repsText(r)}</td>
        <td className="mono">{r.kg != null ? `${r.kg} kg` : '–'}</td><td className="mono">{r.rpe ?? '–'}</td>
        <td className="mono">{r.volume != null ? r.volume.toLocaleString('en') : '–'}</td>
        <td className="mono muted">{r.e1rm ? `~${r.e1rm}` : '–'}</td><td className="muted">{r.note}</td></tr>)}</tbody>
    </table>
  </div>
}

/** On a gym workout's page: what you logged in Notion for that day. */
export function StrengthSessionCard({ date, span }: { date: string; span: number }) {
  const { data: d } = useApi(`/strength/day/${date}`, date)
  if (!d) return null
  return <Card span={span} title="Strength session" right={d.exercises.length ? `${d.phase ?? ''} · ${d.sets} sets · ${d.volume.toLocaleString('en')} kg volume` : 'from your Notion log'}>
    {d.exercises.length ? <SessionTable d={d} /> : <div className="muted" style={{ fontSize: 13 }}>
      Nothing logged for this day yet. Tick the exercises on the session's checklist in Notion and press Sync.</div>}
  </Card>
}
