// Annual training plan (ATP) in Friel's format: one row per week with races, priority, period, volume,
// weights phase and an X per ability for swim, bike and run. Data: data/plans/atp-*.yaml + the intervals.icu calendar.
import { useState } from 'react'
import { Card, Loading, useApi } from '../components/ui'
import { addDays, api, fd } from '../lib/util'

const ABILITIES: [string, string][] = [['AE', 'Aerobic endurance'], ['MF', 'Muscular force'], ['SS', 'Speed skills'],
  ['ME', 'Muscular endurance'], ['AC', 'Aerobic capacity'], ['SP', 'Sprint power'], ['T', 'Testing']]
const SPORTS: [string, string, string][] = [['swim', 'Swim', 'var(--swim)'], ['bike', 'Bike', 'var(--ride)'], ['run', 'Run', 'var(--run)']]
const WEIGHTS: Record<string, string> = { AA: 'Anatomical adaptation', MT: 'Muscular transition', MS: 'Maximum strength', SM: 'Strength maintenance' }
export const PERIOD_COLOR = (n: string) => n === 'Prep' ? '#4a4a5c' : n.startsWith('Base') ? '#3a4a6b' : n.startsWith('Build') ? '#2f7a66'
  : n === 'Peak' ? '#b8862e' : n === 'Race' ? '#d9603f' : '#2c2c36'
const PRI_COLOR: Record<string, string> = { A: '#ff7a59', B: '#f7c76a', C: '#8aa8ff' }

export const PERIODS = ['Prep', 'Base 1', 'Base 2', 'Base 3', 'Build 1', 'Build 2', 'Peak', 'Race', 'Transition']

type Changes = Partial<{ period: string; volume: number | null; tss: number | null; weights: string; swim: string[]; bike: string[]; run: string[]; note: string }>

