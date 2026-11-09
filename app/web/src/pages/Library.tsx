import { useState } from 'react'
import { Blocks, Loading, Seg, useApi } from '../components/ui'
import { fd, SPORT } from '../lib/util'

export default function Library({ refresh }: { refresh: number }) {
  const { data, error } = useApi('/library', refresh)
  const [sport, setSport] = useState('all')
  if (!data) return <Loading error={error} />
  const items = (data as any[]).filter(w => sport === 'all' || w.sport === sport)
  return <>
    <div className="ph">
      <div><h1>Library</h1><p>Your standard workouts. Each has a stable ID, so every repeat can be compared.</p></div>
      <div className="row" style={{ gap: 10 }}>
        <Seg value={sport} options={[['all', 'All'], ['run', 'Run'], ['ride', 'Ride'], ['row', 'Row'], ['str', 'Strength']]} onChange={setSport} />
        <button className="btn off" title="Ask Claude to add one to library/workouts.yaml">+ New workout</button>
      </div>
    </div>
    <div className="libgrid">{items.map(w => (
      <div className="card lib" key={w.id}>
        <div className="row" style={{ justifyContent: 'space-between' }}><span className="id">{w.id}</span>
          <span className="chip" style={{ padding: '3px 8px', fontSize: 11 }}><span className="dot" style={{ background: SPORT[w.sport]?.[1] }} />{SPORT[w.sport]?.[0]}</span></div>
        <div className="n">{w.name}</div>
        <div className="muted" style={{ fontSize: 12 }}>{w.summary}</div>
        <Blocks steps={w.steps} height={46} />
        <div className="ft"><span>{w.count}× done</span><span>{w.last ? 'last ' + fd(w.last, { day: 'numeric', month: 'short', year: '2-digit' }) : 'not done yet'}</span></div>
      </div>
    ))}</div>
  </>
}
