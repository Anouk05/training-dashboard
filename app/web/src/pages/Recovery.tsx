import { useState } from 'react'
import { Card, Loading, Seg, useApi } from '../components/ui'
import { Line } from '../components/charts'
import { fd, rolling } from '../lib/util'

export default function Recovery({ refresh }: { refresh: number }) {
  const [days, setDays] = useState<'90' | '365'>('365')
  const { data: r, error } = useApi(`/recovery?days=${days}`, `${days}-${refresh}`)
  if (!r) return <Loading error={error} />
  const S = r.series as any[], t = r.today
  const avg = (k: string) => { const v = S.map(x => x[k]).filter((x: any) => x != null); return v.length ? v.reduce((a: number, b: number) => a + b, 0) / v.length : 0 }
  const ticks = [0, .25, .5, .75].map(f => S[Math.floor(f * (S.length - 1))].date)
  const axis = <div className="row muted" style={{ justifyContent: 'space-between', fontSize: 11, marginTop: 8 }}>
    {ticks.map(d => <span key={d}>{fd(d, { month: 'short', year: '2-digit' })}</span>)}<span>now</span></div>

  const trend = (span: number, title: string, sub: string, value: any, unit: string, key: string, color: string, h = 120) => (
    <Card span={span} title={title} right={sub}>
      <div className="big">{value ?? '–'}<small>{unit}</small></div>
      <div style={{ marginTop: 10 }}><Line values={rolling(S.map(x => x[key]), 7)} h={h} color={color} fill={color} /></div>{axis}
    </Card>)

  return <>
    <div className="ph">
      <div><h1>Recovery</h1><p>How your body is handling the training · 7-day averages</p></div>
      <Seg value={days} options={[['90', '3 months'], ['365', '12 months']]} onChange={setDays} />
    </div>
    <div className="grid">
      {trend(8, 'HRV · overnight', t.hrv_baseline_low ? `normal ${t.hrv_baseline_low}–${t.hrv_baseline_high} ms` : '', t.hrv_last_night,
        `ms${t.hrv_status ? ' · ' + t.hrv_status.toLowerCase() : ''}`, 'hrv', '#8aa8ff', 160)}
      <Card span={4} title="Data quality" right="excluded from averages">
        {r.flags.map((f: any) => (
          <div className="rule" key={f.from}><span className="ic warn">!</span><div>
            <b>{fd(f.from, { day: 'numeric', month: 'short' })}{f.to !== f.from ? '–' + fd(f.to, { day: 'numeric', month: 'short' }) : ''}:</b> resting HR of {f.values.join(', ')} bpm,
            far above your median of {r.median_rhr}. {f.notes.length ? <>Your calendar around then: {f.notes.map((n: any) => `“${n.name}” (${fd(n.date, { day: 'numeric', month: 'short' })})`).join(', ')}. That likely explains the readings.</>
              : 'That looks like a loose watch or the watch not being worn, unless you were ill.'}</div></div>
        ))}
        <div className="rule"><span className={`ic ${r.sleep_nights_30 >= 27 ? 'ok' : 'warn'}`}>{r.sleep_nights_30 >= 27 ? '✓' : '!'}</span>
          <div>Sleep data for {r.sleep_nights_30} of the last 30 nights.</div></div>
      </Card>
      {trend(4, 'Resting heart rate', `${days === '365' ? '12-month' : '3-month'} avg ${avg('rhr').toFixed(0)} bpm`, t.resting_hr, 'bpm', 'rhr', '#f7c76a')}
      {trend(4, 'Sleep score', `avg ${avg('sleep').toFixed(0)}`, t.sleep_score, t.sleep_h ? `· ${t.sleep_h.toFixed(1)} h last night` : '', 'sleep', '#b49bff')}
      {trend(4, 'Body battery · daily high', `avg ${avg('bb').toFixed(0)}`, t.body_battery_max, '', 'bb', '#5ef2c4')}
      {r.cycle && <CycleCard c={r.cycle} series={S.filter(x => x.phase)} />}
    </div>
  </>
}

export const PHASE_COLORS: Record<string, string> = { menstrual: '#ff6f8f', follicular: '#5ef2c4', ovulation: '#f7c76a', luteal: '#b49bff' }

