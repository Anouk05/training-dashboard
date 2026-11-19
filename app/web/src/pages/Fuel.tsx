// Fuel: today's fuel targets per workout, the food log for a day (plain words; Claude estimates the numbers),
// the day's totals against targets (carbs and protein per kg, energy availability), and the last 7 days.
import { useState } from 'react'
import { Card, Loading, useApi } from '../components/ui'
import FuelTotals from '../components/FuelTotals'
import { addDays, api, fd, SPORT } from '../lib/util'

const SLOTS: [string, string][] = [['breakfast', 'Breakfast'], ['lunch', 'Lunch'], ['dinner', 'Dinner'], ['snack', 'Snack'], ['workout', 'During workout']]

export default function Fuel({ refresh, day }: { refresh: number; day?: string }) {
  const today = new Date().toISOString().slice(0, 10)
  const d = day || today
  const { data: o, error } = useApi('/fuel', refresh)
  const { data: dd, setData: setDay } = useApi(`/fuel/day/${d}`, `${d}-${refresh}`)
  if (!o) return <Loading error={error} />
  const b = o.body

  return <>
    <div className="ph">
      <div><h1>Fuel</h1><p>Before, during and after your workouts, and whether you eat enough over the day</p></div>
      <div className="row muted" style={{ fontSize: 12.5, gap: 18 }}>
        {b.weight && <span>{b.weight} kg{b.body_fat ? ` · ${b.body_fat}% fat` : ''} · Garmin scale {fd(b.date, { day: 'numeric', month: 'short' })}</span>}
      </div>
    </div>
    <div className="grid">
      <Card span={12} title="Fuel today" right="targets from duration, intensity and your weight">
        {o.today_plan.length ? <div className="fplan">{o.today_plan.map((p: any, i: number) => <FuelTarget key={i} p={p} />)}</div>
          : <div className="muted" style={{ fontSize: 13 }}>No workouts planned today: eat normally, with protein spread over your meals.</div>}
      </Card>

      {dd ? <DayLog d={d} dd={dd} setDay={setDay} today={today} /> : <Card span={8} title="Food log"><Loading /></Card>}

      <Card span={4} title="Last 7 days" right={`${o.checked}/${o.workouts} workouts checked`}>
        <table className="ftab">
          <thead><tr><th /><th>kcal</th><th>carbs</th><th>prot.</th><th>EA</th></tr></thead>
          <tbody>{o.days.map((x: any) => <tr key={x.date} className={x.date === d ? 'on' : ''} onClick={() => (location.hash = `fuel/${x.date}`)}>
            <td>{fd(x.date, { weekday: 'short', day: 'numeric' })}{x.n_meals ? '' : <span className="muted"> · –</span>}</td>
            <td className={`mono ${x.n_meals && x.targets.kcal ? (x.totals.kcal >= x.targets.kcal[0] ? 'ok' : 'low') : ''}`}>{x.n_meals ? x.totals.kcal : ''}</td>
            <td className={`mono ${x.per_kg.carbs != null ? (x.per_kg.carbs >= x.targets.carbs_gkg[0] ? 'ok' : 'low') : ''}`}>{x.per_kg.carbs ?? ''}</td>
            <td className={`mono ${x.per_kg.protein != null ? (x.per_kg.protein >= 1.6 ? 'ok' : 'low') : ''}`}>{x.per_kg.protein ?? ''}</td>
            <td className={`mono ${x.ea != null ? (x.ea >= 45 ? 'ok' : x.ea >= 30 ? 'mid' : 'low') : ''}`}>{x.ea ?? ''}</td>
          </tr>)}</tbody>
        </table>
        <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.5, marginTop: 10 }}>
          kcal is green when it reaches the day's minimum (EA 30). Carbs and protein in g per kg. EA = energy availability: kcal eaten minus training kcal, per kg fat-free mass;
          45+ is enough, 30–45 is low for a while, under 30 is too low.
          {o.checked > 0 && <> {o.on_target} of {o.checked} checked workouts were fuelled to target.</>}</div>
      </Card>
    </div>
  </>
}

export function FuelTarget({ p }: { p: any }) {
  const t = p.target, v = p.verdict
  const res = (k: string) => v && <div className={`fres ${v[k] === 'ok' ? 'ok' : 'low'}`}>{v[k] === 'ok' ? '✓' : '!'} {v[`${k}_text`]}</div>
  const open = (e: any) => { e.stopPropagation(); location.hash = `workouts/${p.done_id}` }
  return <div className="ft">
    <div className="k" style={{ color: SPORT[p.sport]?.[1] }}><span className="dot" style={{ background: SPORT[p.sport]?.[1] }} />{p.name} · {p.minutes}′
      {p.done_id && <span className={`fstat ${v ? (v.ok ? 'ok' : 'mid') : ''}`}>{v ? (v.ok ? 'fuelled to target' : 'below target') : 'done'}</span>}</div>
    <div className="r"><b>Before</b><span>{t.before}{res('before')}</span></div>
    <div className="r"><b>During</b><span>{t.during.text}{v && <div className={`fres ${v.during === 'ok' ? 'ok' : 'low'}`}>{v.during === 'ok' ? '✓' : '!'} {p.carbs_g ? `${p.carbs_g} g carbs · ` : ''}{v.during_text}</div>}</span></div>
    <div className="r"><b>After</b><span>{t.after.text}{res('after')}</span></div>
    {p.done_id && <button className="flink" onClick={open}>{v ? 'Change fuel check →' : 'Fill in the fuel check →'}</button>}
  </div>
}

