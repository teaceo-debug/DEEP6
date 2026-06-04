'use client'

interface TerminalFrameProps {
  children: React.ReactNode
}

export function TerminalFrame({ children }: TerminalFrameProps) {
  return (
    <div className="terminal-frame" data-testid="terminal-frame">
      {children}
    </div>
  )
}