/** Daily resting HR and HRV over the tracked cycles, on a background coloured by phase, plus medians per phase. */
function CycleCard({ c, series }: { c: any; series: any[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 800, H = 150, n = series.length, bw = W / Math.max(1, n)
  const line = (k: string, pad: number) => {
    const v = series.map(x => x[k]).filter((x: any) => x != null), lo = Math.min(...v) - pad, hi = Math.max(...v) + pad
    let d = '', pen = false
    series.forEach((x, i) => { if (x[k] == null) { pen = false; return }
      d += `${pen ? 'L' : 'M'}${(i + .5) * bw} ${8 + (1 - (x[k] - lo) / (hi - lo)) * (H - 16)}`; pen = true })
    return d
  }
  const hp = hover != null ? series[hover] : null
  const daysLeft = Math.round((new Date(c.next_period + 'T12:00').getTime() - Date.now()) / 864e5)
  return <Card span={12} title="Menstrual cycle" right={`from Garmin cycle tracking · ${c.cycles} cycles since ${fd(c.since, { day: 'numeric', month: 'short' })}`}>
    <div className="grid" style={{ gridTemplateColumns: '1fr 2fr', gap: 24, alignItems: 'start' }}>
      <div>
        <div className="big">Day {c.day}<small> · {c.name.toLowerCase()} phase</small></div>
        <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>
          {c.ongoing ? (daysLeft > 0 ? `Next period expected in about ${daysLeft} day${daysLeft === 1 ? '' : 's'}` : 'Next period expected any day now')
            : ''} · Garmin's predicted cycle length {c.cycle_length} days</div>
        <table className="ctab">
          <thead><tr><th /><th>Days</th><th>Resting HR</th><th>HRV</th><th>Sleep</th></tr></thead>
          <tbody>{c.phases.map((p: any) => <tr key={p.phase} className={p.phase === c.phase ? 'on' : ''}>
            <td><span className="dot" style={{ background: PHASE_COLORS[p.phase] }} />{p.name}</td><td className="mono">{p.days}</td>
            <td className="mono">{p.rhr ?? '–'}</td><td className="mono">{p.hrv ?? '–'}</td><td className="mono">{p.sleep ?? '–'}</td></tr>)}</tbody>
        </table>
        <div className="muted" style={{ fontSize: 11.5, marginTop: 10, lineHeight: 1.5 }}>Medians per phase. Readiness judges your resting HR and HRV against
          earlier days in the same phase, so a higher resting HR in the luteal phase isn't read as fatigue.</div>
      </div>
      <div style={{ position: 'relative' }}>
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block', height: H }} onPointerLeave={() => setHover(null)}>
          {series.map((x, i) => <rect key={i} x={i * bw} y={0} width={bw + .5} height={H} fill={PHASE_COLORS[x.phase]} opacity={hover === i ? .3 : .12}
            onPointerEnter={() => setHover(i)} />)}
          <path d={line('rhr', 2)} stroke="#f7c76a" strokeWidth={2} fill="none" vectorEffect="non-scaling-stroke" pointerEvents="none" />
          <path d={line('hrv', 5)} stroke="#8aa8ff" strokeWidth={2} fill="none" vectorEffect="non-scaling-stroke" pointerEvents="none" />
        </svg>
        {hp && <div className="ctip" style={{ left: `min(calc(${((hover! + .5) / n) * 100}% + 10px), calc(100% - 170px))` }}>
          <div className="muted mono" style={{ fontSize: 11 }}>{fd(hp.date, { weekday: 'short', day: 'numeric', month: 'short' })}</div>
          <div style={{ color: PHASE_COLORS[hp.phase] }}>{hp.phase}</div>
          <div><span style={{ color: '#f7c76a' }}>{hp.rhr ?? '–'}</span> bpm · <span style={{ color: '#8aa8ff' }}>{hp.hrv ?? '–'}</span> ms</div></div>}
        <div className="row muted" style={{ gap: 16, fontSize: 11.5, marginTop: 8, flexWrap: 'wrap' }}>
          <span><span style={{ color: '#f7c76a' }}>━</span> resting HR</span><span><span style={{ color: '#8aa8ff' }}>━</span> HRV</span>
          {Object.entries(PHASE_COLORS).map(([k, col]) => <span key={k}><span className="dot" style={{ background: col }} />{k}</span>)}
          <span style={{ marginLeft: 'auto' }}>{fd(series[0].date, { day: 'numeric', month: 'short' })} – today</span>
        </div>
      </div>
    </div>
  </Card>
}
