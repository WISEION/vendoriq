import { expect, test } from '@playwright/test';

// Phase 0 smoke: the shell renders, the rail navigates, the workspaces switch and the AZ/EN
// toggle persists. The full journeys (vendor register → submit, officer import → decide →
// match) land in phase 3A, together with the 34 × 2 screenshots.

test('the shell renders the rail and the topbar', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'İcmal', level: 2 })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Vendor reyestri' })).toBeVisible();
});

test('the AZ/EN toggle switches the interface and survives a reload', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('group', { name: 'Language' }).getByRole('button', { name: 'EN' }).click();
  await expect(page.getByRole('heading', { name: 'Overview', level: 2 })).toBeVisible();

  await page.reload();
  await expect(page.getByRole('heading', { name: 'Overview', level: 2 })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
});

test('the theme toggle survives a reload', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('group', { name: 'Theme' }).getByRole('button').first().click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');

  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('the rail reaches every manager screen', async ({ page }) => {
  await page.goto('/');
  for (const [label, heading] of [
    ['Vendor reyestri', 'Vendor reyestri'],
    ['Müraciətlər', 'Müraciətlər və qiymətləndirmə'],
    ['Layihələr və uyğunluq', 'Layihələr və vendor uyğunluğu'],
    ['Bazar kəşfiyyatı', 'Bazar kəşfiyyatı'],
    ['Bal modelləri', 'Bal modelləri'],
    ['Məlumat mənbələri', 'Məlumat mənbələri və inteqrasiyalar'],
  ]) {
    await page.getByRole('link', { name: label, exact: true }).click();
    await expect(page.getByRole('heading', { name: heading, level: 2 })).toBeVisible();
  }
});

test('the workspace switch swaps the rail for the vendor portal', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('group', { name: 'Workspace' }).getByRole('link', { name: 'Vendor portalı' }).click();

  await expect(page.getByRole('heading', { name: 'Müraciət statusu', level: 2 })).toBeVisible();
  for (const label of [
    'Status',
    'Şirkət profili',
    'Müraciət forması',
    'Sənədlər',
    'Bəyannamə və göndəriş',
  ]) {
    await expect(page.getByRole('link', { name: label, exact: true })).toBeVisible();
  }
  await expect(page.getByRole('link', { name: 'Vendor reyestri' })).toHaveCount(0);
});
