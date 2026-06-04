import { fmtPrice } from './format'

export interface LevelsPanelProps {
  gamma_flip?: number
  call_wall?: number
  put_wall?: number
  hvl?: number
  zero_dte_magnet?: number
  expected_move_up?: number
  expected_move_down?: number
}

export function LevelsPanel({
  gamma_flip, call_wall, put_wall, hvl,
  zero_dte_magnet, expected_move_up, expected_move_down,
}: LevelsPanelProps) {
  const mid = expected_move_up != null && expected_move_down != null
    ? (expected_move_up + expected_move_down) / 2
    : null
  const ptsUp = mid != null && expected_move_up != null
    ? Math.round(expected_move_up - mid)
    : null
  const ptsDn = mid != null && expected_move_down != null
    ? Math.round(mid - expected_move_down)
    : null

  return (
    <div className="panel-section" data-testid="levels-panel">
      <div className="panel-row">
        <span className="text-dim text-bold">{'LEVELS'}</span>
      </div>
      <div className="panel-row">
        <span className="text-dim">{'GAMMA FLIP: '}</span>
        <span className="text-bright">{fmtPrice(gamma_flip)}</span>
        {'  '}
        <span className="text-bright">{'\u25B2 above=bullish'}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'CALL WALL: '}</span>
        <span className="text-bright">{fmtPrice(call_wall)}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'PUT WALL: '}</span>
        <span className="text-bright">{fmtPrice(put_wall)}</span>
      </div>
      <div className="panel-row">
        <span className="text-dim">{'HVL:        '}</span>
        <span className="text-bright">{fmtPrice(hvl)}</span>
        {'                   '}
        <span className="text-dark">{'\u2502 '}</span>
        <span className="text-dim">{'0DTE MAGNET: '}</span>
        <span className="text-bright">{fmtPrice(zero_dte_magnet)}</span>
      </div>
      <div className="panel-row">
        <span className="text-dim">{'EXP MOVE+:  '}</span>
        <span className="text-bright">{fmtPrice(expected_move_up)}</span>
        {ptsUp != null && <span className="text-dim">{` (+${ptsUp}pts)`}</span>}
        {'         '}
        <span className="text-dark">{'\u2502 '}</span>
        <span className="text-dim">{'EXP MOVE-: '}</span>
        <span className="text-bright">{fmtPrice(expected_move_down)}</span>
        {ptsDn != null && <span className="text-dim">{` (-${ptsDn}pts)`}</span>}
      </div>
    </div>
  )
}
