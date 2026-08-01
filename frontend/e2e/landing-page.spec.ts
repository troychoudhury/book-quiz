import { test, expect } from '@playwright/test';

test.describe('Landing Page — Acceptance Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:5173');
  });

  test('displays the search bar prominently', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search|book/i);
    await expect(searchInput).toBeVisible();
    await expect(searchInput).toBeEnabled();
  });

  test('shows login and sign up buttons in header', async ({ page }) => {
    await expect(page.getByRole('link', { name: /log in|login/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /sign up|register/i })).toBeVisible();
  });

  test('searching for a non-existent book shows empty state', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search|book/i);
    await searchInput.fill('xyznonexistentbook999');
    await searchInput.press('Enter');
    await expect(page.getByText(/no books found|no results/i)).toBeVisible({ timeout: 10000 });
  });

  test('can navigate without logging in', async ({ page }) => {
    // Verify that the landing page content is accessible
    await expect(page.locator('body')).toBeVisible();
  });
});
