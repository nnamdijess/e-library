import { test, expect, type Page } from "@playwright/test";

function simulateSaveOutage() {
  // Browsers can dispatch page-exit keepalive requests outside Playwright's
  // routing hook. Intercept at fetch so failed saves stay failed on refresh.
  const fetch = window.fetch.bind(window);
  window.fetch = (input, options) => {
    if (localStorage.getItem("test-progress-outage") && options?.method === "PUT" && String(input).endsWith("/progress")) return Promise.resolve(new Response('{"detail":{"message":"Test server unavailable"}}', { status: 503 }));
    return fetch(input, options);
  };
}

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill("testowner");
  await page.getByLabel("Password", { exact: true }).fill("local-reader-test-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: /Read book\s*:\s*Reader fixture/ }).click();
  await expect(page.getByRole("button", { name: "Contents", exact: true })).toBeEnabled({ timeout: 45000 });
}

test("confirmed CFI survives refresh, offline retry, and a second device conflict", async ({ page, browser }, testInfo) => {
  await page.addInitScript(simulateSaveOutage);
  await signIn(page);
  const bookUrl = page.url();
  const status = page.locator(".reader-save-note");
  await page.getByRole("button", { name: "Contents", exact: true }).click();
  await page.getByRole("complementary").getByRole("button", { name: "First chapter", exact: true }).click();
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(status).toHaveText("Synced");
  const before = await page.locator(".reader-footer [role=status]").innerText();
  await page.reload();
  await expect(page.locator(".reader-footer [role=status]")).toHaveText(before, { timeout: 45000 });
  // Abort only progress writes: book and login remain online. Do not equate
  // navigator.onLine with proof the server is reachable.
  await page.evaluate(() => localStorage.setItem("test-progress-outage", "1"));
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(status).toContainText("saved locally");
  const queued = await page.evaluate(() => Object.entries(localStorage).filter(([key]) => key.startsWith("ebook-pending-v1:")));
  expect(queued).toHaveLength(1);
  await page.reload();
  await expect(page.getByRole("button", { name: "Contents", exact: true })).toBeEnabled();
  await expect(status).toContainText("saved locally", { timeout: 45000 });
  await page.evaluate(() => localStorage.removeItem("test-progress-outage"));
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(status).toHaveText("Synced");
  // Seed authentication only into an independent browser context. Backend
  // tests separately cover two independently issued owner sessions. Reusing
  // the test login avoids hitting the real login rate limit across projects.
  const authentication = await page.context().storageState();
  const second = await browser.newContext({ viewport: testInfo.project.use.viewport, storageState: { cookies: authentication.cookies, origins: [] } });
  try {
    const other = await second.newPage();
    await other.goto(bookUrl);
    await expect(other.getByRole("button", { name: "Contents", exact: true })).toBeEnabled({ timeout: 45000 });
    await expect(other.locator(".reader-footer [role=status]")).toHaveText(await page.locator(".reader-footer [role=status]").innerText());
    await other.getByRole("button", { name: "Next", exact: true }).click();
    await expect(other.locator(".reader-save-note")).toHaveText("Synced");
    // First device still has its old base revision. It must not overwrite.
    await page.getByRole("button", { name: "Previous", exact: true }).click();
    await expect(page.getByRole("button", { name: "Load saved position", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Load saved position", exact: true }).click();
    await expect(status).toHaveText("Synced");
    await expect(page.locator(".reader-footer [role=status]")).toHaveText(await other.locator(".reader-footer [role=status]").innerText());
  } finally { await second.close(); }
  expect(page.url()).toBe(bookUrl);
});
