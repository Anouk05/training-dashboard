import { useEffect, useState } from 'react'
import { api, glowFor } from './lib/util'
import { prefetch } from './components/ui'
import Today from './pages/Today'
import Week from './pages/Week'
import Plan from './pages/Plan'
import Workouts from './pages/Workouts'
import Progress from './pages/Progress'
import Recovery from './pages/Recovery'
import Library from './pages/Library'
import Fitness from './pages/Fitness'
import Fuel from './pages/Fuel'

const PAGES: [string, string][] = [['today', 'Today'], ['week', 'Week'], ['plan', 'Season'], ['workouts', 'Workouts'],
  ['progress', 'Progress'], ['fuel', 'Fuel'], ['recovery', 'Recovery'], ['library', 'Library']]

const parseHash = () => (location.hash.slice(1) || 'today').split('/')

export default function App() {
  const [route, setRoute] = useState(parseHash)
  const [refresh, setRefresh] = useState(0)   // bumped after a sync so pages re-fetch
  const [glow, setGlow] = useState(158)
  const [sync, setSync] = useState<{ state: 'idle' | 'busy' | 'err'; at?: string }>({ state: 'idle' })

  useEffect(() => {
    const on = () => { setRoute(parseHash()); window.scrollTo(0, 0) }
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  }, [])
  useEffect(() => { api('/today').then(t => setGlow(glowFor(t.readiness?.score))).catch(() => {}) }, [refresh])
  // load every page's data in the background so the first click on a tab is instant too
  useEffect(() => {
    const t = setTimeout(() => prefetch('/today', '/week', '/season', '/atp', '/seasons', '/activities?limit=80', '/progress',
      '/recovery?days=365', '/library', '/fitness?days=180', '/fuel'), 300)
    return () => clearTimeout(t)
  }, [])

  const runSync = async () => {
    setSync({ state: 'busy' })
    try {
      const r = await api('/sync', { method: 'POST' })
      setSync({ state: r.ok ? 'idle' : 'err', at: r.at?.slice(11) })
      setRefresh(x => x + 1)
    } catch { setSync({ state: 'err' }) }
  }

  const [page, arg] = route
  const props = { refresh }
  return (
    <div className="app" style={{ ['--glow' as string]: glow }}>
      <div className="top">
        <div className="brand"><i />Pulse</div>
        <nav>{PAGES.map(([k, n]) => <a key={k} href={'#' + k} className={page === k ? 'on' : ''}>{n}</a>)}</nav>
        <button className={`sync ${sync.state}`} onClick={runSync} title="Pull new data from Garmin and intervals.icu">
          <i />{sync.state === 'busy' ? 'Syncing…' : sync.state === 'err' ? 'Sync failed · retry' : sync.at ? `Synced ${sync.at}` : 'Sync'}
        </button>
      </div>
      <div className="page" key={page}>
        {page === 'today' && <Today {...props} />}
        {page === 'week' && <Week {...props} start={arg} />}
        {page === 'plan' && <Plan {...props} view={arg} />}
        {page === 'workouts' && <Workouts {...props} id={arg} />}
        {page === 'progress' && <Progress {...props} />}
        {page === 'recovery' && <Recovery {...props} />}
        {page === 'library' && <Library {...props} />}
        {page === 'fitness' && <Fitness {...props} />}
        {page === 'fuel' && <Fuel {...props} day={arg} />}
      </div>
    </div>
  )
}
