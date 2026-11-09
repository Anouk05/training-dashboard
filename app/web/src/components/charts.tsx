// Hand-rolled SVG charts: small, dependency-free and easy to restyle.
import { useId, type ReactNode } from 'react'

type V = (number | null | undefined)[]

export function scale(vals: V, w: number, h: number, pad: number, min?: number, max?: number) {
  const real = vals.filter((x): x is number => x != null)
  const lo = min ?? Math.min(...real), hi = max ?? Math.max(...real)
  const sx = (i: number) => pad + (i / Math.max(1, vals.length - 1)) * (w - pad * 2)
  const sy = (x: number) => h - pad - ((x - lo) / (hi - lo || 1)) * (h - pad * 2)
  let d = '', pen = false
  vals.forEach((x, i) => {
    if (x == null) { pen = false; return }
    d += (pen ? 'L' : 'M') + sx(i).toFixed(1) + ' ' + sy(x).toFixed(1); pen = true
  })
  return { d, sx, sy }
}

export function Line({ values, h = 120, w = 600, color = '#fff', fill, band, min, max, width = 2, dash, children }:
  { values: V; h?: number; w?: number; color?: string; fill?: string; band?: [number, number, string]; min?: number; max?: number;
    width?: number; dash?: string; children?: ReactNode }) {
  const id = useId().replace(/:/g, '')
  if (!values.some(v => v != null)) return <svg height={h} />
  const p = scale(values, w, h, 4, min, max)
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: 'block', overflow: 'visible' }}>
      {band && <rect x={0} y={p.sy(band[1])} width={w} height={p.sy(band[0]) - p.sy(band[1])} fill={band[2]} rx={4} />}
      {fill && <>
        <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={fill} stopOpacity=".35" /><stop offset="1" stopColor={fill} stopOpacity="0" />
        </linearGradient></defs>
        <path d={fillPath(values, p, h)} fill={`url(#${id})`} />
      </>}
      {children}
      <path d={p.d} fill="none" stroke={color} strokeWidth={width} strokeDasharray={dash} strokeLinejoin="round"
        strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

/** Area under the line, closed per continuous segment so gaps in the data stay empty. */
function fillPath(values: V, p: ReturnType<typeof scale>, h: number) {
  let d = '', start = -1
  values.forEach((v, i) => {
    const end = v == null || i === values.length - 1
    if (v != null && start < 0) start = i
    if (end && start >= 0) {
      const stop = v == null ? i - 1 : i
      d += `M${p.sx(start)} ${h}` + values.slice(start, stop + 1).map((x, k) => `L${p.sx(start + k)} ${p.sy(x as number)}`).join('') + `L${p.sx(stop)} ${h}Z`
      start = -1
    }
  })
  return d
}

export function arc(cx: number, cy: number, r: number, a0: number, a1: number) {
  const p = (a: number) => [cx + r * Math.cos(a), cy + r * Math.sin(a)]
  const [x0, y0] = p(a0), [x1, y1] = p(a1)
  return `M${x0} ${y0} A${r} ${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${x1} ${y1}`
}

export function Donut({ parts, label, sub }: { parts: [number, string][]; label: string; sub: string }) {
  let a0 = -Math.PI / 2
  return (
    <svg width="140" height="140" viewBox="0 0 140 140">
      {parts.map(([v, c], i) => {
        if (!v) return null
        const a1 = a0 + v * 2 * Math.PI - 0.04
        const el = <path key={i} d={arc(70, 70, 56, a0, Math.max(a0 + 0.01, a1))} stroke={c} strokeWidth="14" fill="none" strokeLinecap="round" />
        a0 = a1 + 0.04
        return el
      })}
      <text x="70" y="74" textAnchor="middle" fill="#fff" fontSize="26" fontFamily="Geist" fontWeight="500">{label}</text>
      <text x="70" y="92" textAnchor="middle" fill="#8b8b97" fontSize="11" fontFamily="Geist">{sub}</text>
    </svg>
  )
}
