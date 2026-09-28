import type { GraphNode } from '../types';
import { authorUrl } from '../gitLinks';

function openLink(url: string | null) {
  if (url) window.open(url, '_blank', 'noopener,noreferrer');
}

function AuthorChip({ author, githubBase }: { author: GraphNode; githubBase: string | null }) {
  return (
    <button
      data-testid="author-chip"
      onClick={(e) => {
        e.stopPropagation();
        openLink(authorUrl(githubBase, author.id));
      }}
      style={{
        fontSize: 11, padding: '2px 8px', borderRadius: 999,
        border: '1px solid #fdba74', background: '#fff7ed', color: '#9a3412',
        cursor: 'pointer', marginRight: 4
      }}
    >
      {author.name}
    </button>
  );
}

export default AuthorChip;
