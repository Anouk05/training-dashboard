// Interactive chart for one workout: time and bpm axes, HR-zone bands, a line coloured by zone,
// and a hover crosshair with a readout at every moment. A synced pace (run) or power (ride) strip
// sits underneath. Without heart rate, power becomes the main line, with FTP-based power zones.
import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import { DEFAULT_ZONE_NAMES, pace, ZONE_COLORS } from '../lib/util'

type Pt = [number, number | null, number | null, number | null, number | null] // minutes, hr, m/s, watts, metres
type Zones = { floors: number[]; max_hr: number | null; lthr: number | null; sport: string; method: string; names?: string[] | null } | null
type Rep = { from: number; to: number }
type PowerZones = { ftp: number; np: number | null; floors: number[]; names?: string[] | null } | null

const PAD = { l: 44, r: 92, t: 12, b: 26 }

export const zoneOf = (hr: number, floors: number[]) => {
  let z = -1
  floors.forEach((f, i) => { if (hr >= f) z = i })
  return z
}

const clock = (min: number) => {
  const s = Math.round(min * 60), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`
}
const tickLabel = (min: number) => (min >= 60 ? `${Math.floor(min / 60)}:${String(Math.round(min % 60)).padStart(2, '0')}` : `${Math.round(min)}′`)

/** Hard-edged vertical gradient stops (offset 0 = top of the chart) so the line takes each zone's colour. */
function gradientStops(floors: number[], yLo: number, yHi: number): [number, string][] {
  if (!floors.length) return [[0, '#ff4f7b'], [1, '#ff4f7b']]
  const off = (v: number) => Math.min(1, Math.max(0, 1 - (v - yLo) / (yHi - yLo)))
  const stops: [number, string][] = []
  for (let i = floors.length - 1; i >= 0; i--) { // top zone first so offsets increase
    const top = i < floors.length - 1 ? floors[i + 1] : Infinity
    stops.push([off(Math.min(top, yHi)), ZONE_COLORS[i]], [off(floors[i]), ZONE_COLORS[i]])
  }
  stops.push([off(floors[0]), '#8b8b97'], [1, '#8b8b97']) // below Z1
  return stops
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(800)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, e.contentRect.width)))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return { ref, w }
}

/** Minutes per zone, computed from the samples with the zones shown on the chart (field 1 = HR, 3 = power). */
export function timeInZones(points: Pt[], floors: number[], field: 1 | 3 = 1) {
  const out = floors.map(() => 0)
  for (let i = 0; i + 1 < points.length; i++) {
    const v = points[i][field], dt = points[i + 1][0] - points[i][0]
    if (v == null || dt <= 0 || dt > 1) continue // skip pauses
    const z = zoneOf(v, floors)
    out[Math.max(0, z)] += dt
  }
  return out
}

/** Which line the chart is built around: heart rate when recorded, otherwise power. */
export function chartMode(points: Pt[]): 'hr' | 'power' | null {
  if (points.some(p => p[1] != null)) return 'hr'
  if (points.filter(p => p[3] != null && p[3] > 0).length > points.length * 0.3) return 'power'
  return null
}

export type Section = { type: string; start: number; end: number; avg_watts?: number | null; avg_hr?: number | null;
  intensity?: number | null; speed?: number | null; zone?: number | null }

export default function HrChart({ points, zones, powerZones = null, sport, reps = [], highlight = null, sections = [], onSection }:
  { points: Pt[]; zones: Zones; powerZones?: PowerZones; sport: string; reps?: Rep[]; highlight?: Rep | null;
    sections?: Section[]; onSection?: (i: number | null) => void }) {
  const { ref, w } = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const pts = useMemo(() => points.filter(p => p[0] != null), [points])
  const mode = chartMode(pts)
  // main series: heart rate, or power smoothed over 3 samples (raw power is very spiky)
  const main = useMemo(() => pts.map((p, i) => {
    if (mode === 'hr') return p[1]
    const win = pts.slice(Math.max(0, i - 1), i + 2).map(q => q[3]).filter((v): v is number => v != null)
    return win.length ? win.reduce((a, b) => a + b, 0) / win.length : null
  }), [pts, mode])
  if (!mode) return <div className="empty">No heart rate or power recorded for this workout.</div>
  const isPower = mode === 'power'
  const vals = main.filter((x): x is number => x != null)
  const unit = isPower ? 'W' : 'bpm'

  const floors = isPower ? powerZones?.floors ?? [] : zones?.floors ?? []
  const names = (isPower ? powerZones?.names : zones?.names) ?? DEFAULT_ZONE_NAMES
  const last = floors.length - 1
  const tMax = pts[pts.length - 1][0] || 1
  const sortedMain = [...vals].sort((a, b) => a - b)
  const yLo = isPower ? 0 : Math.max(40, Math.floor((Math.min(...vals) - 8) / 10) * 10)
  const yHi = isPower ? Math.ceil((sortedMain[Math.floor(sortedMain.length * 0.995)] * 1.12) / 50) * 50
    : Math.ceil((Math.max(...vals) + 6) / 10) * 10
  const H = 300, iw = w - PAD.l - PAD.r, ih = H - PAD.t - PAD.b
  const X = (t: number) => PAD.l + (t / tMax) * iw
  const Y = (hr: number) => PAD.t + (1 - (hr - yLo) / (yHi - yLo)) * ih

  // line path broken at missing samples
  let d = '', pen = false
  pts.forEach((p, i) => {
    const v = main[i]
    if (v == null) { pen = false; return }
    d += `${pen ? 'L' : 'M'}${X(p[0]).toFixed(1)} ${Y(Math.min(v, yHi)).toFixed(1)}`; pen = true
  })

  // x ticks: aim for ~7 labels on a "nice" minute step
  const step = [1, 2, 5, 10, 15, 20, 30, 60].find(s => tMax / s <= 8) ?? 60
  const xt: number[] = []
  for (let t = 0; t <= tMax + 1e-6; t += step) xt.push(t)
  const yt: number[] = []
  const yStep = isPower ? (yHi > 400 ? 100 : 50) : (yHi - yLo) > 80 ? 20 : 10
  for (let v = yLo; v <= yHi; v += yStep) yt.push(v)

  // zone bands: [floor_i, floor_{i+1}) clipped to the visible range
  const bands = floors.map((f, i) => {
    const top = i < last ? floors[i + 1] : Math.max(yHi, zones?.max_hr ?? yHi)
    const a = Math.max(f, yLo), b = Math.min(top, yHi)
    return b > a ? { i, y0: Y(b), y1: Y(a), mid: (a + b) / 2, label: `Z${i + 1} ${Math.round(f)}${i < last ? '–' + Math.round(top - 1) : '+'}` } : null
  }).filter(Boolean) as { i: number; y0: number; y1: number; mid: number; label: string }[]

  // secondary strip: pace for runs (faster = higher), power for rides (unless power is already the main line)
  const isRide = sport === 'ride'
  const sec = isPower && isRide ? pts.map(() => null) : pts.map((p, i) => {
    if (isRide) return p[3]
    const win = pts.slice(Math.max(0, i - 1), i + 2).map(q => q[2]).filter((v): v is number => v != null && v > 0.5)
    const v = win.length ? win.reduce((a, b) => a + b, 0) / win.length : null
    return v ? 1000 / v / 60 : null // min/km
  })
  const secVals = sec.filter((v): v is number => v != null && (isRide || v < 12))
  const showSec = secVals.length > pts.length * 0.3
  const SH = 92, sih = SH - 20
  // scale on the 3rd–97th percentile so a few stops or GPS spikes don't flatten the line
  const sorted = [...secVals].sort((x, y) => x - y), q = (f: number) => sorted[Math.floor(f * (sorted.length - 1))] ?? 0
  const sLo = isRide ? 0 : q(0.03), sHi = isRide ? q(0.99) * 1.08 : q(0.97)
  const SY = (v: number) => 6 + (isRide ? 1 - v / sHi : (v - sLo) / (sHi - sLo || 1)) * sih
  let sd = '', spen = false
  sec.forEach((v, i) => {
    if (v == null || (!isRide && v >= 12)) { spen = false; return }
    const c = Math.min(Math.max(v, sLo), sHi) // clamp outliers to the strip
    sd += `${spen ? 'L' : 'M'}${X(pts[i][0]).toFixed(1)} ${SY(c).toFixed(1)}`; spen = true
  })

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
    const t = ((e.clientX - r.left - PAD.l) / iw) * tMax
    if (t < 0 || t > tMax) return setHover(null)
    let lo = 0, hi = pts.length - 1 // nearest sample by time
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (pts[m][0] < t) lo = m; else hi = m }
    setHover(Math.abs(pts[lo][0] - t) < Math.abs(pts[hi][0] - t) ? lo : hi)
  }

  const hp = hover != null ? pts[hover] : null
  const hv = hover != null ? main[hover] : null
  const hz = hv != null ? zoneOf(hv, floors) : -1
  const inRep = hp ? reps.findIndex(r => hp[0] >= r.from && hp[0] <= r.to) : -1
  const gid = 'hrz' + Math.round(yLo) + Math.round(yHi)

  // band above the chart: one box per section with its averages, like intervals.icu's interval header
  const BAND = sections.length ? 78 : 0
  const secLabel = (x: Section) => {
    const d = Math.round(x.end - x.start), m = Math.floor(d / 60), sec = d % 60
    return m >= 1 ? `${m}m${sec ? String(sec).padStart(2, '0') + 's' : ''}` : `${sec}s`
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      {BAND > 0 && <svg width={w} height={BAND} style={{ display: 'block' }} onPointerLeave={() => onSection?.(null)}>
        {sections.map((x, i) => {
          const x0 = X(x.start / 60), x1 = X(x.end / 60), bw = x1 - x0, cx = (x0 + x1) / 2
          const work = x.type === 'WORK', on = highlight && Math.abs(highlight.from * 60 - x.start) < 1
          const lines: [string, string][] = [[secLabel(x), '#cfcfd6'],
            [x.avg_watts != null ? `${x.avg_watts}w` : '', '#b49bff'],
            [x.avg_hr != null ? `${x.avg_hr}bpm` : '', '#ff6f8f'],
            [isRide || !x.speed ? (x.intensity != null ? `${x.intensity}%` : '') : `${pace(1000 / x.speed / 60)}/km`, '#8b8b97']]
          // narrow sections show fewer lines; the rest is in the table and on hover
          const fit = bw >= 50 ? 4 : bw >= 34 ? 2 : 0
          return <g key={i} onPointerEnter={() => onSection?.(i)} style={{ cursor: 'default' }}>
            <rect x={x0 + 1} y={2} width={Math.max(2, bw - 2)} height={BAND - 6} rx={6}
              fill={on ? 'hsla(158, 80%, 62%, .14)' : work ? 'rgba(255,159,107,.10)' : 'rgba(255,255,255,.035)'}
              stroke={on ? 'hsla(158, 80%, 62%, .6)' : work ? 'rgba(255,159,107,.35)' : 'rgba(255,255,255,.07)'} />
            {lines.slice(0, fit).map(([t, c], k) => t && <text key={k} x={cx} y={19 + k * 16} textAnchor="middle" fontSize={k === 0 ? 11.5 : 11}
              fontFamily="Geist Mono" fill={c} fontWeight={k === 0 ? 500 : 400}>{t}</text>)}
          </g>
        })}
      </svg>}
      {(() => { // narrow sections: their numbers appear in a small label on hover
        const i = highlight ? sections.findIndex(x => Math.abs(highlight.from * 60 - x.start) < 1) : -1
        const x = sections[i]
        if (!x || X(x.end / 60) - X(x.start / 60) >= 50) return null
        const cx = (X(x.start / 60) + X(x.end / 60)) / 2
        return <div style={{ position: 'absolute', top: 2, left: Math.min(w - 110, Math.max(0, cx - 52)), width: 104, pointerEvents: 'none', zIndex: 2,
          padding: '6px 8px', borderRadius: 8, background: 'rgba(12,12,16,.95)', border: '1px solid rgba(255,159,107,.45)',
          fontFamily: '"Geist Mono", monospace', fontSize: 11, lineHeight: 1.45, textAlign: 'center' }}>
          <div style={{ color: '#cfcfd6', fontWeight: 500 }}>{secLabel(x)}</div>
          {x.avg_watts != null && <div style={{ color: '#b49bff' }}>{x.avg_watts}w</div>}
          {x.avg_hr != null && <div style={{ color: '#ff6f8f' }}>{x.avg_hr}bpm</div>}
          {isRide || !x.speed ? x.intensity != null && <div className="muted">{x.intensity}%</div> : <div className="muted">{pace(1000 / x.speed / 60)}/km</div>}
        </div>
      })()}
      <svg width={w} height={H + (showSec ? SH + 8 : 0)} style={{ display: 'block', touchAction: 'none', cursor: 'crosshair' }}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        <defs>
          {/* line colour follows the zone it's in */}
          <linearGradient id={gid} gradientUnits="userSpaceOnUse" x1="0" x2="0" y1={Y(yHi)} y2={Y(yLo)}>
            {gradientStops(floors, yLo, yHi).map(([o, c], i) => <stop key={i} offset={o} stopColor={c} />)}
          </linearGradient>
          <clipPath id={gid + 'c'}><rect x={PAD.l} y={PAD.t} width={iw} height={ih} /></clipPath>
        </defs>

        {bands.map(b => <g key={b.i}>
          <rect x={PAD.l} y={b.y0} width={iw} height={b.y1 - b.y0} fill={ZONE_COLORS[b.i]} opacity={hz === b.i ? 0.16 : 0.07} />
          <text x={PAD.l + iw + 8} y={(b.y0 + b.y1) / 2 + 4} fontSize={11} fontFamily="Geist" fill={ZONE_COLORS[b.i]} opacity={b.y1 - b.y0 > 12 ? 1 : 0}>{b.label}</text>
        </g>)}
        {reps.map((r, i) => <rect key={i} x={X(r.from)} y={PAD.t} width={X(r.to) - X(r.from)} height={ih} fill="rgba(255,255,255,.04)" stroke="rgba(255,255,255,.08)" strokeDasharray="3 3" />)}
        {highlight && <rect x={X(highlight.from)} y={PAD.t} width={Math.max(2, X(highlight.to) - X(highlight.from))} height={ih} fill="hsla(158, 80%, 62%, .12)" stroke="hsla(158, 80%, 62%, .6)" />}

        {yt.map(v => <g key={v}>
          <line x1={PAD.l} x2={PAD.l + iw} y1={Y(v)} y2={Y(v)} stroke="rgba(255,255,255,.06)" />
          <text x={PAD.l - 8} y={Y(v) + 4} textAnchor="end" fontSize={11} fontFamily="Geist Mono" fill="#8b8b97">{v}</text>
        </g>)}
        <text x={10} y={PAD.t + 4} fontSize={10.5} fontFamily="Geist" fill="#8b8b97" transform={`rotate(-90 10 ${PAD.t + ih / 2}) translate(${-ih / 2 + 20} 0)`}>{unit}</text>
        {xt.map(t => <g key={t}>
          <line x1={X(t)} x2={X(t)} y1={PAD.t} y2={PAD.t + ih} stroke="rgba(255,255,255,.04)" />
          <text x={X(t)} y={H - 8} textAnchor="middle" fontSize={11} fontFamily="Geist Mono" fill="#8b8b97">{tickLabel(t)}</text>
        </g>)}

        <path d={d} fill="none" stroke={`url(#${gid})`} strokeWidth={2} strokeLinejoin="round" clipPath={`url(#${gid}c)`} />

        {showSec && <g transform={`translate(0 ${H + 8})`}>
          <rect x={PAD.l} y={0} width={iw} height={SH - 8} rx={6} fill="rgba(255,255,255,.025)" />
          <path d={sd} fill="none" stroke="#8aa8ff" strokeWidth={1.5} strokeLinejoin="round" />
          <text x={PAD.l + iw + 8} y={16} fontSize={11} fontFamily="Geist" fill="#8aa8ff">{isRide ? 'power' : 'pace'}</text>
          <text x={PAD.l + iw + 8} y={31} fontSize={10.5} fontFamily="Geist Mono" fill="#8b8b97">{isRide ? `0–${Math.round(sHi)} W` : `${pace(sLo)}–${pace(sHi)}`}</text>
        </g>}

        {hp && <g pointerEvents="none">
          <line x1={X(hp[0])} x2={X(hp[0])} y1={PAD.t} y2={H - PAD.b + (showSec ? SH + 8 : 0)} stroke="rgba(255,255,255,.55)" strokeDasharray="2 3" />
          {hv != null && <circle cx={X(hp[0])} cy={Y(Math.min(hv, yHi))} r={5} fill="#07070a" stroke={hz >= 0 ? ZONE_COLORS[hz] : '#fff'} strokeWidth={2.5} />}
          {showSec && sec[hover!] != null && (isRide || sec[hover!]! < 12) &&
            <circle cx={X(hp[0])} cy={H + 8 + SY(Math.min(Math.max(sec[hover!]!, sLo), sHi))} r={4} fill="#07070a" stroke="#8aa8ff" strokeWidth={2} />}
        </g>}
      </svg>

      {hp && (() => {
        const left = X(hp[0]), flip = left > w - 220
        return (
          <div style={{ position: 'absolute', top: BAND + 14, left: flip ? left - 192 : left + 12, width: 180, pointerEvents: 'none', padding: '10px 12px', borderRadius: 12,
            background: 'rgba(12,12,16,.92)', border: '1px solid rgba(255,255,255,.12)', backdropFilter: 'blur(12px)', fontSize: 12.5, lineHeight: 1.55 }}>
            <div className="mono muted" style={{ fontSize: 11 }}>{clock(hp[0])}{hp[4] ? ` · ${(hp[4] / 1000).toFixed(2)} km` : ''}{inRep >= 0 ? ` · rep ${inRep + 1}` : ''}</div>
            <div style={{ fontSize: 22, fontWeight: 500, letterSpacing: '-.02em' }}>{hv != null ? Math.round(hv) : '–'}<span className="muted" style={{ fontSize: 12, fontWeight: 400 }}> {unit}</span></div>
            {hz >= 0 && <div style={{ color: ZONE_COLORS[hz] }}>Z{hz + 1} {names[hz]}{hv != null && (isPower ? powerZones?.ftp : zones?.lthr)
              ? <span className="muted"> · {Math.round((hv / (isPower ? powerZones!.ftp : zones!.lthr!)) * 100)}% {isPower ? 'FTP' : 'LTHR'}</span> : null}</div>}
            {hz < 0 && floors.length > 0 && <div className="muted">below Z1</div>}
            {isPower ? (hp[2] != null && hp[2] > 0.5 && <div>{(hp[2] * 3.6).toFixed(1)} km/h</div>)
              : isRide ? (hp[3] != null && <div>{Math.round(hp[3])} W</div>) : (sec[hover!] != null && sec[hover!]! < 12 && <div>{pace(sec[hover!]!)} /km</div>)}
          </div>
        )
      })()}
    </div>
  )
}
