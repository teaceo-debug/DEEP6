/**
 * ReplayControls.tsx — Bottom 48px replay controls strip.
 *
 * Per UI-SPEC §Replay Controls Strip:
 *   - SessionSelector (left edge)
 *   - SkipBack / Play|Pause / SkipForward (lucide-react icons, 44×44 touch targets)
 *   - Jump-to-bar input (80px, monospace, placeholder "bar #")
 *   - Bar counter: "N / total"
 *   - Speed selector: 1x / 2x / 5x / auto (72px)
 *   - LIVE button (56px, active state: lime bg / dark text)
 *
 * In live mode: all replay controls are disabled (opacity-30, pointer-events-none)
 * except the LIVE indicator which shows active state.
 */
'use client';
import { SkipBack, Play, Pause, SkipForward } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { useReplayStore, type ReplaySpeed } from '@/store/replayStore';
import { SessionSelector } from './SessionSelector';

export function ReplayControls() {
  const mode = useReplayStore((s) => s.mode);
  const currentBarIndex = useReplayStore((s) => s.currentBarIndex);
  const totalBars = useReplayStore((s) => s.totalBars);
  const speed = useReplayStore((s) => s.speed);
  const playing = useReplayStore((s) => s.playing);

  // Access actions without re-rendering on action identity changes
  const actions = useReplayStore.getState;
  const disabled = mode !== 'replay';

  return (
    <footer
      className="shrink-0 flex items-center px-4 gap-2 text-[13px]"
      style={{
        height: '48px',
        background: 'var(--bg-surface)',
        borderTop: '1px solid var(--border-subtle)',
      }}
    >
      {/* Session selector — always interactive so operator can switch sessions */}
      <SessionSelector />

      {/* Replay controls — disabled in live mode */}
      <div
        className={`flex items-center gap-2 ${disabled ? 'opacity-30 pointer-events-none' : ''}`}
      >
        <Button
          variant="ghost"
          size="icon"
          aria-label="Previous bar"
          className="h-11 w-11"
          onClick={() => actions().rewindBar()}
        >
          <SkipBack className="h-4 w-4" />
        </Button>

        {playing ? (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Pause replay"
            className="h-11 w-11"
            onClick={() => actions().pause()}
          >
            <Pause className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Play replay"
            className="h-11 w-11"
            onClick={() => actions().play()}
          >
            <Play className="h-4 w-4" />
          </Button>
        )}

        <Button
          variant="ghost"
          size="icon"
          aria-label="Next bar"
          className="h-11 w-11"
          onClick={() => actions().advanceBar()}
        >
          <SkipForward className="h-4 w-4" />
        </Button>

        <Input
          placeholder="bar #"
          className="w-20 font-mono"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              const n = parseInt((e.target as HTMLInputElement).value, 10);
              if (!Number.isNaN(n)) actions().jumpToBar(n);
            }
          }}
        />

        <span
          className="font-mono text-[12px]"
          style={{ color: 'var(--muted)' }}
        >
          {currentBarIndex + 1} / {totalBars}
        </span>

        <span style={{ color: 'var(--muted)', marginLeft: '8px' }}>Speed</span>

        <Select
          value={speed}
          onValueChange={(v) => actions().setSpeed(v as ReplaySpeed)}
        >
          <SelectTrigger className="w-[72px] h-11">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1x">1x</SelectItem>
            <SelectItem value="2x">2x</SelectItem>
            <SelectItem value="5x">5x</SelectItem>
            <SelectItem value="auto">auto</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* LIVE button — always interactive; active state when mode === 'live' */}
      <Button
        variant="outline"
        className="ml-auto w-14"
        style={
          mode === 'live'
            ? { background: 'var(--type-a)', color: 'var(--bg-base)' }
            : {}
        }
        onClick={() => actions().setMode('live', null)}
      >
        LIVE
      </Button>
    </footer>
  );
}
