export function fmtPrice(n: number | undefined | null): string {
  if (n == null) return '---'
  return n.toLocaleString('en-US', {
    minimumFractionDigits: n % 1 !== 0 ? 2 : 0,
    maximumFractionDigits: 2,
  })
}

export function fmtGex(n: number | undefined | null, dollar = false): string {
  if (n == null) return '---'
  const abs = Math.abs(n)
  const sign = n >= 0 ? '+' : '-'
  const d = dollar ? '$' : ''
  if (abs >= 1e9) return `${sign}${d}${(abs / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `${sign}${d}${Math.round(abs / 1e6)}M`
  if (abs >= 1e3) return `${sign}${d}${Math.round(abs / 1e3)}K`
  return `${sign}${d}${abs.toFixed(0)}`
}

export function signColor(n: number | undefined | null): string {
  if (n == null) return 'var(--terminal-dim)'
  return n >= 0 ? 'var(--terminal-green)' : 'var(--terminal-red)'
}

export function signGlow(n: number | undefined | null): string {
  if (n == null) return 'none'
  return n >= 0 ? 'var(--terminal-glow)' : 'var(--terminal-glow-red)'
}
