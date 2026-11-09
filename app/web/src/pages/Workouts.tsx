import { useState } from 'react'
import { Analysis, Card, Loading, prefetch, useApi } from '../components/ui'
import { api, DEFAULT_ZONE_NAMES, dur, fd, pace, SPORT, ZONE_COLORS } from '../lib/util'
import HrChart, { chartMode, timeInZones } from '../components/HrChart'
import FuelCheck from '../components/FuelCheck'

export default function Workouts({ refresh, id }: { refresh: number; id?: string }) {
  const { data: list, error } = useApi('/activities?limit=80', refresh)
  if (!list) return <Loading error={error} />
  const sel = id || list[0]?.id
  return (
    <div className="grid">
      <Card span={3} title="Recent workouts" right={`${list.length} shown`}>
        <div className="alist">{list.map((a: any) => (
          <div key={a.id} className={`aitem ${a.id === sel ? 'on' : ''}`} onClick={() => (location.hash = `workouts/${a.id}`)}
            onMouseEnter={() => prefetch(`/activity/${a.id}`)}>
            <div className="ic2" style={{ background: SPORT[a.sport][1] }}>{SPORT[a.sport][0][0]}</div>
            <div style={{ minWidth: 0 }}><div className="n">{a.name}</div><div className="m">{fd(a.date, { day: 'numeric', month: 'short' })} · {dur(a.minutes)}</div></div>
            <div className="r">{a.load || ''}</div>
          </div>
        ))}</div>
      </Card>
      <div className="s9 sub" style={{ display: 'grid', gap: 14, gridTemplateColumns: 'repeat(9,1fr)', alignContent: 'start' }}>
        {sel && <Detail id={sel} key={sel} preview={list.find((a: any) => a.id === sel)} />}
      </div>
    </div>
  )
}

