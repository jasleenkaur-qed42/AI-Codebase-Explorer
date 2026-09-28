import type { SessionEvent } from '../types';

interface ToolsInvokedPanelProps {
  event: SessionEvent | null;
}

export function ToolsInvokedPanel({ event }: ToolsInvokedPanelProps) {
  const tools = event?.tools_invoked ?? [];

  return (
    <div data-testid="tools-invoked-panel" style={{ padding: '8px 16px', borderBottom: '1px solid #e5e7eb' }}>
      <strong style={{ fontSize: 12, color: '#6b7280' }}>TOOLS INVOKED</strong>
      {tools.length === 0 ? (
        <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>None yet.</div>
      ) : (
        <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 12 }}>
          {tools.map((tool, i) => (
            <li key={i}>
              <code>{tool.command} {tool.args.join(' ')}</code>
              {tool.summary && <span style={{ color: '#6b7280' }}> — {tool.summary}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
