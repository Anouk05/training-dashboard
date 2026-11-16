import { useState } from 'react'
import { Card, Loading, Seg, useApi } from '../components/ui'
import { scale } from '../components/charts'
import { fd, isoWeekNo, pace } from '../lib/util'
import { StrengthPanel } from '../components/Strength'

// Per sport: efficiency factor over time (aerobic sessions), tests done, current thresholds and the tests you can do.
const SPORTS: [string, string][] = [['run', 'Run'], ['ride', 'Bike'], ['swim', 'Swim'], ['strength', 'Strength']]
const EF_TEXT: Record<string, string> = {
  run: 'metres per heartbeat on steady runs (average HR below Z3) · higher = more speed for the same effort',
  ride: 'normalised power ÷ heart rate on steady rides (average HR below Z3) · higher = more power for the same effort',
  swim: 'metres per heartbeat on steady swims · wrist heart rate in water is unreliable, so read it as a rough trend',
}

export default function Progress({ refresh }: { refresh: number }) {
  const { data: p, error } = useApi('/progress', refresh)
  const [sport, setSport] = useState('run')
  if (!p?.sports) return <Loading error={error} />  // also while an older cached shape is replaced
  const s = p.sports[sport]

  return <>
    <div className="ph">
      <div><h1>Progress</h1><p>Are you getting fitter? Efficiency on steady sessions, and your tests over time.</p></div>
      <Seg value={sport} options={SPORTS.map(([k, n]) => [k, k === 'strength' ? n : `${n} (${p.sports[k].tests.length})`] as [string, string])} onChange={setSport} />
    </div>
    <div className="grid">
      {sport === 'strength' ? <StrengthPanel refresh={refresh} /> : <>
        <EfCard s={s} sport={sport} />
        <Card span={4} title="Thresholds" right="intervals.icu settings">
          {s.thresholds.length ? s.thresholds.map((t: any) => <div className="test" key={t.label}><span>{t.label}</span><b className="mono">{t.value}</b><span /><span /></div>)
            : <div className="muted" style={{ fontSize: 13 }}>No thresholds for this sport.</div>}
          {s.tests[0] && <div className="muted" style={{ fontSize: 12, marginTop: 12 }}>
            Last test: {s.tests[0].test}, {fd(s.tests[0].date, { day: 'numeric', month: 'short', year: 'numeric' })}</div>}
        </Card>
      </>}

      {sport !== 'strength' && <>
      <Card span={12} title="Test results" right={`${s.tests.length} test${s.tests.length === 1 ? '' : 's'}`}>
        {s.tests.length ? <table className="ttab">
          <thead><tr><th>Date</th><th>Test</th><th>Result</th><th /></tr></thead>
          <tbody>{s.tests.map((t: any, i: number) => (
            <tr key={i} className={t.id ? 'click' : ''} onClick={() => t.id && (location.hash = `workouts/${t.id}`)}>
              <td className="mono muted">{fd(t.date, { day: 'numeric', month: 'short', year: 'numeric' })}</td>
              <td>{t.test}{t.name && t.name !== t.test ? <span className="muted"> · {t.name}</span> : null}</td>
              <td>{t.results.map((r: any) => <span key={r.label} className="res"><span className="muted">{r.label}</span> <b className="mono">{r.value}</b></span>)}</td>
              <td className="muted" style={{ fontSize: 11.5 }}>{t.id ? 'open ›' : ''}</td>
            </tr>))}</tbody>
        </table> : <div className="empty">No {SPORTS.find(x => x[0] === sport)![1].toLowerCase()} tests yet. Pick one below.</div>}
      </Card>

      <Card span={12} title="Tests you can do" right={<>name the workout like the test and it's picked up · protocols in <span className="mono">{p.tests_file}</span></>}>
        <div className="topts">{s.options.map((o: any) => {
          const done = s.tests.filter((t: any) => t.test === o.name)
          return <div className="topt" key={o.id}>
            <div className="n">{o.name}</div>
            <div className="m">{o.measures}</div>
            <div className="h">{o.how}</div>
            <div className="w"><span className="muted">When</span> {o.when}</div>
            <div className="w muted">{done.length ? `Done ${done.length}× · last ${fd(done[0].date, { day: 'numeric', month: 'short' })}`
              : o.match ? 'Not done yet' : `Not logged yet · add to ${p.log_file}`}</div>
          </div>
        })}</div>
      </Card>

      </>}
      {s.repeats.length > 0 && <Repeats groups={s.repeats} />}
    </div>
  </>
}

const LOC: Record<string, [string, string]> = { outdoor: ['Outdoor', '#5ef2c4'], indoor: ['Indoor', '#8aa8ff'] }

function EfCard({ s, sport }: { s: any; sport: string }) {
  const [hover, setHover] = useState<number | null>(null)
  const all = s.ef.points as any[], unit = s.ef.unit
  const hasBoth = all.some(p => p.indoor) && all.some(p => !p.indoor)
  const [where, setWhere] = useState<'both' | 'indoor' | 'outdoor'>('both')
  const pts = where === 'both' ? all : all.filter(p => (where === 'indoor') === p.indoor)
  if (pts.length < 2) return <Card span={8} title="Efficiency factor"><div className="empty">Not enough steady {sport === 'swim' ? 'swims' : 'sessions'} with heart rate yet.</div></Card>
  const ev = pts.map(x => x.eff)
  const W = 700, H = 230, PLOT = 196
  const lo = Math.min(...ev), hi = Math.max(...ev), pad = (hi - lo) * 0.15 || 0.05
  const sc = scale(ev, W, PLOT, 24, lo - pad, hi + pad)
  // one 5-session rolling average per location, drawn through that location's own sessions
  const lines = (['outdoor', 'indoor'] as const).map(loc => {
    const idx = pts.map((p, i) => [p, i] as const).filter(([p]) => p.indoor === (loc === 'indoor')).map(([, i]) => i)
    const v = idx.map(i => ev[i])
    const d = idx.map((i, k) => { const w = v.slice(Math.max(0, k - 4), k + 1); return `${k ? 'L' : 'M'}${sc.sx(i)} ${sc.sy(w.reduce((a, b) => a + b, 0) / w.length)}` }).join('')
    return { loc, d, n: idx.length }
  }).filter(l => l.n >= 2)
  const hp = hover != null ? pts[hover] : null
  const dp = sport === 'ride' ? 2 : 3
  const labelEvery = Math.ceil(pts.length / 9)
  const stats = (where === 'both' ? (hasBoth ? ['outdoor', 'indoor'] : [all[0].indoor ? 'indoor' : 'outdoor']) : [where])
    .map(k => [k, s.ef.trend[k]] as [string, any]).filter(([, t]) => t)
  return <Card span={8} title={`Efficiency factor · ${unit}`}
    right={hasBoth ? <Seg small value={where} options={[['both', 'Both'], ['outdoor', 'Outdoor'], ['indoor', 'Indoor']]} onChange={setWhere} /> : EF_TEXT[sport]}>
    <div className="row" style={{ gap: 36, alignItems: 'flex-end', flexWrap: 'wrap' }}>
      {stats.map(([k, t]) => <div key={k}>
        <div className="muted" style={{ fontSize: 11.5, color: LOC[k][1] }}>{LOC[k][0]} · last 3 sessions</div>
        <div className="big" style={{ marginTop: 2 }}>{t.last.toFixed(dp)}<small>{unit}</small></div>
        {t.pct != null && <div className="mono" style={{ fontSize: 12, color: t.pct >= 0 ? '#5ef2c4' : '#f7c76a' }}>
          {t.pct > 0 ? '+' : ''}{t.pct}% <span className="muted">vs {t.before.toFixed(dp)} ({fd(t.since, { day: 'numeric', month: 'short' })})</span></div>}
      </div>)}
    </div>
    <div style={{ position: 'relative' }} onMouseLeave={() => setHover(null)}>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', height: 240 }}>
        {lines.map(l => <path key={l.loc} d={l.d} stroke={LOC[l.loc][1]} strokeWidth={2} fill="none" opacity={.85} />)}
        {pts.map((r, i) => { const c = LOC[r.indoor ? 'indoor' : 'outdoor'][1]
          return <g key={r.id} style={{ cursor: 'pointer' }} onClick={() => (location.hash = `workouts/${r.id}`)} onMouseEnter={() => setHover(i)}>
          {hover === i && <line x1={sc.sx(i)} x2={sc.sx(i)} y1={8} y2={PLOT} stroke="rgba(255,255,255,.18)" strokeDasharray="2 3" />}
          <circle cx={sc.sx(i)} cy={sc.sy(ev[i])} r={12} fill="transparent" />
          <circle cx={sc.sx(i)} cy={sc.sy(ev[i])} r={hover === i ? 6 : 3.5} fill={hover === i ? c : 'rgba(7,7,10,.6)'} stroke={c} strokeWidth={1.2} />
          {((i % labelEvery === 0 && pts.length - 1 - i >= labelEvery / 2) || i === pts.length - 1) && <>
            <text x={sc.sx(i)} y={PLOT + 16} textAnchor="middle" fill={hover === i ? '#fff' : '#8b8b97'} fontSize={10.5} fontFamily="Geist">{fd(r.date, { day: 'numeric', month: 'short' })}</text>
            <text x={sc.sx(i)} y={PLOT + 30} textAnchor="middle" fill="#6b6b76" fontSize={9.5} fontFamily="Geist Mono">W{isoWeekNo(r.date)} ’{r.date.slice(2, 4)}</text></>}
        </g> })}
      </svg>
      {hp && (() => {
        const left = (sc.sx(hover!) / W) * 100, flip = left > 65
        return <div className="eftip" style={{ [flip ? 'right' : 'left']: `${flip ? 100 - left + 2 : left + 2}%` }}>
          <div className="muted" style={{ fontSize: 11.5 }}>{fd(hp.date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })} · week {isoWeekNo(hp.date)}</div>
          <div style={{ fontWeight: 500, margin: '2px 0 4px' }}>{hp.name} <span style={{ color: LOC[hp.indoor ? 'indoor' : 'outdoor'][1], fontSize: 11.5 }}>{hp.indoor ? 'indoor' : 'outdoor'}</span></div>
          <div><b className="mono" style={{ fontSize: 16 }}>{hp.eff.toFixed(dp)}</b> <span className="muted">{unit}</span></div>
          <div className="muted">{[hp.pace ? `${pace(hp.pace)}/km` : hp.power ? `${Math.round(hp.power)} W` : null, hp.avg_hr ? `${Math.round(hp.avg_hr)} bpm` : null,
            `${Math.round(hp.minutes)}′`, hp.decoupling != null ? `drift ${Number(hp.decoupling).toFixed(1)}%` : null].filter(Boolean).join(' · ')}</div>
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>click to open</div>
        </div>
      })()}
    </div>
    <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.5 }}>{EF_TEXT[sport]}. Dots are sessions, lines are 5-session averages
      {hasBoth ? ', kept apart for indoor and outdoor because heat and no airflow raise your heart rate indoors' : ''}.
      {Object.keys(s.ef.skipped || {}).length > 0 && <><br />Only steady aerobic sessions count. Left out: {Object.entries(s.ef.skipped)
        .sort((a: any, b: any) => b[1] - a[1]).map(([k, v]) => `${v} × ${k}`).join(' · ')}.</>}</div>
  </Card>
}

function Repeats({ groups }: { groups: any[] }) {
  const [sel, setSel] = useState(groups[0].id)
  const g = groups.find(x => x.id === sel) || groups[0]
  return <Card span={12} title="Same session over time" right={<Seg small value={g.id} options={groups.map(x => [x.id, `${x.name} (${x.count})`] as [string, string])} onChange={setSel} />}>
    <div className="mults" style={{ gridTemplateColumns: `repeat(${Math.min(6, Math.max(1, g.repeats.length))},1fr)` }}>
      {g.repeats.slice(-12).map((r: any) => (
        <div className="mult" key={r.id} style={{ cursor: 'pointer' }} onClick={() => (location.hash = `workouts/${r.id}`)}>
          <div className="k">{fd(r.date, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })} · W{isoWeekNo(r.date)}</div>
          <div className="v">{r.pace ? pace(r.pace) : r.power ? `${r.power.toFixed(0)} W` : '–'}</div>
          <div className="k">{r.avg_hr ? `${r.avg_hr.toFixed(0)} bpm` : 'no HR'} · EF {r.eff ?? '–'}</div>
          <div className="k" style={{ marginTop: 6, color: 'var(--soft)' }}>{r.name}</div>
        </div>
      ))}
    </div>
  </Card>
}