function DayLog({ d, dd, setDay, today }: { d: string; dd: any; setDay: (x: any) => void; today: string }) {
  const [form, setForm] = useState<any>({ slot: 'breakfast', time: '', text: '', kcal: '', carbs: '', protein: '', fat: '' })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  const t = dd.totals, tg = dd.targets
  const save = async () => {
    if (!form.text.trim()) return
    setBusy(true); setErr(null)
    try {
      const num = (v: string) => v.trim() === '' ? null : Number(v.replace(',', '.'))
      setDay(await api(`/fuel/day/${d}/meal`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, time: form.time || null, kcal: num(form.kcal), carbs: num(form.carbs), protein: num(form.protein), fat: num(form.fat) }) }))
      setForm({ ...form, text: '', time: '', kcal: '', carbs: '', protein: '', fat: '' })
    } catch (e) { setErr(String(e)) }
    setBusy(false)
  }
  const del = async (id: string) => setDay(await api(`/fuel/day/${d}/meal/${id}`, { method: 'DELETE' }))

  return <Card span={8} title={<span className="row" style={{ gap: 12 }}>Food log
    <span className="stepper small"><button onClick={() => (location.hash = `fuel/${addDays(d, -1)}`)}>‹</button>
      <b>{d === today ? 'Today' : fd(d, { weekday: 'short', day: 'numeric', month: 'short' })}</b>
      <button disabled={d >= today} onClick={() => (location.hash = `fuel/${addDays(d, 1)}`)}>›</button></span></span>}
    right={`${dd.training.hours} h training${dd.training.planned ? ' planned' : ''} · ~${dd.training.exercise_kcal} kcal`}>
    <FuelTotals t={t} tg={tg} ea={dd.ea} kg={dd.body?.weight || tg.protein[0] / 1.6} />
    {dd.to_estimate > 0 && <div className="fnote">{dd.to_estimate} meal{dd.to_estimate === 1 ? '' : 's'} without numbers yet. Claude estimates them every evening at 21:00,
      or ask in the chat: <span className="mono">estimate my food log</span>. Totals and EA count once every meal has numbers.</div>}

    <div className="meals">{dd.meals.map((m: any) => { const isOpen = open === m.id, canOpen = !!(m.items?.length || m.assumed)
      return <div key={m.id} className={`mealw ${isOpen ? 'open' : ''}`}>
        <div className={`meal ${canOpen ? 'click' : ''}`} onClick={() => canOpen && setOpen(isOpen ? null : m.id)}>
          <span className="mono muted">{m.time || ''}</span>
          <div><div className="muted" style={{ fontSize: 11 }}>{SLOTS.find(s => s[0] === m.slot)?.[1] ?? m.slot}{canOpen && <span className="more"> · {isOpen ? 'hide' : 'show'} breakdown</span>}</div><div>{m.text}</div></div>
          <div className="mono nums">{m.kcal != null ? <>{Math.round(m.kcal)} kcal · C {Math.round(m.carbs ?? 0)} · P {Math.round(m.protein ?? 0)} · F {Math.round(m.fat ?? 0)}
            <span className="src">{m.source === 'estimate' ? 'estimated' : 'yours'}</span></> : <span className="muted">to estimate</span>}</div>
          <button className="x" title="Delete" onClick={e => { e.stopPropagation(); del(m.id) }}>×</button>
        </div>
        {isOpen && <div className="mbreak">
          {m.items?.length > 0 && <table>
            <thead><tr><th>Ingredient</th><th>Amount</th><th>kcal</th><th>carbs</th><th>protein</th><th>fat</th></tr></thead>
            <tbody>{m.items.map((x: any, i: number) => <tr key={i}><td>{x.name}</td><td className="muted">{x.amount}</td>
              <td className="mono">{x.kcal}</td><td className="mono">{x.carbs}</td><td className="mono">{x.protein}</td><td className="mono">{x.fat}</td></tr>)}
              <tr className="sum"><td>Total</td><td /><td className="mono">{Math.round(m.kcal)}</td><td className="mono">{Math.round(m.carbs)}</td>
                <td className="mono">{Math.round(m.protein)}</td><td className="mono">{Math.round(m.fat)}</td></tr></tbody>
          </table>}
          {m.assumed && <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>{m.assumed} Tell Claude if an amount was different.</div>}
        </div>}
      </div> })}</div>

    <div className="madd">
      <select className="field" value={form.slot} onChange={e => setForm({ ...form, slot: e.target.value })}>{SLOTS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select>
      <input className="field" style={{ width: 80 }} placeholder="time" value={form.time} onChange={e => setForm({ ...form, time: e.target.value })} />
      <input className="field grow" placeholder="What did you eat? e.g. 2 slices of wholemeal bread with peanut butter, a banana, cappuccino"
        value={form.text} onChange={e => setForm({ ...form, text: e.target.value })} onKeyDown={e => e.key === 'Enter' && save()} />
      <button className="btn pri" disabled={busy || !form.text.trim()} onClick={save}>Add</button>
    </div>
    <details className="mopt"><summary>Know the numbers? (optional)</summary>
      <div className="row" style={{ gap: 8, marginTop: 8 }}>{(['kcal', 'carbs', 'protein', 'fat'] as const).map(k =>
        <input key={k} className="field mono" style={{ width: 90 }} placeholder={k === 'kcal' ? 'kcal' : `${k} g`} value={form[k]} onChange={e => setForm({ ...form, [k]: e.target.value })} />)}</div>
    </details>
    {err && <div style={{ color: '#ff9b8a', fontSize: 12.5, marginTop: 8 }}>Couldn't save: {err}</div>}
  </Card>
}
