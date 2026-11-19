// The food log's day totals: one energy bar (eaten kcal split into carbs, protein and fat, with the kcal target
// outlined on the same track) and a row per macro with grams, g/kg and its own target.

const COL = { carbs: '#5ef2c4', protein: '#8fb4ff', fat: '#f7c76a' }
const KCAL_PER_G = { carbs: 4, protein: 4, fat: 9 }
type Macro = keyof typeof COL

// percentages that always add up to 100 (largest remainder rounds up)
function shares(v: number[]) {
  const sum = v.reduce((a, b) => a + b, 0), raw = v.map(x => x / sum * 100), pct = raw.map(Math.floor)
  raw.map((x, i) => [x - pct[i], i]).sort((a, b) => b[0] - a[0]).slice(0, 100 - pct.reduce((a, b) => a + b, 0)).forEach(([, i]) => pct[i]++)
  return { raw, pct }
}

const pos = (v: number, max: number) => `${Math.min(100, Math.max(0, v / max * 100))}%`

function MacroRow({ k, label, grams, value, unit, lo, hi, max, target }:
  { k: Macro; label: string; grams: number; value: number; unit: string; lo: number; hi: number; max: number; target: string }) {
  return <div className="fmac">
    <div className="k"><i style={{ background: COL[k] }} />{label}</div>
    <div className="v">{grams} g <small>{unit}</small></div>
    <div className="mini"><b style={{ width: pos(value, max), background: COL[k] }} />
      <u style={{ left: pos(lo, max), width: `calc(${pos(hi, max)} - ${pos(lo, max)})` }} /></div>
    <div className="tg mono">{target}</div>
  </div>
}

export default function FuelTotals({ t, tg, ea, kg }: { t: any; tg: any; ea: number | null; kg: number }) {
  const kcal = (['carbs', 'protein', 'fat'] as Macro[]).map(k => (t[k] || 0) * KCAL_PER_G[k])
  const hasMacros = kcal.some(Boolean), { raw, pct } = hasMacros ? shares(kcal) : { raw: [0, 0, 0], pct: [0, 0, 0] }
  const max = Math.max(t.kcal || 0, tg.kcal ? tg.kcal[1] : 0) * 1.04 || 1
  const eatenW = (t.kcal || 0) / max * 100
  let left = 0
  const segs = raw.map(r => { const w = r / 100 * eatenW, s = { left, w }; left += w; return s })
  const fatPct = hasMacros ? raw[2] : 0
  const gkg = (g: number) => (g / kg).toFixed(1)

  return <div className="ftot">
    <div className="ftop">
      <div><div className="muted">Eaten</div>
        <div className="big">{(t.kcal || 0).toLocaleString('en')}<small>kcal{tg.kcal && <> · target {tg.kcal[0].toLocaleString('en')}–{tg.kcal[1].toLocaleString('en')}</>}</small></div></div>
      {ea != null && <span className={`eapill mono ${ea >= 45 ? 'ok' : ea >= 30 ? 'mid' : 'low'}`}>EA {ea} · {ea >= 45 ? 'enough' : ea >= 30 ? 'reduced' : 'low'}</span>}
    </div>

    <div className="etrack">
      {segs.map((s, i) => <i key={i} style={{ left: `${s.left}%`, width: i < 2 && segs[i + 1].w > 0 ? `calc(${s.w}% - 2px)` : `${s.w}%`, borderRadius: i === 2 || !segs[i + 1].w ? '0 5px 5px 0' : undefined, background: Object.values(COL)[i] }} />)}
      {tg.kcal && <u style={{ left: pos(tg.kcal[0], max), width: `calc(${pos(tg.kcal[1], max)} - ${pos(tg.kcal[0], max)})` }} />}
    </div>
    <div className="epct mono">
      {hasMacros && segs.map((s, i) => s.w > 5 && <span key={i} style={{ left: `${s.left + s.w / 2}%` }}>{'CPF'[i]} {pct[i]}%</span>)}
      {tg.kcal && <span className="muted" style={{ left: `calc((${pos(tg.kcal[0], max)} + ${pos(tg.kcal[1], max)}) / 2)` }}>target</span>}
    </div>

    <div className="fmacs">
      <MacroRow k="carbs" label="Carbs" grams={t.carbs} value={t.carbs / kg} unit={`${gkg(t.carbs)} g/kg`}
        lo={tg.carbs_gkg[0]} hi={tg.carbs_gkg[1]} max={tg.carbs_gkg[1] * 1.3} target={`target ${tg.carbs_gkg[0]}–${tg.carbs_gkg[1]} g/kg`} />
      <MacroRow k="protein" label="Protein" grams={t.protein} value={t.protein / kg} unit={`${gkg(t.protein)} g/kg`}
        lo={1.6} hi={2.0} max={2.6} target="target 1.6–2.0 g/kg" />
      <MacroRow k="fat" label="Fat" grams={t.fat} value={fatPct} unit={`${gkg(t.fat)} g/kg`}
        lo={20} hi={35} max={50} target="guide 20–35% of energy" />
    </div>
  </div>
}
