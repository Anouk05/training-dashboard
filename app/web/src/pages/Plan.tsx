import { Card, Loading, Seg, useApi } from '../components/ui'
import { scale } from '../components/charts'
import { fd, SPORT } from '../lib/util'
import Atp from './Atp'


export default function Plan({ refresh, view }: { refresh: number; view?: string }) {
  return view === 'history' ? <History refresh={refresh} /> : <ThisSeason refresh={refresh} />
}

function ViewSwitch({ v }: { v: 'season' | 'history' }) {
  return <Seg value={v} options={[['season', 'This season'], ['history', 'Past seasons']]}
    onChange={x => (location.hash = x === 'season' ? 'plan' : 'plan/history')} />
}

function ThisSeason({ refresh }: { refresh: number }) {
  return <>
    <div className="ph">
      <div><h1>This season</h1><p>Annual training plan: periods, weekly volume, weights and abilities per week · built with the plan-season skill</p></div>
      <div className="row"><ViewSwitch v="season" /></div>
    </div>
    <Atp refresh={refresh} />
  </>
}

const MIX: Record<string, string> = { row: 'var(--row)', run: 'var(--run)', ride: 'var(--ride)', str: 'var(--str)', other: '#555' }

function Mix({ mix }: { mix: Record<string, number> }) {
  const e = Object.entries(mix).filter(([, v]) => v > 0)
  return <>
    <div className="mixbar">{e.map(([k, v]) => <div key={k} style={{ flex: v, background: MIX[k] }} />)}</div>
    <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{e.filter(([, v]) => v >= 5).map(([k, v]) => `${SPORT[k]?.[0] ?? k} ${v}%`).join(' · ')}</div>
  </>
}

const resultText = (r: any) => {
  const when = r.date ? ` (${fd(r.date, { day: 'numeric', month: 'short' })}${r.end && r.end !== r.date ? '–' + fd(r.end, { day: 'numeric' }) : ''})` : ''
  return `${r.label}${r.time ? ' · ' + r.time : ''}${when}`
}

