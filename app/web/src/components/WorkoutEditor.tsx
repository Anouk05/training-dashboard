// Add, edit or delete a planned workout in intervals.icu (which syncs it to the watch).
// A workout without event_id is a new one.
// Steps use intervals.icu's workout text, previewed live as blocks.
import { useEffect, useRef, useState } from 'react'
import { api, dur, SPORT } from '../lib/util'
import { Blocks } from './ui'

const TYPES: [string, string][] = [['Run', 'run'], ['Ride', 'ride'], ['Swim', 'swim'], ['WeightTraining', 'str'], ['Other', 'other']]
const SYNTAX = `- 10m Z2 HR          10 min in zone 2
- 2km 4:40 pace       2 km at a pace
- 5m 220w             5 min at a power

4x                    repeat the lines below…
- 3m Z4
- 2m Z1
                      …until the next empty line`

export default function WorkoutEditor({ workout, weekStart, onClose, onSaved }:
  { workout: any; weekStart: string; onClose: () => void; onSaved: (week: any) => void }) {
  const [name, setName] = useState(workout.name)
  const initialType: string = workout.type || TYPES.find(t => t[1] === workout.sport)?.[0] || 'Other'
  const [type, setType] = useState(initialType)
  const [day, setDay] = useState(workout.date)
  const [desc, setDesc] = useState(workout.description || '')
  const [preview, setPreview] = useState<any>({ steps: workout.steps, minutes: workout.minutes, load: workout.load })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [help, setHelp] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const isNew = !workout.event_id
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => { nameRef.current?.focus() }, [])
  useEffect(() => { // live preview, debounced; until the steps change, show intervals.icu's own numbers
    if (desc === (workout.description || '')) return setPreview({ steps: workout.steps, minutes: workout.minutes, load: workout.load })
    const t = setTimeout(() => {
      api('/workout/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ description: desc }) })
        .then(setPreview).catch(() => {})
    }, 250)
    return () => clearTimeout(t)
  }, [desc])

  const sportKey = TYPES.find(t => t[0] === type)?.[1] ?? (type.includes('Ride') ? 'ride' : type.includes('Run') ? 'run' : 'other')
  const changes: Record<string, string> = {}
  if (name.trim() && name.trim() !== workout.name) changes.name = name.trim()
  if (desc !== (workout.description || '')) changes.description = desc
  if (type !== initialType) changes.type = type
  if (day !== workout.date) changes.day = day
  const dirty = isNew ? name.trim().length > 0 : Object.keys(changes).length > 0
  const json = { 'Content-Type': 'application/json' }

  const run = async (req: () => Promise<any>, what: string) => {
    setSaving(true); setErr(null)
    try { onSaved(await req()) } catch (e) { setErr(`Couldn't ${what}: ${e}`); setSaving(false) }
  }
  const save = () => {
    if (!dirty || saving) return
    if (isNew) return run(() => api('/event', { method: 'POST', headers: json,
      body: JSON.stringify({ week_start: weekStart, day, name: name.trim(), type, description: desc }) }), 'add the workout to intervals.icu')
    return run(() => api(`/event/${workout.event_id}`, { method: 'POST', headers: json,
      body: JSON.stringify({ week_start: weekStart, ...changes }) }), 'save to intervals.icu')
  }
  const remove = () => {
    if (!confirmDelete) { setConfirmDelete(true); setTimeout(() => setConfirmDelete(false), 4000); return }
    run(() => api(`/event/${workout.event_id}?week_start=${weekStart}`, { method: 'DELETE' }), 'delete the workout')
  }

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save()
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  })

  return (
    <div className="modal-bg" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal" role="dialog" aria-label={isNew ? 'New workout' : 'Edit workout'}>
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 18 }}>
          <span className="muted" style={{ fontSize: 12 }}>{isNew ? 'New workout' : 'Edit planned workout'} · saves to intervals.icu and your watch</span>
          <button className="x" onClick={onClose} aria-label="Close">×</button>
        </div>

        <input ref={nameRef} className="field title" value={name} onChange={e => setName(e.target.value)} placeholder="Workout name" />

        <div className="row" style={{ gap: 14, margin: '14px 0 18px', flexWrap: 'wrap' }}>
          <div className="seg">{TYPES.map(([t, k]) => (
            // e.g. VirtualRide isn't one of the buttons: highlight the matching sport instead
            <button key={t} className={type === t || (!TYPES.some(x => x[0] === type) && k === sportKey) ? 'on' : ''} onClick={() => setType(t)}>
              <span className="dot" style={{ background: SPORT[k][1], marginRight: 6 }} />{SPORT[k][0]}</button>))}
          </div>
          <input type="date" className="field date" value={day} onChange={e => setDay(e.target.value)} />
        </div>

        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
          <span className="muted" style={{ fontSize: 12 }}>Steps</span>
          <button className="link" onClick={() => setHelp(h => !h)}>{help ? 'Hide syntax' : 'Syntax help'}</button>
        </div>
        {help && <pre className="syntax">{SYNTAX}</pre>}
        <textarea className="field steps" value={desc} onChange={e => setDesc(e.target.value)} spellCheck={false}
          rows={Math.min(14, Math.max(5, desc.split('\n').length + 1))} placeholder={'- 10m Z2 HR\n\n4x\n- 4m Z4\n- 2m Z1\n\n- 10m Z1'} />

        <div className="preview">
          {preview?.steps?.length ? <Blocks steps={preview.steps} height={64} /> : <div className="empty" style={{ padding: '14px 0' }}>No steps recognised yet.</div>}
          <div className="row muted" style={{ fontSize: 12.5, gap: 16 }}>
            <span>≈ <b style={{ color: '#fff' }}>{dur(preview?.minutes || 0)}</b></span>
            <span>est. load <b style={{ color: '#fff' }}>~{preview?.load ?? 0}</b></span>
            <span>intervals.icu recalculates both when you save</span>
          </div>
        </div>

        {err && <div style={{ color: '#ff9b8a', fontSize: 13, marginTop: 12 }}>{err}</div>}
        <div className="row" style={{ gap: 10, marginTop: 20 }}>
          {!isNew && <button className={`btn danger ${confirmDelete ? 'armed' : ''}`} onClick={remove} disabled={saving}>
            {confirmDelete ? 'Click again to delete' : 'Delete workout'}</button>}
          <span style={{ flex: 1 }} />
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className={`btn pri ${!dirty || saving ? 'off' : ''}`} onClick={save} disabled={!dirty || saving}>
            {saving ? 'Saving…' : isNew ? 'Add to intervals.icu' : 'Save to intervals.icu'}</button>
        </div>
      </div>
    </div>
  )
}