export default function Atp({ refresh }: { refresh: number }) {
  const { data: p, error, setData } = useApi('/atp', refresh)
  const [sel, setSel] = useState<string[]>([])
  const [anchor, setAnchor] = useState<number | null>(null)
  const [saveErr, setSaveErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(0)
  if (!p) return <Loading error={error} />
  if (!p.weeks) return <div className="empty">No annual plan yet. Ask Claude to build one: it's saved in data/plans/atp-&lt;season&gt;.yaml.</div>

  const today = new Date().toISOString().slice(0, 10)
  const isNow = (w: any) => w.start <= today && today < addDays(w.start, 7)
  const maxV = Math.max(...p.weeks.map((w: any) => w.volume || 0)), maxT = Math.max(...p.weeks.map((w: any) => w.tss || 0))

  // optimistic: change the table right away, then save to the plan file
  const save = (starts: string[], changes: Changes) => {
    const before = p
    const weeks = p.weeks.map((w: any) => starts.includes(w.start) ? { ...w, ...changes } : w)
    setData({ ...p, weeks, planned_hours: weeks.reduce((a: number, w: any) => a + (w.volume || 0), 0),
      planned_tss: weeks.reduce((a: number, w: any) => a + (w.tss || 0), 0) })
    setSaveErr(null); setSaving(n => n + 1)
    api('/atp/weeks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ starts, changes }) })
      .then(d => { setData(d); if (d.notes_error) setSaveErr(`Plan saved, but the intervals.icu week notes weren't updated (${d.notes_error})`) }).catch(e => { setData(before); setSaveErr(`Couldn't save: ${e}`) }).finally(() => setSaving(n => n - 1))
  }
  const toggle = (w: any, sport: string, a: string) =>
    save([w.start], { [sport]: w[sport]?.includes(a) ? w[sport].filter((x: string) => x !== a) : [...(w[sport] || []), a] })
  const pick = (i: number, shift: boolean) => {
    const s = p.weeks[i].start
    if (shift && anchor != null) {
      const [a, b] = [Math.min(anchor, i), Math.max(anchor, i)]
      setSel(p.weeks.slice(a, b + 1).map((w: any) => w.start))
    } else {
      setSel(sel.includes(s) ? sel.filter(x => x !== s) : [...sel, s]); setAnchor(i)
    }
  }
  const selWeeks = p.weeks.filter((w: any) => sel.includes(w.start))

  return <>
    <div className="grid" style={{ marginBottom: 14 }}>
      <Card span={4} title="Season goals" right={`${p.season}${p.athlete ? ' · ' + p.athlete : ''}`}>
        <ol className="atp-list">{p.goals?.map((g: string, i: number) => <li key={i}>{g}</li>)}</ol>
      </Card>
      <Card span={5} title="Training objectives" right="your limiters">
        <ol className="atp-list">{p.objectives?.map((g: string, i: number) => <li key={i}>{g}</li>)}</ol>
      </Card>
      <Card span={3} title="Annual volume">
        <div className="mono" style={{ fontSize: 30, letterSpacing: '-.02em' }}>{p.annual_volume}<span className="muted" style={{ fontSize: 13 }}> h</span>
          {p.annual_tss && <span style={{ fontSize: 18, marginLeft: 14 }}>{(p.annual_tss / 1000).toFixed(1)}K<span className="muted" style={{ fontSize: 12 }}> TSS</span></span>}</div>
        <div className="muted" style={{ fontSize: 12, lineHeight: 1.6, marginTop: 6 }}>
          planned {Math.round(p.planned_hours * 10) / 10} h · {p.planned_tss?.toLocaleString('en')} TSS<br />done {p.done_hours} h · {p.done_load?.toLocaleString('en')} load
        </div>
      </Card>
    </div>

    <Card title={<>Annual training plan{saving > 0 && <span className="muted" style={{ marginLeft: 10, fontSize: 12 }}>saving…</span>}</>}
      right={<>weights: {Object.entries(WEIGHTS).map(([k, v]) => <span key={k} title={v} style={{ marginLeft: 8 }}><b className="mono">{k}</b> {v.toLowerCase()}</span>)}</>}>
      {saveErr && <div className="atp-err">{saveErr}</div>}
      {sel.length > 0 && <SelectionBar weeks={selWeeks} onApply={c => save(sel, c)} onClear={() => setSel([])} />}
      <div className="atp-wrap">
        <table className="atp">
          <thead>
            <tr>
              <th colSpan={8} />
              {SPORTS.map(([k, n, c]) => <th key={k} colSpan={ABILITIES.length} className="sport" style={{ color: c, borderBottomColor: c }}>{n}</th>)}
            </tr>
            <tr>
              <th title="Click to select, shift-click to select a range">Week</th><th>Mon.</th><th className="l">Races · focus</th><th>Pri.</th><th className="l">Period</th><th>Hours</th><th title="Training stress score target; green = load done (intervals.icu)">TSS</th>
              <th className="rot"><span>Weights</span></th>
              {SPORTS.map(([k]) => ABILITIES.map(([a, n]) => <th key={k + a} className={`rot ${a === 'AE' ? 'first' : ''}`} title={n}><span>{n}</span></th>))}
            </tr>
          </thead>
          <tbody>
            {p.weeks.map((w: any, i: number) => {
              const prev = p.weeks[i - 1], newPeriod = !prev || prev.period !== w.period
              const past = addDays(w.start, 7) <= today
              const race = w.races[0], picked = sel.includes(w.start)
              return (
                <tr key={w.start} className={`${isNow(w) ? 'now' : ''} ${past ? 'past' : ''} ${newPeriod ? 'np' : ''} ${picked ? 'sel' : ''}`}>
                  <td className="mono wk" onClick={e => pick(i, e.shiftKey)} title="Select week (shift-click for a range)">{String(w.week).padStart(2, '0')}</td>
                  <td className="mono muted">{fd(w.start, { day: '2-digit', month: '2-digit' })}</td>
                  <td className="l races">{w.races.map((r: any) => <div key={r.date + r.name}>
                    <span className="dot" style={{ background: PRI_COLOR[r.priority] }} />{r.name}
                    <span className="muted"> · {fd(r.date, { weekday: 'short', day: 'numeric' })}{r.not_in_calendar ? ' · not in calendar' : ''}</span></div>)}
                    <NoteCell note={w.note} onSave={note => note !== (w.note || '') && save([w.start], { note })} />
                  </td>
                  <td>{race && <b style={{ color: PRI_COLOR[race.priority] }}>{race.priority}</b>}</td>
                  <td className="l">
                    <select className="period" style={{ background: PERIOD_COLOR(w.period) }} value={w.period}
                      onChange={e => save([w.start], { period: e.target.value })}>
                      {PERIODS.map(x => <option key={x}>{x}</option>)}
                    </select>
                  </td>
                  <NumCell value={w.volume} done={w.done_hours} max={maxV} limit={40} what="Hours"
                    onSave={v => save([w.start], { volume: v })} onError={setSaveErr} />
                  <NumCell value={w.tss} done={w.done_load} max={maxT} limit={2000} what="TSS" whole
                    onSave={v => save([w.start], { tss: v })} onError={setSaveErr} />
                  <td className="wt">
                    <select className="wsel mono" value={w.weights || ''} title={WEIGHTS[w.weights]} onChange={e => save([w.start], { weights: e.target.value })}>
                      <option value="">–</option>{Object.keys(WEIGHTS).map(k => <option key={k} value={k}>{k}</option>)}
                    </select>
                  </td>
                  {SPORTS.map(([k, n, c]) => ABILITIES.map(([a, an]) => <td key={k + a} className={`x ${a === 'AE' ? 'first' : ''}`}
                    onClick={() => toggle(w, k, a)} title={`${n} · ${an}`}>
                    {w[k]?.includes(a) ? <span className="mark" style={{ background: c }} /> : <span className="mark off" />}</td>))}
                </tr>)
            })}
          </tbody>
        </table>
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 12, lineHeight: 1.6 }}>
        Click a period, hours, TSS, weights or ability cell to change that week, or the focus text to edit it. Select weeks by their number
        (shift-click for a range) to change several at once. Hours and TSS are the week's targets; green is what you did (hours, and load from intervals.icu). Races come from your intervals.icu calendar.
        Changes are saved to the weekly notes in intervals.icu and to <span className="mono" style={{ color: 'var(--soft)' }}>{p.file}</span>.
      </div>
    </Card>
  </>
}

