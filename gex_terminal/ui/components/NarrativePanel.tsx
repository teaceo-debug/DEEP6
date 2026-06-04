export interface NarrativePanelProps {
  text: string
  model: string
  cached: boolean
  cost_usd: number
}

function wrapText(text: string, maxLen: number): string[] {
  const words = text.split(' ')
  const lines: string[] = []
  let line = ''
  for (const word of words) {
    if (line && line.length + 1 + word.length > maxLen) {
      lines.push(line)
      line = word
    } else {
      line = line ? `${line} ${word}` : word
    }
  }
  if (line) lines.push(line)
  return lines
}

export function NarrativePanel({
  text, model, cached, cost_usd,
}: NarrativePanelProps) {
  const wrapped = wrapText(text, 84)
  const line1 = wrapped[0] ?? ''
  const line2 = wrapped[1] ?? ''

  const badge = cached
    ? `[${model.toUpperCase()} \u00B7 CACHED]`
    : `[${model.toUpperCase()} \u00B7 LIVE \u00B7 $${cost_usd.toFixed(3)}]`

  return (
    <div className="panel-section" data-testid="narrative-panel">
      <div className="panel-row">
        <span className="text-dim">{'AI: '}{line1}</span>
      </div>
      <div className="panel-row">
        <span className="text-dim">{'    '}{line2}</span>
      </div>
      <div className="panel-row">
        <span className="text-dark">{'    '}{badge}</span>
      </div>
    </div>
  )
}