function History({ refresh }: { refresh: number }) {
  const { data, error } = useApi('/seasons', refresh)
  const { data: atp } = useApi('/atp', refresh)
  if (!data) return <Loading error={error} />
  const seas = data.seasons.filter((x: any) => x.kind === 'season'), offs = data.seasons.filter((x: any) => x.kind === 'off')
  const planned = atp?.weeks?.filter((w: any) => w.volume != null) ?? []
  const rows = [...seas, ...(planned.length ? [{ label: 'This season', avg_h: Math.round(atp.planned_hours / planned.length * 10) / 10,
    peak_h: Math.max(...planned.map((w: any) => w.volume)), plan: true, load_complete: false }] : [])]
  const mxh = Math.max(...rows.map((r: any) => r.peak_h))
  const range = (x: any) => `${fd(x.from, { day: 'numeric', month: 'short', year: 'numeric' })} – ${fd(x.to, { day: 'numeric', month: 'short', year: 'numeric' })}`
  const hm = data.half_marathons
  const hp = scale(hm.map((h: any) => -h.minutes), 600, 120, 22, -Math.max(...hm.map((h: any) => h.minutes)) - 4, -Math.min(...hm.map((h: any) => h.minutes)) + 4)
  const gain = hm.length >= 2 ? hm[hm.length - 2].minutes - hm[hm.length - 1].minutes : 0

  return <>
    <div className="ph">
      <div><h1>Past seasons</h1><p>Seasons run from 1 September to the first week of July · {data.duplicates.count} duplicate recordings ({data.duplicates.hours} h) removed · load from intervals.icu since March 2025</p></div>
      <div className="row"><ViewSwitch v="history" /></div>
    </div>
    <div className="grid" style={{ marginBottom: 14 }}>
      <Card span={8} title="Average week per season" right={<><span style={{ color: '#5ef2c4' }}>▮</span> average · ┄ busiest week · <span style={{ color: '#5ef2c4' }}>┆</span> this season's plan</>}>
        <div style={{ display: 'flex', gap: 10 }}>{rows.map((r: any) => (
          <div key={r.label} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
            <div style={{ height: 180, width: '100%', display: 'flex', alignItems: 'end', justifyContent: 'center', position: 'relative' }}>
              <div style={{ width: '34%', height: `${r.avg_h / mxh * 100}%`, borderRadius: '8px 8px 3px 3px', background: r.plan ? 'transparent' : 'linear-gradient(#7de8c8,#3fbf99)', border: r.plan ? '1.5px dashed rgba(94,242,196,.6)' : undefined }} />
              <div style={{ position: 'absolute', left: '18%', right: '18%', bottom: `${r.peak_h / mxh * 100}%`, borderTop: '1.5px dotted rgba(255,255,255,.45)' }} />
            </div>
            <div className="mono" style={{ fontSize: 15 }}>{r.avg_h.toFixed(1)}<span className="muted" style={{ fontSize: 11 }}> h/wk</span></div>
            <div className="muted" style={{ fontSize: 11.5 }}>{r.label}{r.plan ? ' · plan' : ''}</div>
            <div className="mono muted" style={{ fontSize: 11 }}>{r.load_complete ? `load ${r.avg_load}/wk` : 'load —'}</div>
          </div>
        ))}</div>
        <div className="muted" style={{ fontSize: 11.5, marginTop: 12 }}>Your intervals.icu history starts in March 2025, so older seasons have no comparable load. intervals.icu can import older Garmin activities (Settings → Garmin Connect → download history) to fill this in.</div>
      </Card>
      <Card span={4} title="Half marathon, over the years" right="all your 21 km runs">
        <svg width="100%" viewBox="0 0 600 120" style={{ display: 'block', height: 130, overflow: 'visible' }}>
          <path d={hp.d} stroke="rgba(94,242,196,.5)" strokeWidth={1.5} fill="none" strokeDasharray="4 4" />
          {hm.map((h: any, i: number) => <g key={i}><circle cx={hp.sx(i)} cy={hp.sy(-h.minutes)} r={7} fill="#07070a" stroke="#5ef2c4" strokeWidth={2} />
            <text x={hp.sx(i)} y={hp.sy(-h.minutes) - 14} textAnchor="middle" fill="#fff" fontSize={13} fontFamily="Geist Mono">{h.time}</text></g>)}
        </svg>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--mute)', marginTop: 8 }}>
          {hm.map((h: any) => <span key={h.date} style={{ textAlign: 'center' }}>{fd(h.date, { day: 'numeric', month: 'short', year: '2-digit' })}<br />{h.place}</span>)}</div>
        {gain > 0 && <div style={{ fontSize: 13, marginTop: 14, color: 'var(--soft)' }}><b style={{ color: '#5ef2c4' }}>−{Math.floor(gain)}:{String(Math.round((gain % 1) * 60)).padStart(2, '0')}</b> on your previous half marathon.</div>}
      </Card>
    </div>

    <div className="seasons">
      {[...seas].reverse().map((x: any) => (
        <div className="card scard" key={x.label}>
          <div className="lab">{x.label}</div><div className="muted" style={{ fontSize: 12 }}>{range(x)} · {Math.round(x.weeks)} weeks</div>
          <div className="kv">
            <div><div className="k">Avg week</div><div className="v">{x.avg_h.toFixed(1)}<small>h</small></div></div>
            <div><div className="k">Avg load</div><div className="v">{x.load_complete ? <>{x.avg_load}<small>/wk</small></> : <>—<small>{x.avg_load > 50 ? 'partial' : ''}</small></>}</div></div>
            <div><div className="k">Busiest week</div><div className="v">{x.peak_h}<small>h</small></div></div>
            <div><div className="k">Sessions</div><div className="v">{x.sessions}</div></div>
          </div>
          <div className="muted" style={{ fontSize: 11 }}>Sport mix</div><Mix mix={x.mix} />
          <div className="sec">Goals</div>
          <ul>{x.goals?.length ? x.goals.map((g: any, i: number) => <li key={i} className={g.achieved ? '' : 'goal'}>{g.goal ?? g}{g.achieved === false ? ' · not achieved' : ''}</li>)
            : <li className="goal muted">Not recorded yet</li>}</ul>
          <div className="sec">Results</div>
          <ul>{x.results.length ? x.results.map((r: any, i: number) => <li key={i}>{resultText(r)}</li>) : <li className="goal muted">No races found</li>}</ul>
        </div>
      ))}
      <div className="card scard">
        <div className="lab" style={{ fontSize: 15 }}>Between seasons</div><div className="muted" style={{ fontSize: 12 }}>Summers and the gap before this season</div>
        {[...offs].reverse().map((x: any) => <div key={x.label}>
          <div className="sec plain"><span>{x.label}</span><span className="muted" style={{ fontSize: 11.5 }}>{x.avg_h} h/wk</span></div>
          <div className="muted" style={{ fontSize: 11.5, margin: '2px 0 4px' }}>{range(x)}</div>
          {x.sessions > 0 && <Mix mix={x.mix} />}
          {x.results.length > 0 && <ul>{x.results.map((r: any, i: number) => <li key={i}>{resultText(r)}</li>)}</ul>}
        </div>)}
      </div>
    </div>
    <div className="muted" style={{ fontSize: 12, marginTop: 14 }}>Goals live in <span className="mono" style={{ color: 'var(--soft)' }}>data/plans/seasons.yaml</span>. Tell Claude what you aimed for each season, and each goal gets marked as achieved or not.</div>
  </>
}
