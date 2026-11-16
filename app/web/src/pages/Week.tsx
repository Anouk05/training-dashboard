import { useState, type DragEvent } from 'react'
import { Card, Draft, Loading, Md, RATING, useApi, ZBar } from '../components/ui'
import { Donut } from '../components/charts'
import WorkoutEditor from '../components/WorkoutEditor'
import { addDays, api, dur, fd, isoWeekNo, SPORT } from '../lib/util'

const BASIC = new Set(['AE', 'MF', 'SS']), ADV = new Set(['ME', 'AC', 'SP'])
const ABILITY_NAMES: Record<string, string> = { AE: 'Aerobic endurance (basic)', MF: 'Muscular force (basic)', SS: 'Speed skills (basic)',
  ME: 'Muscular endurance (advanced)', AC: 'Aerobic capacity (advanced)', SP: 'Sprint power (advanced)', T: 'Testing',
  AA: 'Weights: anatomical adaptation', MT: 'Weights: muscular transition', MS: 'Weights: maximum strength', SM: 'Weights: strength maintenance' }

export default function Week({ refresh, start }: { refresh: number; start?: string }) {
  const { data: w, error, setData } = useApi(`/week${start ? `?start=${start}` : ''}`, `${start}-${refresh}`)
  const [drag, setDrag] = useState<any | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [over, setOver] = useState<string | null>(null)
  const [saving, setSaving] = useState<Set<string>>(new Set())
  const [editing, setEditing] = useState<any | null>(null)
  const [open, setOpen] = useState<Set<string>>(new Set())
  if (!w) return <Loading error={error} />

  const keyOf = (p: any) => String(p.event_id ?? p.index)

  // Optimistic move: the tile jumps to the new day at once; the server call runs in the background
  // and the week is replaced with the server's answer (or rolled back if it fails).
  const drop = async (to: string) => {
    setOver(null)
    const p = drag
    setDrag(null)
    if (!p || p.date === to) return
    const before = w
    const k = keyOf(p)
    setData({ ...w, days: w.days.map((d: any) => ({
      ...d, planned: d.date === to ? [...d.planned.filter((x: any) => keyOf(x) !== k), { ...p, date: to }]
        : d.planned.filter((x: any) => keyOf(x) !== k),
    })) })
    setSaving(s => new Set(s).add(k))
    setErr(null)
    try {
      const res = await api('/week/move', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ week_start: w.start, to, event_id: p.event_id, index: p.index }),
      })
      setData(res)
    } catch (e) {
      setData(before)
      setErr(`Couldn't move “${p.name}”: ${e}`)
    }
    setSaving(s => { const n = new Set(s); n.delete(k); return n })
  }

  // Time of day for a planned workout ("" clears it); saved in intervals.icu, so it shows on the watch too.
  const setTime = async (p: any, time: string) => {
    const k = keyOf(p)
    setSaving(s => new Set(s).add(k))
    setErr(null)
    try {
      setData(await api(`/event/${p.event_id}/time`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ week_start: w.start, time: time || null }),
      }))
    } catch (e) {
      setErr(`Couldn't set the time of “${p.name}”: ${e}`)
    }
    setSaving(s => { const n = new Set(s); n.delete(k); return n })
  }

  const onOver = (e: DragEvent, date: string) => {
    if (!drag) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (over !== date) setOver(date)
  }
  const onLeave = (e: DragEvent, date: string) => {
    // ignore leave events fired when moving between a column's own children
    if (e.currentTarget.contains(e.relatedTarget as Node)) return
    setOver(o => (o === date ? null : o))
  }

  const sports: [string, string][] = [['run', 'Run'], ['ride', 'Ride'], ['swim', 'Swim'], ['str', 'Strength']]
  const mxh = Math.max(1, ...sports.map(([k]) => w.by_sport[k].plan_hours)) * 1.15
  const mxl = Math.max(1, ...sports.map(([k]) => w.by_sport[k].plan_load)) * 1.15
  const it = w.intensity

  return <>
    <div className="ph">
      <div><h1>Week {isoWeekNo(w.start)}</h1><p>{w.focus || 'No weekly note'}{w.source === 'intervals' ? ' · planned in intervals.icu, drag to move (syncs to your watch)' : ''}<Draft show={w.status === 'draft'} label="draft plan" /></p>
        {err && <p style={{ color: '#ff9b8a' }}>{err}</p>}</div>
      <div className="row" style={{ gap: 14 }}>
        <div className="stepper">
          <button onClick={() => (location.hash = `week/${addDays(w.start, -7)}`)}>‹</button>
          <b>{fd(w.start, { day: 'numeric', month: 'short' })} – {fd(addDays(w.start, 6), { day: 'numeric', month: 'short' })}</b>
          <button onClick={() => (location.hash = `week/${addDays(w.start, 7)}`)}>›</button>
        </div>
        <a className="btn" href="https://intervals.icu/calendar" target="_blank" rel="noreferrer">Open intervals.icu ↗</a>
      </div>
    </div>

    <div className="wcols">{w.days.map((d: any) => (
      <div key={d.date} className={`wcol ${d.is_today ? 'today' : ''} ${over === d.date ? 'drop' : ''}`}
        onDragOver={e => onOver(e, d.date)} onDragLeave={e => onLeave(e, d.date)}
        onDrop={e => { e.preventDefault(); drop(d.date) }}>
        <div className={`hd lvl-${d.intensity ?? 'rest'}`} title={d.intensity ? `${d.intensity} day` : 'rest day'}>
          <span><b>{fd(d.date)}</b>{d.intensity === 'hard' && <i className="dayhard">hard</i>}</span><span>{fd(d.date, { day: 'numeric', month: 'short' })}</span></div>
        {d.notes.map((n: any, i: number) => <div key={i} className={`daynote ${n.race ? 'race' : ''}`}>{n.race ? `◆ ${n.race.replace('RACE_', '')} race · ` : ''}{n.name}</div>)}
        {d.done.map((a: any) => (
          <div className="tile" key={a.id} onClick={() => (location.hash = `workouts/${a.id}`)}>
            <div className="k" style={{ color: SPORT[a.sport][1] }}><span className="dot" style={{ background: SPORT[a.sport][1] }} />{SPORT[a.sport][0]} · done</div>
            <div className="n">{a.name}</div>
            <div className="m">{dur(a.minutes)}{a.km ? ` · ${a.km.toFixed(1)} km` : ''}{a.avg_hr ? ` · ${a.avg_hr.toFixed(0)} bpm` : ''} · load {a.load}</div>
            <ZBar zones={a.zones} />
            {a.analysis && <div className="ana"><span className="dot" style={{ background: RATING[a.analysis.rating]?.[1] ?? '#8b8b97' }} />{a.analysis.title}</div>}
            {(a.rpe || a.notes) && <div className="note">{a.rpe ? `RPE ${a.rpe.toFixed(0)}/10` : ''}{a.feel ? ` · ${a.feel.toLowerCase()}` : ''}
              {a.notes && <div style={{ marginTop: 3, color: 'var(--mute)' }}>{a.notes.length > 70 ? a.notes.slice(0, 70) + '…' : a.notes}</div>}</div>}
          </div>
        ))}
        {d.planned.map((p: any) => (
          <div className={`tile plan ${drag && keyOf(drag) === keyOf(p) ? 'dragging' : ''} ${saving.has(keyOf(p)) ? 'saving' : ''}`} key={keyOf(p)} draggable
            onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', keyOf(p)); setDrag(p) }}
            onDragEnd={() => { setOver(null); setDrag(null) }}
            onClick={() => setOpen(o => { const n = new Set(o), k = keyOf(p); n.has(k) ? n.delete(k) : n.add(k); return n })}>
            <span className="grip">⋮⋮</span>
            <div className="k" style={{ color: SPORT[p.sport][1] }}><span className="dot" style={{ background: SPORT[p.sport][1] }} /><span>{SPORT[p.sport][0]} · {p.event_id ? <PlanTime time={p.time} open={open.has(keyOf(p))} onSet={t => setTime(p, t)} /> : 'planned'}</span></div>
            <div className="n">{p.name}</div>
            <div className="m">{p.sub}{p.sub ? ' · ' : ''}load ~{p.load}</div>
            {p.abilities?.length > 0 && <div className="abil">{p.abilities.map((a: string) =>
              <span key={a} className={`ab ${ADV.has(a) ? 'adv' : BASIC.has(a) ? 'basic' : 'other'}`} title={ABILITY_NAMES[a] ?? a}>{a}</span>)}</div>}
            <ZBar zones={p.zones} />
            {open.has(keyOf(p)) ? <>
              {p.summary && <div className="m wdesc">{p.summary}</div>}
              {p.event_id && <button className="btn editw" onClick={e => { e.stopPropagation(); setEditing(p) }}>Edit</button>}
            </> : <div className="more">click for details</div>}
          </div>
        ))}
        {drag && over === d.date && drag.date !== d.date && <div className="ghost">Move {drag.name} here</div>}
        {!d.done.length && !d.planned.length && !d.notes.length && !(drag && over === d.date) && <div className="muted" style={{ fontSize: 12.5, padding: 2 }}>Rest day</div>}
        {w.source === 'intervals' && !drag && <button className="addw" onClick={() => setEditing({ date: d.date, name: '', sport: 'run', type: 'Run', description: '', steps: [], minutes: 0, load: 0 })}>+ Add workout</button>}
      </div>
    ))}</div>

    <div className="grid" style={{ marginTop: 14 }}>
      <Card span={4} title="Volume & load by sport" right={<>done · <span style={{ color: '#fff' }}>▮</span> planned</>}>
        <div className="row" style={{ gap: 28, marginBottom: 16 }}>
          <div><div className="muted" style={{ fontSize: 11.5 }}>Hours</div><div className="big" style={{ fontSize: 26 }}>{w.totals.hours}<small>/ {w.totals.plan_hours} h</small></div></div>
          <div><div className="muted" style={{ fontSize: 11.5 }}>Load</div><div className="big" style={{ fontSize: 26 }}>{w.totals.load}<small>/ {w.totals.plan_load}</small></div></div>
        </div>
        <div className="bars2">{sports.map(([k, n]) => {
          const s = w.by_sport[k], c = SPORT[k][1]
          return (
            <div className="r" key={k}><span>{n}</span>
              <div><div className="tr"><i style={{ width: `${s.hours / mxh * 100}%`, background: c }} />{s.plan_hours > 0 && <u style={{ left: `${s.plan_hours / mxh * 100}%` }} />}</div>
                <div className="mono muted" style={{ fontSize: 10.5, marginTop: 4 }}>{s.hours} / {s.plan_hours} h</div></div>
              <div><div className="tr"><i style={{ width: `${s.load / mxl * 100}%`, background: c, opacity: .65 }} />{s.plan_load > 0 && <u style={{ left: `${s.plan_load / mxl * 100}%` }} />}</div>
                <div className="mono muted" style={{ fontSize: 10.5, marginTop: 4 }}>{s.load} / {s.plan_load} load</div></div>
            </div>
          )
        })}</div>
      </Card>

      {w.split?.target && <SplitCard s={w.split} />}

      <Card span={4} title="Intensity · last 7 days" right="heart rate, else power · target 80 / 20">
        <div className="row" style={{ gap: 22 }}>
          <Donut parts={[[it.easy, 'var(--z2)'], [it.moderate, 'var(--z3)'], [it.hard, 'var(--z4)']]} label={`${Math.round(it.easy * 100)}%`} sub="easy" />
          <div style={{ fontSize: 13, lineHeight: 2 }}>
            <div><span className="dot" style={{ background: 'var(--z2)' }} /> Easy (Z1–2) <b className="mono">{Math.round(it.easy * 100)}%</b></div>
            <div><span className="dot" style={{ background: 'var(--z3)' }} /> Moderate (Z3) <b className="mono">{Math.round(it.moderate * 100)}%</b></div>
            <div><span className="dot" style={{ background: 'var(--z4)' }} /> Hard (Z4–5) <b className="mono">{Math.round(it.hard * 100)}%</b></div>
            {(it.from_power > 0 || it.unmeasured > 0) && <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.4, marginTop: 6 }}>
              {it.from_power > 0 && <>{it.from_power} ride{it.from_power > 1 ? 's' : ''} without heart rate counted by power zones.<br /></>}
              {it.unmeasured > 0 && <>{it.unmeasured} session{it.unmeasured > 1 ? 's' : ''} without heart rate or power not counted.</>}</div>}
          </div>
        </div>
      </Card>

      <Card span={4} title="Coach rules" right="coach/rules.yaml">
        {w.rules.map((r: any, i: number) => (
          <div className="rule" key={i}><span className={`ic ${r.ok && !r.warn ? 'ok' : r.ok ? 'warn' : 'bad'}`}>{r.ok && !r.warn ? '✓' : '!'}</span><div><Md text={r.text} /></div></div>
        ))}
      </Card>
    </div>
    {editing && <WorkoutEditor workout={editing} weekStart={w.start} onClose={() => setEditing(null)}
      onSaved={week => { setData(week); setEditing(null) }} />}
  </>
}

