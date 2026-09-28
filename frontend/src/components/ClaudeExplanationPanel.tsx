import type { SessionEvent } from '../types';

interface ClaudeExplanationPanelProps {
  event: SessionEvent | null;
  connected: boolean;
}

export function ClaudeExplanationPanel({ event, connected }: ClaudeExplanationPanelProps) {
  return (
    <div data-testid="claude-explanation-panel" style={{ padding: '8px 16px', borderBottom: '1px solid #e5e7eb' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong style={{ fontSize: 12, color: '#6b7280' }}>CLAUDE</strong>
        <span
          data-testid="claude-session-status"
          style={{ fontSize: 11, color: connected ? '#16a34a' : '#9ca3af' }}
        >
          {connected ? '● live' : '○ waiting for session'}
        </span>
      </div>
      {event ? (
        <div style={{ marginTop: 4 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{event.question}</div>
          <div style={{ fontSize: 13, marginTop: 2, whiteSpace: 'pre-wrap' }}>{event.answer_markdown}</div>
        </div>
      ) : (
        <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
          No answers yet — ask a question in Claude Code while this repo's server is running.
        </div>
      )}
    </div>
  );
}
