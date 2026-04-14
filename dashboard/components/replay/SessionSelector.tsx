/**
 * SessionSelector.tsx — Session date picker for replay mode.
 *
 * On mount, calls fetchSessions() to populate a shadcn Select dropdown.
 * When a session is selected, activates replay mode via replayStore.setMode.
 * Renders in both live and replay modes so the operator can switch sessions
 * without manually editing the URL.
 *
 * Per D-13 (11-CONTEXT.md): sessions come from Phase 9 EventStore via FastAPI.
 * Returns null when no sessions are available (backend not ready / no history).
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
      <SelectTrigger className="w-[140px] h-11 font-mono text-[12px]">
        <SelectValue placeholder="Select session" />
      </SelectTrigger>
      <SelectContent>
        {sessions.map((s) => (
          <SelectItem key={s.session_id} value={s.session_id}>
            {s.session_id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
