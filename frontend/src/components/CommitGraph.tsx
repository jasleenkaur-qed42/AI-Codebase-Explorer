import { useState } from 'react';
import { commitUrl } from '../gitLinks';
import type { GraphData, GraphNode } from '../types';
import AuthorChip from './AuthChip';

function openLink(url: string | null) {
  if (url) window.open(url, '_blank', 'noopener,noreferrer');
}

function FileCard({ file, authors, githubBase }: { file: GraphNode; authors: GraphNode[]; githubBase: string | null }) {
  return (
    <div
      data-testid="file-card"
      style={{
        border: '1px solid #e5e7eb', borderRadius: 6, padding: '8px 12px',
        marginTop: 8, marginLeft: 24, background: '#f8fafc',
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 600 }}>{file.name}</div>
      <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
        {authors.map((author) => (
          <AuthorChip key={author.id} author={author} githubBase={githubBase} />
        ))}
      </div>
    </div>
  );
}

function CommitCard({
  commit,
  files,
  authors,
  githubBase,
  expanded,
  onToggle,
}: {
  commit: GraphNode;
  files: GraphNode[];
  authors: GraphNode[];
  githubBase: string | null;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div data-testid="commit-card" style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 14px', marginBottom: 10 }}>
      <div
        data-testid="commit-card-header"
        onClick={onToggle}
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
      >
        <div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{commit.docstring || commit.name}</div>
          <div style={{ fontSize: 11, color: '#6b7280' }}>{commit.name.slice(0, 8)}</div>
        </div>
        <button
          data-testid="commit-link-button"
          aria-label="Open commit on GitHub"
          onClick={(e) => {
            e.stopPropagation();
            openLink(commitUrl(githubBase, commit.name));
          }}
          style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 16, color: '#64748b' }}
        >
          ↗
        </button>
      </div>
      {expanded && (
        <div data-testid="commit-files">
          {files.map((file) => (
            <FileCard key={file.id} file={file} authors={authors} githubBase={githubBase} />
          ))}
        </div>
      )}
    </div>
  );
}

export function CommitGraph({ data, githubBase }: { data: GraphData; githubBase: string | null }) {
  const [expandedCommits, setExpandedCommits] = useState<Set<string>>(new Set());

  const commits = data.nodes.filter((n) => n.type === 'commit');
  const filesById = new Map(data.nodes.filter((n) => n.type === 'file').map((n) => [n.id, n]));
  const authorsById = new Map(data.nodes.filter((n) => n.type === 'author').map((n) => [n.id, n]));

  const toggle = (commitId: string) => {
    setExpandedCommits((prev) => {
      const next = new Set(prev);
      if (next.has(commitId)) next.delete(commitId);
      else next.add(commitId);
      return next;
    });
  };
      
  return (
    <div data-testid="commit-graph">
      {commits.map((commit) => {
        const files = data.edges
          .filter((e) => e.src_id === commit.id && e.type === 'modifies')
          .map((e) => filesById.get(e.dst_id))
          .filter((f): f is GraphNode => Boolean(f));
        const authors = data.edges
          .filter((e) => e.src_id === commit.id && e.type === 'authored_by')
          .map((e) => authorsById.get(e.dst_id))
          .filter((a): a is GraphNode => Boolean(a));

        return (
          <CommitCard
            key={commit.id}
            commit={commit}
            files={files}
            authors={authors}
            githubBase={githubBase}
            expanded={expandedCommits.has(commit.id)}
            onToggle={() => toggle(commit.id)}
          />
        );
      })}
    </div>
  );
}
