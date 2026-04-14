/**
 * ErrorBanner.tsx — per UI-SPEC v2 §8
 *
 * Copy (exact):
 *   disconnected → "LINK DOWN — RECONNECTING…"                --bid, AlertCircle icon
 *   stale        → "STALE — LAST TICK {N}s AGO"               --amber, Clock icon
 *   replay_404   → "SESSION NOT FOUND — SELECT FROM HISTORY"  --amber, AlertTriangle icon
 *   success      → "LINK RESTORED"                            --ask, CheckCircle2 icon, auto-dismiss 3s
 *
 * Position: position:absolute, top:44px, z-index:10 — does NOT push content down.
 * Animation: slide-down from top, 200ms ease-out on appear.
 *            Bottom border fades in/out with the banner (accent color, 40% alpha).
 * Success variant: auto-dismisses after 3s with fade.
 * Stale variant:   Clock icon pulses at 2s loop.
 */
'use client';
import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Clock, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { useTradingStore } from '@/store/tradingStore';
import { useReplayStore } from '@/store/replayStore';

// 16×16 at text baseline, 4px left-side breathing room
const ICON_STYLE = { width: 16, height: 16, strokeWidth: 1.25, flexShrink: 0 } as const;

type BannerVariant = 'error' | 'warning' | 'success';

interface BannerState {
  msg: string;
  accentColor: string;
  variant: BannerVariant;
  icon: React.ReactNode;
}

function resolveBanner(
  connected: boolean,
  feedStale: boolean,
  lastTs: number,
  replayError: string | null,
  replayMode: string,
): BannerState | null {
  if (replayError) {
    return {
      msg: 'SESSION NOT FOUND \u2014 SELECT FROM HISTORY',
      accentColor: 'var(--amber)',
      variant: 'warning',
      icon: <AlertTriangle style={{ ...ICON_STYLE, color: 'var(--amber)' }} />,
    };
  }
  if (replayMode === 'live' && !connected) {
    return {
      msg: 'LINK DOWN \u2014 RECONNECTING\u2026',
      accentColor: 'var(--bid)',
      variant: 'error',
      icon: <AlertCircle style={{ ...ICON_STYLE, color: 'var(--bid)' }} />,
    };
  }
  if (feedStale) {
    const staleSecs = lastTs > 0 ? Math.round(Date.now() / 1000 - lastTs) : 0;
    return {
      msg: `STALE \u2014 LAST TICK ${staleSecs}s AGO`,
      accentColor: 'var(--amber)',
      variant: 'warning',
      icon: (
        <Clock
          className="error-banner-clock-pulse"
          style={{ ...ICON_STYLE, color: 'var(--amber)' }}
        />
      ),
    };
  }
  return null;
}

export function ErrorBanner() {
  const status = useTradingStore((s) => s.status);
  const replayError = useReplayStore((s) => s.error);
  const replayMode = useReplayStore((s) => s.mode);

  const banner = resolveBanner(
    status.connected,
    status.feedStale,
    status.lastTs,
    replayError,
    replayMode,
  );

  // Track previous connected state to show a success flash when reconnected
  const prevConnectedRef = useRef(status.connected);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const wasConnected = prevConnectedRef.current;
    prevConnectedRef.current = status.connected;
    // Reconnect: was disconnected, now connected
    if (!wasConnected && status.connected) {
      setSuccessMsg('LINK RESTORED');
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
      successTimerRef.current = setTimeout(() => setSuccessMsg(null), 3000);
    }
    return () => {
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
    };
  }, [status.connected]);

  // Resolve what to show: success overrides errors for 3s after reconnect
  const activeBanner: BannerState | null = successMsg
    ? {
        msg: successMsg,
        accentColor: 'var(--ask)',
        variant: 'success',
        icon: <CheckCircle2 style={{ ...ICON_STYLE, color: 'var(--ask)' }} />,
      }
    : banner;

  if (!activeBanner) return null;

  const { msg, accentColor, icon, variant } = activeBanner;

  return (
    <>
      <style>{`
        @keyframes banner-slide-down {
          from { transform: translateY(-100%); opacity: 0; }
          to   { transform: translateY(0);     opacity: 1; }
        }
        @keyframes banner-bottom-line-in {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes banner-clock-pulse {
          0%, 100% { opacity: 0.5; }
          50%       { opacity: 1.0; }
        }
        .error-banner-enter {
          animation: banner-slide-down 200ms ease-out forwards;
        }
        .error-banner-enter::after {
          content: "";
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 1px;
          background: var(--banner-accent);
          animation: banner-bottom-line-in 300ms ease-out forwards;
        }
        .error-banner-clock-pulse {
          animation: banner-clock-pulse 2s ease-in-out infinite;
        }
        @media (prefers-reduced-motion: reduce) {
          .error-banner-enter { animation: none; }
          .error-banner-enter::after { animation: none; }
          .error-banner-clock-pulse { animation: none; }
        }
      `}</style>
      <div
        role="alert"
        aria-live="polite"
        data-variant={variant}
        className="text-sm label-tracked error-banner-enter"
        style={{
          /* @ts-expect-error -- CSS custom property for ::after bottom line */
          '--banner-accent': `color-mix(in srgb, ${accentColor} 40%, transparent)`,
          position: 'absolute',
          top: 44,
          left: 0,
          right: 0,
          zIndex: 10,
          background: 'var(--surface-1)',
          borderBottom: `1px solid color-mix(in srgb, ${accentColor} 40%, transparent)`,
          // 4px icon breathing room on left, 8px gap between icon and text via flex gap
          paddingLeft: 20,
          paddingRight: 16,
          paddingTop: 6,
          paddingBottom: 6,
          color: accentColor,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        {icon}
        {msg}
      </div>
    </>
  );
}