/** The tile's header reads "Run · planned", or "Run · 07:30" once it has a time of day. On an open tile that part
 * becomes clickable ("set time" / the time) and turns into a time field; emptying the field clears the time. */
function PlanTime({ time, open, onSet }: { time: string | null; open: boolean; onSet: (t: string) => void }) {
  const [edit, setEdit] = useState(false)
  if (edit) return <input className="ptime-in" type="time" step={300} defaultValue={time ?? ''} autoFocus
    onClick={e => e.stopPropagation()}
    onBlur={e => { setEdit(false); if (e.target.value !== (time ?? '')) onSet(e.target.value) }}
    onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') setEdit(false) }} />
  const label = time ?? (open ? 'set time' : 'planned')
  return <span className={`ptime ${time ? 'set' : ''} ${open ? 'can' : ''}`} title={open ? 'Time of day (empty = any time)' : undefined}
    onClick={open ? e => { e.stopPropagation(); setEdit(true) } : undefined}>{label}</span>
}

/** Share of swim, bike and run time this week (weights left out), planned and done, against the annual plan's target. */
function SplitCard({ s }: { s: any }) {
  const rows: [string, string, string][] = [['swim', 'Swim', 'var(--swim)'], ['bike', 'Bike', 'var(--ride)'], ['run', 'Run', 'var(--run)']]
  const anyDone = Object.values(s.done).some((v: any) => v > 0)
  return <Card span={4} title="Sport split" right={<>planned · <span style={{ color: '#fff' }}>┃</span> target</>}>
    <div className="split">{rows.map(([k, n, c]) => {
      const pl = s.planned[k], tg = s.target[k], off = pl - tg
      return <div className="r" key={k}>
        <span>{n}</span>
        <div className="tr"><i style={{ width: `${pl}%`, background: c }} /><u style={{ left: `${tg}%` }} /></div>
        <span className="mono">{pl}%<small className="muted"> / {tg}%</small></span>
        <span className={`mono d ${Math.abs(off) <= 5 ? 'ok' : 'off'}`}>{off > 0 ? '+' : ''}{off}</span>
      </div>
    })}</div>
    <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.5, marginTop: 12 }}>
      Share of swim + bike + run time{s.weights_hours ? `; ${s.weights_hours} h of weights left out` : ''}.
      {anyDone && <> Done so far: {rows.map(([k, n]) => `${n.toLowerCase()} ${s.done[k]}%`).join(' · ')}.</>}<br />
      Target: {s.why}. Change it under <span className="mono">sport_split</span> in the plan file.
    </div>
  </Card>
}