function Detail({ id, preview }: { id: string; preview?: any }) {
  const { data: fetched, error, setData } = useApi(`/activity/${id}`)
  const [hl, setHl] = useState<number | null>(null) // section hovered in the table, highlighted on the chart
  if (!fetched && !preview) return <div style={{ gridColumn: 'span 9' }}><Loading error={error} /></div>
  // until the details arrive, render the header from the list entry
  const d = fetched ?? { summary: preview, points: [], polyline: [], reps: [], earlier: [], planned: null, workout: null, loading: true }
  const a = d.summary, pts = d.points as any[]
  const mode = chartMode(pts)
  const isPower = mode === 'power'
  const floors: number[] = (isPower ? d.power_zones?.floors : d.zones?.floors) ?? []
  const tiz = mode && floors.length ? timeInZones(pts, floors, isPower ? 3 : 1) : null
  const tizTotal = tiz ? tiz.reduce((x, y) => x + y, 0) || 1 : 1

  let map = null
  if (d.polyline.length > 2) {
    const la = d.polyline.map((p: number[]) => p[0]), lo = d.polyline.map((p: number[]) => p[1])
    const mnla = Math.min(...la), mxla = Math.max(...la), mnlo = Math.min(...lo), mxlo = Math.max(...lo)
    const k = Math.cos((mnla * Math.PI) / 180), sc = Math.min(260 / ((mxlo - mnlo) * k || 1), 200 / (mxla - mnla || 1))
    const path = d.polyline.map((p: number[], i: number) => `${i ? 'L' : 'M'}${(20 + (p[1] - mnlo) * k * sc).toFixed(1)} ${(220 - (p[0] - mnla) * sc).toFixed(1)}`).join('')
    map = <svg width="100%" viewBox="0 0 300 240" style={{ display: 'block', height: 240 }}>
      <defs><filter id="mg"><feGaussianBlur stdDeviation="4" /></filter></defs>
      <path d={path} stroke="#ff8f5a" strokeWidth={6} fill="none" opacity={.35} filter="url(#mg)" />
      <path d={path} stroke="#ffb27a" strokeWidth={2.2} fill="none" strokeLinejoin="round" /></svg>
  }

  // sections as split by intervals.icu (warm-up, efforts, recoveries); fall back to auto-detected run reps
  const sections = (d.sections ?? []) as any[]
  const reps = (sections.length ? sections.filter(x => x.type === 'WORK').map(x => ({ from: x.start / 60, to: x.end / 60 })) : d.reps) as any[]
  const hlSec = hl != null ? sections[hl] : null
  const repSummary = reps.length > 1 && (() => {
    const p = reps.map(r => r.pace), h = reps.map(r => r.avg_hr).filter(Boolean)
    const spread = Math.round((Math.max(...p) - Math.min(...p)) * 60)
    return `${reps.length} reps at ${pace(Math.min(...p))}–${pace(Math.max(...p))}/km (${spread} s spread), heart rate ${Math.min(...h)}–${Math.max(...h)} bpm.`
      + (spread <= 6 ? ' Even pacing.' : ` The fastest rep was ${spread} s quicker than the slowest; aim for a tighter spread.`)
  })()

  return <>
    <Card span={9} title={`${fd(a.date, { weekday: 'long', day: 'numeric', month: 'long' })} · ${SPORT[a.sport][0]}`}
      right={d.workout ? <span className="mono">{d.workout.id} · {d.repeat_number}{['st', 'nd', 'rd'][d.repeat_number - 1] || 'th'} time</span> : null}>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 16 }}>
        <div className="big" style={{ fontSize: 30 }}>{a.name}</div>
        <div className="chips">{d.workout?.targets?.pace && <span className="chip">Target <b>{d.workout.targets.pace}</b></span>}
          {a.compliance > 0 && <span className={`chip ${a.compliance >= 80 && a.compliance <= 120 ? 'good' : ''}`}>Plan compliance <b>{Math.round(a.compliance)}%</b></span>}
          {a.te && <span className="chip">{a.te.replace(/_/g, ' ').toLowerCase()}</span>}</div>
      </div>
      <div className="stats">
        <div><div className="k">{a.km ? 'Distance' : 'Sport'}</div><div className="v">{a.km ? <>{a.km.toFixed(2)}<small>km</small></> : SPORT[a.sport][0]}</div></div>
        <div><div className="k">Time</div><div className="v">{dur(a.minutes)}</div></div>
        <div><div className="k">{a.sport === 'run' ? 'Avg pace' : 'Avg power'}</div><div className="v">{a.sport === 'run' ? <>{pace(a.pace)}<small>/km</small></> : a.power ? <>{a.power.toFixed(0)}<small>W</small></> : '–'}</div></div>
        <div><div className="k">Avg HR</div><div className="v">{a.avg_hr ? <>{a.avg_hr.toFixed(0)}<small>bpm</small></> : '–'}</div></div>
        <div><div className="k">Load</div><div className="v">{a.load || '–'}</div></div>
        <div><div className="k">RPE</div><div className="v">{a.rpe ? <>{a.rpe.toFixed(0)}<small>/10</small></> : '–'}</div></div>
      </div>
    </Card>

    <Card span={9} title={isPower ? 'Power · no heart rate recorded' : 'Heart rate'}
      right={isPower ? (d.power_zones ? <>power zones: intervals.icu · FTP {d.power_zones.ftp} W{d.power_zones.np ? ` · normalised ${d.power_zones.np} W` : ''} · hover for details</> : 'hover for details')
        : d.zones ? <>zones: {d.zones.source} {d.zones.sport.toLowerCase()} · LTHR {d.zones.lthr}{reps.length ? ` · dashed = ${sections.length ? 'efforts' : 'reps'}` : ''} · hover for details</> : 'hover for details'}>
      {pts.length ? <HrChart points={pts} zones={d.zones} powerZones={d.power_zones} sport={a.sport} reps={reps}
          highlight={hlSec ? { from: hlSec.start / 60, to: hlSec.end / 60 } : null} sections={sections} onSection={setHl} />
        : <div className="empty" style={{ height: 300, display: 'grid', placeItems: 'center' }}>{d.loading ? (error ? `Couldn't load details: ${error}` : 'Loading heart rate…') : 'No second-by-second data for this activity.'}</div>}
    </Card>

    {d.analysis && <Card span={5} title="Coach analysis" right={<span className="who" style={{ display: 'inline-flex' }}><i />Claude</span>}>
      <Analysis a={d.analysis} /></Card>}
    <NotesCard d={d} span={d.analysis ? 4 : 9} onSaved={setData} repSummary={repSummary || null} />
    {a.sport !== 'str' && <FuelCheck aid={a.id} span={9} />}

    {tiz && <Card span={map ? 6 : 9} title={isPower ? 'Time in power zones' : 'Time in zones'} right="from the samples, with the zones above">
      {floors.map((_, i) => `Z${i + 1} ${((isPower ? d.power_zones?.names : d.zones?.names) ?? DEFAULT_ZONE_NAMES)[i] ?? ''}`).map((n, i) => (
        <div key={n} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 90px', alignItems: 'center', gap: 12, fontSize: 12.5, marginBottom: 8 }}>
          <span style={{ color: ZONE_COLORS[i] }}>{n}<span className="muted mono" style={{ fontSize: 10.5 }}> {Math.round(floors[i])}{isPower ? 'W' : ''}+</span></span>
          <div style={{ height: 10, borderRadius: 6, background: 'rgba(255,255,255,.05)' }}>
            <div style={{ width: `${(tiz[i] / tizTotal) * 100}%`, height: '100%', borderRadius: 6, background: ZONE_COLORS[i] }} /></div>
          <span className="mono" style={{ textAlign: 'right' }}>{dur(tiz[i])} <span className="muted">{Math.round((tiz[i] / tizTotal) * 100)}%</span></span>
        </div>))}
    </Card>}

    {map && <Card span={3} title="Route" right={a.km ? `${a.km.toFixed(1)} km` : ''}>{map}</Card>}

    {sections.length > 0 && <SectionsCard sections={sections} sport={a.sport} onHover={setHl} active={hl} />}

    {!sections.length && reps.length > 0 && <Card span={9} title="Reps" right="from second-by-second data">
      <table className="t"><thead><tr><th></th><th className="n">Dist</th><th className="n">Pace</th><th className="n">Avg HR</th><th className="n">Max</th></tr></thead>
        <tbody>{reps.map((r, i) => <tr key={i}><td>Rep {i + 1}</td><td className="n">{r.km.toFixed(2)} km</td><td className="n">{pace(r.pace)}/km</td><td className="n">{r.avg_hr ?? '–'} bpm</td><td className="n">{r.max_hr ?? '–'}</td></tr>)}</tbody></table>
    </Card>}

    {d.earlier.length > 0 && <Card span={9} title="Same session, earlier" right={d.workout?.name}>
      <div className="mults">{d.earlier.map((e: any) => (
        <div className="mult" key={e.id} style={{ cursor: 'pointer' }} onClick={() => (location.hash = `workouts/${e.id}`)}>
          <div className="k">{fd(e.date, { day: 'numeric', month: 'short', year: '2-digit' })}</div>
          <div className="v">{e.pace ? pace(e.pace) : e.power ? `${e.power.toFixed(0)} W` : dur(e.minutes)}<small className="muted" style={{ fontSize: 12 }}>{e.pace ? ' /km' : ''}</small></div>
          <div className="k">{e.avg_hr ? `${e.avg_hr.toFixed(0)} bpm · ` : ''}{e.name}</div>
        </div>
      ))}</div>
    </Card>}
  </>
}

