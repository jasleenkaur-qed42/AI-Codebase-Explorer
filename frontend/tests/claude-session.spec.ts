import { expect, test } from '@playwright/test';

test('posting a session explanation to the backend shows up live in the panel', async ({ page, request }) => {
  await page.goto('/');

  // This is the first spec to run (see playwright.config.ts: workers: 1,
  // fullyParallel: false, and other specs' own comments about "leftover
  // session events replayed from an earlier spec"), so it's the only place
  // the explorer's genuine "no query asked yet" empty state can be observed.
  await page.getByTestId('tab-explorer').click();
  await expect(page.getByTestId('explorer-empty-state')).toBeVisible();
  await expect(page.getByTestId('commit-graph-view')).toHaveCount(0);
  await page.getByTestId('tab-dashboard').click();

  await expect(page.getByTestId('claude-session-status')).toHaveText('● live');
  await expect(page.getByText('No answers yet', { exact: false })).toBeVisible();

  const response = await request.post('http://127.0.0.1:8420/api/session/explain', {
    data: {
      question: 'What does helper do?',
      answer_markdown: 'It parses configuration files and returns 1.',
      node_ids: ['function:foo.py:helper:1'],
      tools_invoked: [
        { command: 'query search', args: ['docstrings', 'configuration'], summary: '1 hit' },
      ],
    },
  });
  expect(response.ok()).toBeTruthy();

  await expect(page.getByTestId('claude-explanation-panel').getByText('What does helper do?')).toBeVisible();
  await expect(
    page.getByTestId('claude-explanation-panel').getByText('It parses configuration files and returns 1.'),
  ).toBeVisible();
  await expect(page.getByTestId('tools-invoked-panel').getByText('query search', { exact: false })).toBeVisible();
});