function NumCell({ value, done, max, limit, what, whole = false, onSave, onError }: { value: number | null; done?: number | null; max: number;
  limit: number; what: string; whole?: boolean; onSave: (v: number | null) => void; onError: (e: string) => void }) {
  const [edit, setEdit] = useState(false)
  const commit = (raw: string) => {
    setEdit(false)
    const v = raw.trim(), n = v === '' ? null : Number(v.replace(',', '.'))
    if (n !== null && (isNaN(n) || n < 0 || n > limit)) return onError(`${what} must be a number between 0 and ${limit}.`)
    if (n !== value) onSave(n === null ? null : whole ? Math.round(n) : n)
  }
  return <td className="vol" onClick={() => !edit && setEdit(true)}>
    {edit ? <input autoFocus className="volin mono" defaultValue={value ?? ''} onBlur={e => commit(e.target.value)}
      onKeyDown={e => { const t = e.target as HTMLInputElement
        if (e.key === 'Escape') t.value = t.defaultValue  // blur then saves nothing
        if (e.key === 'Enter' || e.key === 'Escape') t.blur() }} />
      : value != null ? <>
        <span className="vbar" style={{ width: `${(value / max) * 100}%` }} />
        <span className="mono">{value}</span>
        {done != null && <span className="mono done" title="done">{done}</span>}
      </> : <span className="muted">—</span>}
  </td>
}

function NoteCell({ note, onSave }: { note?: string; onSave: (n: string) => void }) {
  const [edit, setEdit] = useState(false)
  if (edit) return <input autoFocus className="notein" defaultValue={note || ''} placeholder="Focus for this week"
    onBlur={e => { setEdit(false); onSave(e.target.value.trim()) }}
    onKeyDown={e => { const t = e.target as HTMLInputElement
      if (e.key === 'Escape') t.value = t.defaultValue
      if (e.key === 'Enter' || e.key === 'Escape') t.blur() }} />
  return <span className={`muted note ${note ? '' : 'empty'}`} onClick={() => setEdit(true)}>{note || '+ focus'}</span>
}

function SelectionBar({ weeks, onApply, onClear }: { weeks: any[]; onApply: (c: Changes) => void; onClear: () => void }) {
  const [period, setPeriod] = useState('')
  const [volume, setVolume] = useState('')
  const [tss, setTss] = useState('')
  const [weights, setWeights] = useState('-')
  const apply = () => {
    const c: Changes = {}
    if (period) c.period = period
    if (volume.trim()) c.volume = Number(volume.replace(',', '.'))
    if (tss.trim()) c.tss = Math.round(Number(tss))
    if (weights !== '-') c.weights = weights
    if (Object.keys(c).length) onApply(c)
    setPeriod(''); setVolume(''); setTss(''); setWeights('-')
  }
  const first = weeks[0], last = weeks[weeks.length - 1]
  return <div className="atp-bar">
    <b>{weeks.length} week{weeks.length === 1 ? '' : 's'}</b>
    <span className="muted">{first && fd(first.start, { day: 'numeric', month: 'short' })}{weeks.length > 1 ? ' – ' + fd(addDays(last.start, 6), { day: 'numeric', month: 'short' }) : ''}</span>
    <select className="field" value={period} onChange={e => setPeriod(e.target.value)}>
      <option value="">Period…</option>{PERIODS.map(x => <option key={x}>{x}</option>)}
    </select>
    <input className="field mono" style={{ width: 80 }} value={volume} onChange={e => setVolume(e.target.value)} placeholder="Hours" />
    <input className="field mono" style={{ width: 80 }} value={tss} onChange={e => setTss(e.target.value)} placeholder="TSS" />
    <select className="field" value={weights} onChange={e => setWeights(e.target.value)}>
      <option value="-">Weights…</option><option value="">None</option>{Object.entries(WEIGHTS).map(([k, v]) => <option key={k} value={k}>{k} · {v}</option>)}
    </select>
    <button className="btn pri" onClick={apply}>Apply</button>
    {SPORTS.map(([k, n]) => <button key={k} className="btn" title={`Copy ${n.toLowerCase()} abilities of the first selected week to the others`}
      onClick={() => onApply({ [k]: first[k] || [] })}>Copy {n.toLowerCase()} focus</button>)}
    <button className="btn" onClick={onClear}>Clear</button>
  </div>
}
