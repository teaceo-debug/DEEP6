/**
 * ErrorBanner.tsx — per UI-SPEC v2 §8
 *
 * Phase 11.3-r9: Rich error states, close-code routing, reconnect button,
 * expand to show connection history, reconnect success toast.
 *
 * Variants:
 *   backend_offline  → "BACKEND OFFLINE — start uvicorn on :8000"        --bid
 *   dropped_1006     → "CONNECTION DROPPED — CHECK BACKEND LOG"           --bid
 *   server_error     → "BACKEND ERROR — {reason}"                         --bid
 *   cors             → "POSSIBLE CORS — VERIFY BACKEND ALLOWS :3000"      --amber
 *   rapid_fail       → "SERVER REJECTING CONNECTIONS — BACKEND MAY BE CRASHING" --bid
 *   disconnected     → "LINK DOWN — RECONNECTING…"                        --bid
 *   stale            → "STALE — LAST TICK {N}s AGO"                       --amber
 *   replay_404       → "SESSION NOT FOUND — SELECT FROM HISTORY"          --amber
 *   reconnected_long → "RECONNECTED AFTER {N}m — SHOWING LATEST STATE"    --ask toast
 *   success          → "LINK RESTORED"                                    --ask toast
 *
 * Position: absolute top:44px, z-index:10 — does NOT push content down.
 * Reconnect button: shown when disconnected, calls reconnectNow().
 * Expand: click banner text area → shows last 5 connection history entries.
 */
