// Quick fuel check on a completed workout: when you ate before, what you took during (tap items), and the
// recovery meal after. Compared with the target for this workout; the carbs also go to intervals.icu.
import { useEffect, useState } from 'react'
import { Card, Seg, useApi } from './ui'
import { api } from '../lib/util'

const TIMING: [string, string][] = [['fasted', 'Fasted'], ['<1h', '< 1 h'], ['1-3h', '1–3 h'], ['>3h', '> 3 h']]
const SIZE: [string, string][] = [['snack', 'Snack'], ['meal', 'Meal']]
const AFTER: [string, string][] = [['meal', 'Meal < 1 h'], ['snack', 'Snack < 1 h'], ['later', 'Later'], ['none', 'Nothing']]
const MARK: Record<string, string> = { ok: '✓', low: '!' }

export default function FuelCheck({ aid, span }: { aid: string; span: number }) {
  const { data: f, setData } = useApi(`/activity/${aid}/fuel`, aid)
  const [log, setLog] = useState<any>(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  useEffect(() => { if (f) setLog(f.log ?? { before: {}, during: {}, after: {}, other_g: null, notes: '' }) }, [f?.log, aid])  // eslint-disable-line
  if (!f || !log) return <Card span={span} title="Fuel"><div className="muted">Loading…</div></Card>
  const t = f.target
  const carbs = Object.entries(log.during || {}).reduce((a: number, [k, n]: any) => a + (f.foods.find((x: any) => x.id === k)?.carbs ?? 0) * n, 0) + (Number(log.other_g) || 0)
  const set = (part: string, k: string, v: any) => setLog({ ...log, [part]: { ...log[part], [k]: v } })
  const save = async () => {
    setSaving(true); setMsg(null)
    try {
      const r = await api(`/activity/${aid}/fuel`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(log) })
      setData(r); setMsg(r.sync_error ? `Saved here; intervals.icu not updated (${r.sync_error})` : 'Saved')
    } catch (e) { setMsg(`Couldn't save: ${e}`) }
    setSaving(false)
  }
  const v = f.verdict
  return <Card span={span} title="Fuel check" right={v ? (v.ok ? <span className="ok">fuelled to target</span> : <span className="mid">below target</span>) : 'not filled in yet'}>
    <div className="fc">
      <div className="fr"><b>Before {v && <span className={`ic ${v.before === 'ok' ? 'ok' : 'warn'}`}>{MARK[v.before]}</span>}</b>
        <div><div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <Seg small value={log.before?.timing ?? ''} options={TIMING} onChange={x => set('before', 'timing', x)} />
          {log.before?.timing !== 'fasted' && <Seg small value={log.before?.size ?? ''} options={SIZE} onChange={x => set('before', 'size', x)} />}</div>
          <div className="muted tg">{t.before}</div></div></div>
      <div className="fr"><b>During {v && <span className={`ic ${v.during === 'ok' ? 'ok' : 'warn'}`}>{MARK[v.during]}</span>}</b>
        <div><div className="fitems">{f.foods.map((x: any) => { const n = log.during?.[x.id] ?? 0
          return <span key={x.id} className={`fi ${n ? 'on' : ''}`}>
            <button onClick={() => set('during', x.id, Math.max(0, n - 1))}>−</button>
            <span>{x.name}{n ? <b> ×{n}</b> : ''}</span>
            <button onClick={() => set('during', x.id, n + 1)}>+</button></span> })}
          <input className="field mono" style={{ width: 92 }} placeholder="other g" value={log.other_g ?? ''} onChange={e => setLog({ ...log, other_g: e.target.value })} /></div>
          <div className="muted tg"><b className="mono" style={{ color: 'var(--text)' }}>{Math.round(carbs)} g carbs</b>{v?.during_text ? ` · ${v.during_text}` : ''} · target: {t.during.text}</div></div></div>
      <div className="fr"><b>After {v && <span className={`ic ${v.after === 'ok' ? 'ok' : 'warn'}`}>{MARK[v.after]}</span>}</b>
        <div><Seg small value={log.after?.kind ?? ''} options={AFTER} onChange={x => set('after', 'kind', x)} />
          <div className="muted tg">{t.after.text}</div></div></div>
    </div>
    <div className="row" style={{ gap: 12, marginTop: 10 }}>
      <button className="btn pri" disabled={saving} onClick={save}>{saving ? 'Saving…' : 'Save'}</button>
      {msg && <span className="muted" style={{ fontSize: 12 }}>{msg}</span>}
    </div>
  </Card>
}
