/**
 * SessionSelector.tsx — Dark-variant shadcn Select per UI-SPEC v2 §4.8
 *
 * Trigger: --surface-2 bg, --rule-bright border, text-sm --text, 36px height
 * Content: --surface-1 bg, --rule-bright border, items dim/text on hover, active --lime
 * Data source + onChange contract unchanged from Phase 11.
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
  const sessionId = useReplayStore((s) => s.sessionId);

  useEffect(() => {
    fetchSessions()
      .then(setSessions)
      .catch(() => {
        // Silently ignore when backend is not ready yet
      });
  }, []);

  if (sessions.length === 0) return null;

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
        }}
      >
        <SelectValue placeholder="Select session" />
      </SelectTrigger>
      <SelectContent
        style={{
          background: 'var(--surface-1)',
          border: '1px solid var(--rule-bright)',
          borderRadius: 4,
        }}
      >
        {sessions.map((s) => (
          <SelectItem
            key={s.session_id}
            value={s.session_id}
            className="text-sm"
            style={{ color: 'var(--text-dim)' }}
          >
            {s.session_id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
