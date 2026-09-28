import type { RepoStats } from '../types';

function StatTile({ label, value }: { label: string; value: number | string }) {
  return (
    <div
      data-testid="stat-tile"
      style={{
        background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8,
        padding: '16px 20px', minWidth: 140,
      }}
    >
      <div style={{ fontSize: 28, fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase' }}>{label}</div>
    </div>
  );
}

export function RepoStatsPanel({ data }: { data: RepoStats }) {
  const totalNodes = Object.values(data.node_counts).reduce((a, b) => a + b, 0);
  const totalEdges = Object.values(data.edge_counts).reduce((a, b) => a + b, 0);

  return (
    <>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <StatTile label="Nodes" value={totalNodes} />
        <StatTile label="Edges" value={totalEdges} />
        <StatTile label="Files" value={data.node_counts.file ?? 0} />
        <StatTile label="Commits" value={data.commit_count} />
        <StatTile label="Authors" value={data.author_count} />
      </div>

      <div style={{ display: 'flex', gap: 32, marginTop: 24 }}>
        <div>
          <h3>Frequent changed files</h3>
          <ol>
            {data.top_churn.map((n) => (
              <li key={n.id}>{n.path} ({String(n.attrs.churn ?? 0)} commits)</li>
            ))}
          </ol>
        </div>
        <div>
          <h3>Risky files</h3>
          <ol>
            {data.top_bus_factor_risk.map((n) => (
              <li key={n.id}>
                {n.path} (Modified by {String(n.attrs.bus_factor ?? 0)} authors {String(n.attrs.churn ?? 0)} times)
              </li>
            ))}
          </ol>
        </div>
      </div>
    </>
  );
}
