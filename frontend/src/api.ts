import type { GraphData, GraphNode, NodeCitation, RepoRemote, RepoStats } from './types';

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchRepoStats(): Promise<RepoStats> {
  return getJson<RepoStats>('/api/repo/stats');
}

export function searchDocs(table: string, q: string, limit = 20) {
  const params = new URLSearchParams({ table, q, limit: String(limit) });
  return getJson<Array<{ node: GraphNode; text: string }>>(`/api/search?${params.toString()}`);
}

export function fetchSessionGraph(citations: NodeCitation[]): Promise<GraphData> {
  const primaryIds = citations.filter((c) => c.role === 'primary').map((c) => c.id);
  const supportingIds = citations.filter((c) => c.role === 'supporting').map((c) => c.id);
  const params = new URLSearchParams({
    node_ids: primaryIds.join(','),
    supporting_ids: supportingIds.join(','),
  });
  return getJson<GraphData>(`/api/graph/session?${params.toString()}`);
}

export function fetchRepoRemote(): Promise<RepoRemote> {
  return getJson<RepoRemote>('/api/repo/remote');
}