/** Your notes on the workout: shown and edited here, saved as the activity description in intervals.icu. */
function NotesCard({ d, span, onSaved, repSummary }: { d: any; span: number; onSaved: (x: any) => void; repSummary: string | null }) {
  const a = d.summary
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(a.notes || '')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const canEdit = !!a.icu_id && !d.loading
  const save = async () => {
    setSaving(true); setErr(null)
    try {
      onSaved(await api(`/activity/${a.id}/notes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ notes: text }) }))
      setEditing(false)
    } catch (e) { setErr(`Couldn't save to intervals.icu: ${e}`) }
    setSaving(false)
  }
  return (
    <Card span={span} title="Your notes" right={editing ? 'saves to intervals.icu' : a.feel ? `felt ${a.feel.toLowerCase()}` : ''}>
      {d.planned && <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>Planned: <b style={{ color: 'var(--soft)' }}>{d.planned.name}</b>{d.planned.summary ? ` · ${d.planned.summary}` : ''}</div>}
      {editing ? <>
        <textarea className="field steps" style={{ fontFamily: 'inherit', fontSize: 13.5 }} rows={Math.max(4, text.split('\n').length + 1)} autoFocus
          value={text} onChange={e => setText(e.target.value)} placeholder="How did it feel? Legs, breathing, sleep, food…"
          onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save(); if (e.key === 'Escape') { setEditing(false); setText(a.notes || '') } }} />
        {err && <div style={{ color: '#ff9b8a', fontSize: 12.5, marginTop: 8 }}>{err}</div>}
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8, marginTop: 10 }}>
          <button className="btn" onClick={() => { setEditing(false); setText(a.notes || '') }}>Cancel</button>
          <button className={`btn pri ${saving || text === (a.notes || '') ? 'off' : ''}`} disabled={saving || text === (a.notes || '')} onClick={save}>{saving ? 'Saving…' : 'Save'}</button>
        </div>
      </> : <>
        <div className={`notes ${a.notes ? '' : 'muted'}`} style={{ whiteSpace: 'pre-line', cursor: canEdit ? 'text' : 'default' }}
          onClick={() => canEdit && setEditing(true)}>{a.notes || (canEdit ? 'No notes yet. Click to add how it went.' : 'Notes can be added once this workout is in intervals.icu.')}</div>
        {canEdit && <button className="link" style={{ marginTop: 8 }} onClick={() => setEditing(true)}>{a.notes ? 'Edit notes' : '+ Add notes'}</button>}
      </>}
      {!d.analysis && !editing && <><p style={{ fontSize: 13.5, lineHeight: 1.6, color: '#d6d6dd', margin: '14px 0 10px' }}>
        {repSummary || 'Not analysed yet. The evening run of the analyze-workout skill adds a coach report here.'}</p>
        <div className="who"><i />Auto-check</div></>}
    </Card>
  )
}

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`

/** The workout's sections from intervals.icu: one row per warm-up, effort and recovery. Hover a row to see it on the chart. */
function SectionsCard({ sections, sport, onHover, active }: { sections: any[]; sport: string; onHover: (i: number | null) => void; active: number | null }) {
  const isRun = sport === 'run'
  const name = (x: any, i: number) => x.label || (x.type === 'WORK' ? 'Effort'
    : i === 0 ? 'Warm-up' : i === sections.length - 1 ? 'Cool-down' : 'Recovery')
  const main = sections.filter(x => x.type === 'WORK').sort((a, b) => (b.end - b.start) - (a.end - a.start))[0]
  return (
    <Card span={9} title="Sections" right="as split in intervals.icu · hover a row to see it on the chart">
      {main && main.end - main.start >= 1200 && (
        <div className="row" style={{ gap: 26, marginBottom: 16, flexWrap: 'wrap' }}>
          <div><div className="muted" style={{ fontSize: 11.5 }}>Main effort · {clock(main.end - main.start)}</div>
            <div className="big" style={{ fontSize: 26 }}>{main.avg_watts ?? '–'}<small>W avg</small></div></div>
          <div><div className="muted" style={{ fontSize: 11.5 }}>Heart rate</div>
            <div className="big" style={{ fontSize: 26 }}>{main.avg_hr ?? '–'}<small>bpm avg · max {main.max_hr ?? '–'}</small></div></div>
          {main.last20_hr && <div><div className="muted" style={{ fontSize: 11.5 }}>Last 20 minutes</div>
            <div className="big" style={{ fontSize: 26, color: '#5ef2c4' }}>{Math.round(main.last20_hr)}<small>bpm · {main.last20_watts} W</small></div></div>}
          {main.intensity && <div><div className="muted" style={{ fontSize: 11.5 }}>Intensity</div>
            <div className="big" style={{ fontSize: 26 }}>{main.intensity}<small>% FTP</small></div></div>}
        </div>)}
      <table className="t sections" onMouseLeave={() => onHover(null)}>
        <thead><tr><th>Section</th><th className="n">Time</th><th className="n">Duration</th>
          <th className="n">Avg W</th><th className="n">NP</th><th className="n">Avg HR</th><th className="n">Max HR</th>
          <th className="n">{isRun ? 'Pace' : 'Cadence'}</th><th className="n">% FTP</th></tr></thead>
        <tbody>{sections.map((x, i) => (
          <tr key={i} className={`${x.type === 'WORK' ? 'work' : ''} ${active === i ? 'on' : ''}`} onMouseEnter={() => onHover(i)}>
            <td><span className="dot" style={{ background: x.type === 'WORK' ? '#ff9f6b' : 'rgba(255,255,255,.25)', marginRight: 8 }} />{name(x, i)}</td>
            <td className="n muted">{clock(x.start)}–{clock(x.end)}</td>
            <td className="n">{clock(x.end - x.start)}</td>
            <td className="n">{x.avg_watts ?? '–'}</td><td className="n muted">{x.np ?? '–'}</td>
            <td className="n">{x.avg_hr ?? '–'}</td><td className="n muted">{x.max_hr ?? '–'}</td>
            <td className="n">{isRun ? (x.speed ? pace(1000 / x.speed / 60) : '–') : (x.cadence ?? '–')}</td>
            <td className="n">{x.intensity ?? '–'}</td>
          </tr>))}</tbody>
      </table>
    </Card>
  )
}
