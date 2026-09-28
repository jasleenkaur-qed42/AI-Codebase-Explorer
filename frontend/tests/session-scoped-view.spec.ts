import { expect, test } from '@playwright/test';

async function postSessionExplain(request: import('@playwright/test').APIRequestContext) {
  const response = await request.post('http://127.0.0.1:8420/api/session/explain', {
    data: {
      question: 'How is helper implemented?',
      answer_markdown: 'It parses configuration files and returns 1.',
      node_ids: ['function:foo.py:helper:1'],
      tools_invoked: [],
    },
  });
  expect(response.ok()).toBeTruthy();
}

test('dashboard scopes to the cited nodes of the last question, with an escape hatch back to full stats', async ({
  page,
  request,
}) => {
  await page.goto('/');
  await postSessionExplain(request);

  const dashboard = page.getByTestId('session-dashboard');
  await expect(dashboard).toBeVisible();
  await expect(dashboard.getByText('How is helper implemented?')).toBeVisible();
  await expect(page.getByTestId('session-cited-nodes').getByText('helper')).toBeVisible();
  await expect(page.getByTestId('session-authors').getByText('Jane')).toBeVisible();

  await page.getByTestId('show-full-stats-button').click();
  await expect(page.getByText('Repository Stats & Engineering Health')).toBeVisible();
  await expect(page.getByTestId('show-session-stats-button')).toBeVisible();
});

test('explorer graph shows only commits until one is expanded, revealing its modified files and their author', async ({
  page,
  request,
}) => {
  await page.goto('/');
  await page.getByTestId('tab-explorer').click();
  await postSessionExplain(request);

  await expect(page.getByTestId('commit-graph-view').getByText('How is helper implemented?')).toBeVisible();

  const commitCards = page.getByTestId('commit-card');
  await expect(commitCards).toHaveCount(2, { timeout: 10_000 });
  await expect(page.getByTestId('file-card')).toHaveCount(0);

  const janeCommit = commitCards.filter({ hasText: 'initial commit' });
  await janeCommit.getByTestId('commit-card-header').click();

  const fileCard = janeCommit.getByTestId('file-card');
  await expect(fileCard).toHaveCount(1);
  await expect(fileCard.getByText('foo.py')).toBeVisible();
  await expect(fileCard.getByTestId('author-chip').getByText('Jane')).toBeVisible();

  // The other commit stays collapsed.
  const bobCommit = commitCards.filter({ hasText: 'document main' });
  await expect(bobCommit.getByTestId('file-card')).toHaveCount(0);
});

test('commits expand independently, each showing its own author', async ({ page, request }) => {
  await page.goto('/');
  await page.getByTestId('tab-explorer').click();
  await postSessionExplain(request);

  const commitCards = page.getByTestId('commit-card');
  await expect(commitCards).toHaveCount(2, { timeout: 10_000 });
  const janeCommit = commitCards.filter({ hasText: 'initial commit' });
  const bobCommit = commitCards.filter({ hasText: 'document main' });

  await janeCommit.getByTestId('commit-card-header').click();
  await bobCommit.getByTestId('commit-card-header').click();

  await expect(janeCommit.getByTestId('file-card')).toHaveCount(1);
  await expect(bobCommit.getByTestId('file-card')).toHaveCount(1);
  await expect(janeCommit.getByTestId('author-chip').getByText('Jane')).toBeVisible();
  await expect(bobCommit.getByTestId('author-chip').getByText('Bob')).toBeVisible();

  // Collapsing one leaves the other expanded.
  await janeCommit.getByTestId('commit-card-header').click();
  await expect(janeCommit.getByTestId('file-card')).toHaveCount(0);
  await expect(bobCommit.getByTestId('file-card')).toHaveCount(1);
});

test('dashboard omits commits for nodes cited only as supporting context', async ({ page, request }) => {
  await page.goto('/');
  const response = await request.post('http://127.0.0.1:8420/api/session/explain', {
    data: {
      question: 'Where is the config file referenced?',
      answer_markdown: 'foo.py is mentioned only as context here.',
      node_ids: [{ id: 'file:foo.py', role: 'supporting' }],
      tools_invoked: [],
    },
  });
  expect(response.ok()).toBeTruthy();

  const dashboard = page.getByTestId('session-dashboard');
  await expect(dashboard).toBeVisible();
  await expect(page.getByTestId('session-cited-nodes').getByText('foo.py')).toBeVisible();
  await expect(page.getByTestId('session-commits').locator('li')).toHaveCount(0);
});

test('the commit arrow opens its GitHub link without toggling expansion, and an author chip opens their GitHub profile', async ({
  page,
  request,
}) => {
  await page.goto('/');
  await page.getByTestId('tab-explorer').click();
  await postSessionExplain(request);

  const commitCard = page.getByTestId('commit-card').filter({ hasText: 'initial commit' });
  await expect(commitCard).toBeVisible({ timeout: 10_000 });

  const [commitPopup] = await Promise.all([
    page.waitForEvent('popup'),
    commitCard.getByTestId('commit-link-button').click(),
  ]);
  await expect(commitPopup).toHaveURL(/https:\/\/github\.com\/acme\/app\/commit\/.+/);
  await commitPopup.close();
  await expect(commitCard.getByTestId('file-card')).toHaveCount(0);

  await commitCard.getByTestId('commit-card-header').click();
  const authorChip = commitCard.getByTestId('author-chip').filter({ hasText: 'Jane' });
  const [authorPopup] = await Promise.all([page.waitForEvent('popup'), authorChip.click()]);
  await expect(authorPopup).toHaveURL('https://github.com/acme/app/commits?author=jane%40example.com');
  await authorPopup.close();
});
