import { useQuery } from '@tanstack/react-query';
import { fetchRepoRemote, fetchRepoStats, fetchSessionGraph } from '../api';
import { CommitGraph } from '../components/CommitGraph';
import { RepoStatsPanel } from '../components/RepoStatsPanel';
import type { SessionEvent } from '../types';

interface ExplorerProps {
  event: SessionEvent | null;
}

export function Explorer({ event }: ExplorerProps) {
  const { data: remote } = useQuery({ queryKey: ['repo-remote'], queryFn: fetchRepoRemote });
  const githubBase = remote?.github_base ?? null;

  const { data: stats } = useQuery({ queryKey: ['repo-stats'], queryFn: fetchRepoStats, enabled: !event });

  const nodeIdsKey = event ? event.node_ids.map((c) => `${c.id}:${c.role}`).join(',') : null;
  const { data, isLoading, error } = useQuery({
    queryKey: ['session-graph', nodeIdsKey],
    queryFn: () => fetchSessionGraph(event!.node_ids),
    enabled: Boolean(event),
  });

  if (!event) {
    return (
      <div style={{ padding: 24 }} data-testid="explorer-empty-state">
        <p style={{ color: '#6b7280' }}>Ask a question to see the commit graph for the relevant files.</p>
        {stats && <RepoStatsPanel data={stats} />}
      </div>
    );
  }

  return (
    <div style={{ paddingLeft: 24, paddingRight: 24 }} data-testid="commit-graph-view">
      {isLoading && <div>Loading commits…</div>}
      {error && <div>Failed to load commits.</div>}
      {data && <CommitGraph data={data} githubBase={githubBase} />}
    </div>
  );
}