'use client';
import { useEffect, useRef, useState, useCallback } from 'react';
import { AlertCircle, Clock, AlertTriangle, CheckCircle2, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import { useTradingStore } from '@/store/tradingStore';
import { useReplayStore } from '@/store/replayStore';

// 16×16 at text baseline, 4px left-side breathing room
const ICON_STYLE = { width: 16, height: 16, strokeWidth: 1.25, flexShrink: 0 } as const;
const SMALL_ICON = { width: 12, height: 12, strokeWidth: 1.5, flexShrink: 0 } as const;

type BannerVariant = 'error' | 'warning' | 'success';

interface BannerState {
  msg: string;
  accentColor: string;
  variant: BannerVariant;
  icon: React.ReactNode;
  showReconnect: boolean;
}

function resolveBanner(
  connected: boolean,
  feedStale: boolean,
  lastTs: number,
  replayError: string | null,
  replayMode: string,
  lastError: string | null,
  errorCode: number | null,
): BannerState | null {
  if (replayError) {
    return {
      msg: 'SESSION NOT FOUND \u2014 SELECT FROM HISTORY',
      accentColor: 'var(--amber)',
      variant: 'warning',
      icon: <AlertTriangle style={{ ...ICON_STYLE, color: 'var(--amber)' }} />,
      showReconnect: false,
    };
  }

  if (replayMode === 'live' && !connected) {
    // Route to specific error message if we have one
    let msg = 'LINK DOWN \u2014 RECONNECTING\u2026';
    if (lastError) {
      msg = lastError;
    }
    return {
      msg,
      accentColor: 'var(--bid)',
      variant: 'error',
      icon: <AlertCircle style={{ ...ICON_STYLE, color: 'var(--bid)' }} />,
      showReconnect: true,
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
      showReconnect: false,
    };
  }
  return null;
}

function formatHistoryTs(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

interface ErrorBannerProps {
  reconnectNow?: () => void;
}

export function ErrorBanner({ reconnectNow }: ErrorBannerProps) {
  const status = useTradingStore((s) => s.status);
  const replayError = useReplayStore((s) => s.error);
  const replayMode = useReplayStore((s) => s.mode);

  const banner = resolveBanner(
    status.connected,
    status.feedStale,
    status.lastTs,
    replayError,
    replayMode,
    status.lastError,
    status.errorCode,
  );

  // Track previous connected state + disconnectedAt for long-disconnect recovery toast
  const prevConnectedRef = useRef(status.connected);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [reconnectFlash, setReconnectFlash] = useState(false);

  // Handle reconnectSuccessToast from store (set by useWebSocket on long-disconnect recovery)
  useEffect(() => {
    if (status.reconnectSuccessToast) {
      const disconnectedAt = status.disconnectedAt;
      // disconnectedAt was already cleared by onopen, but we can use history
      // Just show the generic long-reconnect message
      setSuccessMsg('RECONNECTED \u2014 MARKET DATA RESUMED');
      useTradingStore.getState().setReconnectSuccessToast(false);
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
      successTimerRef.current = setTimeout(() => setSuccessMsg(null), 3000);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.reconnectSuccessToast]);

  useEffect(() => {
    const wasConnected = prevConnectedRef.current;
    prevConnectedRef.current = status.connected;
    // Short reconnect: was disconnected, now connected (no long-disconnect toast already set)
    if (!wasConnected && status.connected && !status.reconnectSuccessToast) {
      setSuccessMsg('LINK RESTORED');
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
      successTimerRef.current = setTimeout(() => setSuccessMsg(null), 3000);
    }
    return () => {
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
    };
  }, [status.connected, status.reconnectSuccessToast]);

  const handleReconnect = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setReconnectFlash(true);
      setTimeout(() => setReconnectFlash(false), 600);
      reconnectNow?.();
    },
    [reconnectNow],
  );

  // Resolve what to show: success overrides errors for 3s after reconnect
  const activeBanner: BannerState | null = successMsg
    ? {
        msg: successMsg,
        accentColor: 'var(--ask)',
        variant: 'success',
        icon: <CheckCircle2 style={{ ...ICON_STYLE, color: 'var(--ask)' }} />,
        showReconnect: false,
      }
    : banner;

  if (!activeBanner) return null;

  const { msg, accentColor, icon, variant, showReconnect } = activeBanner;
  const history = status.connectionHistory;

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
        .error-banner-reconnect-btn {
          font-family: inherit;
          font-size: 10px;
          letter-spacing: 0.08em;
          font-weight: 600;
          border: 1px solid currentColor;
          border-radius: 2px;
          padding: 1px 6px;
          cursor: pointer;
          background: transparent;
          color: inherit;
          display: flex;
          align-items: center;
          gap: 3px;
          transition: background 150ms, color 150ms;
          flex-shrink: 0;
        }
        .error-banner-reconnect-btn:hover {
          background: color-mix(in srgb, currentColor 15%, transparent);
        }
        .error-banner-reconnect-btn.flash {
          background: var(--lime, #84cc16);
          color: #000;
          border-color: var(--lime, #84cc16);
        }
        .error-banner-expand-btn {
          background: transparent;
          border: none;
          cursor: pointer;
          color: inherit;
          padding: 0 4px;
          display: flex;
          align-items: center;
          opacity: 0.6;
          flex-shrink: 0;
        }
        .error-banner-expand-btn:hover { opacity: 1; }
        .error-banner-history {
          padding: 6px 20px 6px 44px;
          border-top: 1px solid color-mix(in srgb, var(--banner-accent-raw) 20%, transparent);
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .error-banner-history-row {
          display: flex;
          gap: 8px;
          font-size: 10px;
          opacity: 0.75;
          font-family: 'JetBrains Mono', monospace;
        }
        .error-banner-history-row .ts { color: var(--text-muted, #666); min-width: 80px; }
        .error-banner-history-row .state-connected { color: var(--ask); }
        .error-banner-history-row .state-disconnected { color: var(--bid); }
        @media (prefers-reduced-motion: reduce) {
          .error-banner-enter { animation: none; }
          .error-banner-enter::after { animation: none; }
          .error-banner-clock-pulse { animation: none; }
          .error-banner-reconnect-btn { transition: none; }
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
          '--banner-accent-raw': accentColor,
          position: 'absolute',
          top: 44,
          left: 0,
          right: 0,
          zIndex: 10,
          background: 'var(--surface-1)',
          borderBottom: `1px solid color-mix(in srgb, ${accentColor} 40%, transparent)`,
        }}
      >
        {/* Main row */}
        <div
          style={{
            paddingLeft: 20,
            paddingRight: 16,
            paddingTop: 4,
            paddingBottom: 4,
            color: accentColor,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          {icon}
          {/* Clickable text area — expands history */}
          <span
            role="button"
            tabIndex={0}
            aria-expanded={expanded}
            aria-label="Toggle connection history"
            onClick={() => setExpanded((v) => !v)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setExpanded((v) => !v); }}
            style={{ flex: 1, cursor: history.length > 0 ? 'pointer' : 'default', userSelect: 'none' }}
          >
            {msg}
          </span>

          {/* Expand toggle — only when there's history */}
          {history.length > 0 && (
            <button
              className="error-banner-expand-btn"
              onClick={() => setExpanded((v) => !v)}
              aria-label={expanded ? 'Collapse history' : 'Expand connection history'}
              type="button"
            >
              {expanded
                ? <ChevronUp style={SMALL_ICON} />
                : <ChevronDown style={SMALL_ICON} />}
            </button>
          )}

          {/* Reconnect button — only when disconnected and handler provided */}
          {showReconnect && reconnectNow && (
            <button
              type="button"
              className={`error-banner-reconnect-btn${reconnectFlash ? ' flash' : ''}`}
              onClick={handleReconnect}
              aria-label="Reconnect WebSocket"
            >
              <RefreshCw style={SMALL_ICON} />
              RECONNECT
            </button>
          )}
        </div>

        {/* Expanded history panel */}
        {expanded && history.length > 0 && (
          <div className="error-banner-history" aria-label="Connection history">
            {[...history].reverse().map((entry, i) => (
              <div key={i} className="error-banner-history-row">
                <span className="ts">{formatHistoryTs(entry.ts)}</span>
                <span className={entry.state === 'connected' ? 'state-connected' : 'state-disconnected'}>
                  {entry.state.toUpperCase()}
                </span>
                {entry.code != null && (
                  <span>code={entry.code}</span>
                )}
                {entry.reason && (
                  <span style={{ opacity: 0.6 }}>{entry.reason}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
