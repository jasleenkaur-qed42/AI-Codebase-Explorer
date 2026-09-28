export interface GraphNode {
  id: string;
  type: string;
  name: string;
  path: string | null;
  start_line: number | null;
  end_line: number | null;
  docstring: string | null;
  attrs: Record<string, unknown>;
}

export interface GraphEdge {
  src_id: string;
  dst_id: string;
  type: string;
  attrs: Record<string, unknown>;
}

export interface RepoStats {
  node_counts: Record<string, number>;
  edge_counts: Record<string, number>;
  commit_count: number;
  author_count: number;
  top_churn: GraphNode[];
  top_bus_factor_risk: GraphNode[];
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated?: boolean;
}

export interface ToolInvocation {
  command: string;
  args: string[];
  summary: string;
}

export interface NodeCitation {
  id: string;
  role: 'primary' | 'supporting';
}

export interface SessionEvent {
  question: string;
  answer_markdown: string;
  node_ids: NodeCitation[];
  tools_invoked: ToolInvocation[];
  timestamp: number;
}

export interface RepoRemote {
  github_base: string | null;
}
