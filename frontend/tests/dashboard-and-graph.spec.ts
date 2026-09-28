import { expect, type Page, test } from '@playwright/test';

// All specs in this suite share one backend process, so an earlier spec's
// session/explain POST can still be in the event history (replayed over SSE
// on connect) when this test's page loads -- these tests are about the
// full-repo view specifically, so back out of a scoped view if one shows up.
async function ensureFullRepoView(page: Page, showFullViewTestId: string) {
  const button = page.getByTestId(showFullViewTestId);
  try {
    // Give a leftover session event (replayed over SSE from another spec)
    // a moment to arrive and swap in the scoped view, so we don't check
    // for "no scoped view" before it's had a chance to show up.
    await button.waitFor({ state: 'visible', timeout: 1_500 });
    await button.click();
  } catch {
    // No scoped view showed up -- already on the full-repo view.
  }
}

test('dashboard shows repository stats', async ({ page }) => {
  await page.goto('/');
  await ensureFullRepoView(page, 'show-full-stats-button');

  await expect(page.getByText('Repository Stats & Engineering Health')).toBeVisible();
  await expect(page.getByTestId('stat-tile').first()).toBeVisible();
  await expect(page.getByText('foo.py', { exact: false }).first()).toBeVisible();
});

test('explorer shows the commit graph for the last question, with no full-graph fallback', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('tab-explorer').click();

  // A prior spec (claude-session.spec.ts) already posted a question, and
  // that event replays over SSE on connect -- so by this point the explorer
  // should already be showing its commit graph, not the empty state.
  await expect(page.getByTestId('commit-graph-view')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('commit-card').first()).toBeVisible();
  await expect(page.getByTestId('show-full-graph-button')).toHaveCount(0);
});
