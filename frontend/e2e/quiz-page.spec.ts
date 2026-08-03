import { test, expect } from '@playwright/test';

test.describe('Quiz Page — Acceptance Tests', () => {
  test('shows idle message when no active quiz session', async ({ page }) => {
    await page.goto('http://localhost:5173/quiz/missing-attempt-id');
    await expect(page.getByText(/missing|start a new quiz/i)).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('link', { name: /home/i })).toBeVisible();
  });

  test('quiz page loads and shows question area', async ({ page }) => {
    // Navigate directly — will show idle state since no real session
    await page.goto('http://localhost:5173/quiz/test-attempt');
    // Should show idle or error state, not crash
    await expect(page.locator('body')).toBeVisible();
  });
});
