import { Blocks, Card, Draft, Loading, Md, RATING, useApi, ZBar } from '../components/ui'
import { Line, scale } from '../components/charts'
import { dur, fd, pace, SPORT } from '../lib/util'
import { FuelTarget } from './Fuel'

const VERDICT_COLOR: Record<string, string> = { Primed: '#5ec8f2', 'Ready for quality': '#5ef2c4', 'Easy day': '#f7c76a', Rest: '#ff7a7a' }
const ICON: Record<string, string> = { ok: '✓', warn: '~', bad: '!' }

export function Readiness({ r }: { r: any }) {
  if (r.score == null) return <div className="empty">Not enough recovery data for today yet. Sync your watch.</div>
  const c = VERDICT_COLOR[r.verdict]
  return <>
    <div className="row" style={{ marginBottom: 4 }}>
      <span style={{ width: 12, height: 12, borderRadius: '50%', background: c, boxShadow: `0 0 14px ${c}` }} />
      <span className="muted" style={{ fontSize: 12 }}>{r.score}/100</span>
    </div>
    <div className="verdict">{r.verdict}</div>
    <div className="muted" style={{ fontSize: 13.5, marginBottom: 14 }}>{r.advice}</div>
    {r.reasons.map((x: any, i: number) => (
      <div className="why" key={i}><span className={`ic ${x.status}`}>{ICON[x.status]}</span><div>{x.title}<small>{x.detail}</small></div></div>
    ))}
  </>
}

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

