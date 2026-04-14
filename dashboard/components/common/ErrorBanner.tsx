/**
 * ErrorBanner.tsx — per UI-SPEC v2 §8
 *
 * Copy (exact):
 *   disconnected → "LINK DOWN. RETRYING…"              --bid, AlertCircle icon
 *   stale        → "STALE — last tick {N}s ago"         --amber, Clock icon
 *   replay_404   → "SESSION NOT FOUND. SELECT FROM HISTORY."  --amber, AlertTriangle icon
 *   success      → custom success variant               --ask, CheckCircle2 icon, auto-dismiss 3s
 *
 * Position: position:absolute, top:44px, z-index:10 — does NOT push content down.
 * Animation: slide-down from top, 200ms ease-out on appear.
 * Success variant: auto-dismisses after 3s with fade.
 */
'use client';
import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Clock, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { useTradingStore } from '@/store/tradingStore';
import { useReplayStore } from '@/store/replayStore';

const ICON_STYLE = { width: 14, height: 14, strokeWidth: 1.25, flexShrink: 0 } as const;

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
      msg: 'SESSION NOT FOUND. SELECT FROM HISTORY.',
      accentColor: 'var(--amber)',
      variant: 'warning',
      icon: <AlertTriangle style={{ ...ICON_STYLE, color: 'var(--amber)' }} />,
    };
  }
  if (replayMode === 'live' && !connected) {
    return {
      msg: 'LINK DOWN. RETRYING\u2026',
      accentColor: 'var(--bid)',
      variant: 'error',
      icon: <AlertCircle style={{ ...ICON_STYLE, color: 'var(--bid)' }} />,
    };
  }
  if (feedStale) {
    const staleSecs = lastTs > 0 ? Math.round(Date.now() / 1000 - lastTs) : 0;
    return {
      msg: `STALE \u2014 last tick ${staleSecs}s ago`,
      accentColor: 'var(--amber)',
      variant: 'warning',
      icon: <Clock style={{ ...ICON_STYLE, color: 'var(--amber)' }} />,
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
      setSuccessMsg('RECONNECTED.');
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

  const { msg, accentColor, icon } = activeBanner;

  return (
    <>
      <style>{`
        @keyframes banner-slide-down {
          from { transform: translateY(-100%); opacity: 0; }
          to   { transform: translateY(0);     opacity: 1; }
        }
        .error-banner-enter {
          animation: banner-slide-down 200ms ease-out forwards;
        }
        @media (prefers-reduced-motion: reduce) {
          .error-banner-enter { animation: none; }
        }
      `}</style>
      <div
        role="alert"
        aria-live="polite"
        className="text-sm label-tracked error-banner-enter"
        style={{
          position: 'absolute',
          top: 44,
          left: 0,
          right: 0,
          zIndex: 10,
          background: 'var(--surface-1)',
          borderBottom: `1px solid color-mix(in srgb, ${accentColor} 40%, transparent)`,
          padding: '6px 16px',
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
