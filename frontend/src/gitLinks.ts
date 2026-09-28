export function commitUrl(githubBase: string | null, hash: string): string | null {
  return githubBase ? `${githubBase}/commit/${hash}` : null;
}

export function authorUrl(githubBase: string | null, authorNodeId: string): string | null {
  if (!githubBase) return null;
  const email = authorNodeId.replace(/^author:/, '');
  return `${githubBase}/commits?author=${encodeURIComponent(email)}`;
}