export default function Today({ refresh }: { refresh: number }) {
  const { data: t, error } = useApi('/today', refresh)
  if (!t) return <Loading error={error} />
  const r = t.readiness, s = t.session, wk = t.week
  // second line of the greeting: what recovery says about today, highlighted part in <em>
  const headline: Record<string, [string, string, string]> = {
    Primed: ['Recovery looks ', 'strong', '.'], 'Ready for quality': ['Recovered enough to ', 'train hard', '.'],
    'Easy day': ['A day to ', 'keep easy', '.'], Rest: ['Your body is asking for ', 'rest', '.'] }
  const hl = headline[r.verdict]

  const L = t.load as any[]
  const mx = Math.max(...L.map(x => Math.max(x.fitness, x.fatigue))) * 1.1
  const last = L[L.length - 1]
  const form = last.fitness - last.fatigue

  return <>
    <div className="ph"><div>
      <h1>{greeting()}{t.name ? `, ${t.name}` : ''}.<br />{hl ? <>{hl[0]}<em>{hl[1]}</em>{hl[2]}</> : 'Here is your day.'}</h1>
      <p>{fd(t.date, { weekday: 'long', day: 'numeric', month: 'long' })}{wk.focus ? ` · ${wk.focus}` : ''}<Draft show={wk.status === 'draft'} label="draft plan" /></p>
    </div></div>
    <div className="grid">
      <Card span={4} title="Readiness" right="vs your 30-day baseline"><Readiness r={r} /></Card>

      <Card span={5} title={s?.is_today ? "Today's session" : 'Next session'} right={<span className="mono">{s?.workout}</span>}
        onClick={() => (location.hash = 'week')}>
        {s ? <>
          <div className="sess-title">{s.name}</div>
          <div className="muted" style={{ fontSize: 13 }}>{!s.is_today && fd(s.date, { weekday: 'long', day: 'numeric', month: 'short' }) + ' · '}{dur(s.minutes)}{s.summary && !s.event_id ? ` · ${s.summary}` : ''}</div>
          <Blocks steps={s.steps} />
          <div className="chips">
            {s.event_id && s.summary && s.summary.split(' · ').map((x: string, i: number) => <span className="chip" key={i}><b>{x}</b></span>)}
            {s.targets.pace && <span className="chip">Pace <b>{s.targets.pace}</b></span>}
            {s.targets.power && <span className="chip">Power <b>{s.targets.power}</b></span>}
            {s.targets.hr && <span className="chip">HR <b>{s.targets.hr}</b></span>}
            {t.last_time && <span className="chip">Last time <b>{t.last_time.pace ? `${pace(t.last_time.pace)} @ ${t.last_time.avg_hr}` : fd(t.last_time.date, { day: 'numeric', month: 'short' })}</b></span>}
            <span className="chip">Est. load <b>{s.load}</b></span>
          </div>
        </> : <div className="empty">Nothing planned for the rest of this week. Ask Claude to plan the next block.</div>}
      </Card>

      <Card span={3} className="coach" title="Coach" right={t.coach.source === 'claude' ? 'this morning' : 'auto-check'}>
        <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100% - 26px)' }}>
          {t.coach.paragraphs.map((p: string, i: number) => <p key={i}><Md text={p} /></p>)}
          {t.latest_analysis && <p style={{ cursor: 'pointer' }} onClick={() => (location.hash = `workouts/${t.latest_analysis.id}`)}>
            <span className="dot" style={{ background: RATING[t.latest_analysis.rating]?.[1] ?? '#8b8b97', marginRight: 8 }} />
            <b style={{ color: '#fff' }}>{fd(t.latest_analysis.date, { weekday: 'long' })}:</b> {t.latest_analysis.title} <span className="muted">→</span></p>}
          <div className="who" style={{ marginTop: 'auto' }}><i />{t.coach.source === 'claude' ? 'Claude' : 'Rules & data · Claude adds notes after analysis'}</div>
        </div>
      </Card>

      <Card span={7} title="This week" onClick={() => (location.hash = 'week')}
        right={`done ${dur(wk.totals.hours * 60)} · load ${wk.totals.load}  /  planned ${dur(wk.totals.plan_hours * 60)} · load ${wk.totals.plan_load}`}>
        <div className="strip">{wk.days.map((d: any) => {
          const items = d.done.length ? d.done : d.planned
          const z = items.reduce((acc: number[], a: any) => a.zones.map((v: number, i: number) => v + (acc[i] ?? 0)), [] as number[])
          return (
            <div key={d.date} className={`sday ${d.is_today ? 'today' : ''} ${!d.done.length && d.planned.length ? 'plan' : ''}`}>
              <div className="d"><span>{fd(d.date)}</span><span>{d.date.slice(8)}</span></div>
              {items.length ? items.map((a: any, i: number) => (
                <div className="s" key={i}>{d.done.length ? `${SPORT[a.sport][0]} · ${dur(a.minutes)}` : a.name}
                  <small>{d.done.length ? (a.km ? `${a.km.toFixed(1)} km` : '') : a.sub}</small></div>
              )) : <div className="s muted">Rest</div>}
              <ZBar zones={z} height={4} />
            </div>
          )
        })}</div>
      </Card>

      <Card span={5} onClick={() => (location.hash = 'fitness')} title="Fitness & fatigue · 90 days"
        right={<><span style={{ color: 'var(--z2)' }}>━</span> fitness <span style={{ color: 'var(--load)' }}>┅</span> fatigue</>}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div className="big">{form >= 0 ? '+' : ''}{form.toFixed(0)}<small>form · {form > 5 ? 'fresh' : form < -10 ? 'tired' : 'balanced'}</small></div>
          <span className="muted" style={{ fontSize: 12 }}>details →</span></div>
        <Line values={L.map(x => x.fitness)} h={120} color="#5ef2c4" fill="#5ef2c4" min={0} max={mx}>
          <path d={scale(L.map(x => x.fatigue), 600, 120, 4, 0, mx).d} stroke="#ff8fb1" strokeWidth={1.5} fill="none" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
        </Line>
      </Card>
      <FuelToday refresh={refresh} />
    </div>
  </>
}

function FuelToday({ refresh }: { refresh: number }) {
  const { data: o } = useApi('/fuel', refresh)
  const plan = o?.today_plan ?? []
  if (!plan.length) return null
  return <Card span={12} title="Fuel today" right="food log and details →" onClick={() => (location.hash = 'fuel')}>
    <div className="fplan">{plan.map((p: any, i: number) => <FuelTarget key={i} p={p} />)}</div>
  </Card>
}
