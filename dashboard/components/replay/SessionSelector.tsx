/**
 * SessionSelector.tsx — Dark-variant shadcn Select per UI-SPEC v2 §4.8
 *
 * Trigger: 36px height, --surface-2 bg, --rule-bright border, focus adds --lime 2px outline
 * Content: --surface-2 bg, --rule-bright border, 4px padding
 * Selected option: --lime ▸ prefix character
 * Hover option: --surface-1 bg, 100ms transition
 * Empty/loading state: "No sessions available — waiting for backend…" in --text-mute italic
 */
'use client';
import { useEffect, useState } from 'react';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { fetchSessions, type SessionMeta } from '@/lib/replayClient';
import { useReplayStore } from '@/store/replayStore';

export function SessionSelector() {
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [loaded, setLoaded] = useState(false);
  const sessionId = useReplayStore((s) => s.sessionId);

  useEffect(() => {
    fetchSessions()
      .then((data) => {
        setSessions(data);
        setLoaded(true);
      })
      .catch(() => {
        setLoaded(true);
        // Silently ignore when backend is not ready yet
      });
  }, []);

  // Show empty-state placeholder before data arrives or when no sessions exist
  if (loaded && sessions.length === 0) {
    return (
      <div
        style={{
          height: 36,
          minWidth: 140,
          display: 'flex',
          alignItems: 'center',
          padding: '0 12px',
          background: 'var(--surface-2)',
          border: '1px solid var(--rule-bright)',
          borderRadius: 4,
          fontSize: 11,
          fontFamily: 'var(--font-jetbrains-mono)',
          color: 'var(--text-mute)',
          fontStyle: 'italic',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          userSelect: 'none',
        }}
      >
        No sessions available — waiting for backend…
      </div>
    );
  }

  // Show skeleton trigger while loading
  if (!loaded) {
    return (
      <div
        style={{
          height: 36,
          minWidth: 140,
          background: 'var(--surface-2)',
          border: '1px solid var(--rule)',
          borderRadius: 4,
          display: 'flex',
          alignItems: 'center',
          padding: '0 12px',
          fontSize: 11,
          color: 'var(--text-mute)',
          fontFamily: 'var(--font-jetbrains-mono)',
        }}
      >
        …
      </div>
    );
  }

  return (
    <Select
      value={sessionId ?? ''}
      onValueChange={(v) => useReplayStore.getState().setMode('replay', v)}
    >
      <SelectTrigger
        className="text-sm tnum"
        style={{
          height: 36,
          minWidth: 140,
          background: 'var(--surface-2)',
          border: '1px solid var(--rule-bright)',
          color: 'var(--text)',
          padding: '0 12px',
          borderRadius: 4,
          // Focus ring: --lime 2px (globals.css :focus-visible handles outline,
          // but we reinforce border on focus via inline style swap in JS is complex —
          // the globals.css :focus-visible outline covers this correctly)
        }}
      >
        <SelectValue placeholder="Select session" />
      </SelectTrigger>
      <SelectContent
        style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--rule-bright)',
          borderRadius: 4,
          padding: '4px 0',
        }}
      >
        {sessions.map((s) => (
          <SelectItem
            key={s.session_id}
            value={s.session_id}
            className="text-sm"
            style={{
              color: s.session_id === sessionId ? 'var(--text)' : 'var(--text-dim)',
              // ▸ prefix for selected item via pseudo-content not possible inline;
              // we prefix the text content itself
            }}
          >
            {s.session_id === sessionId ? `▸ ${s.session_id}` : s.session_id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
