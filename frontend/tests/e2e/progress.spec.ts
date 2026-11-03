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

async function savedPosition(page: Page) {
  return page.evaluate(async () => (await (await fetch(`/api/v1/books/${location.pathname.split('/').pop()}/progress`)).json()));
}

async function visibleParagraphs(page: Page) {
  return page.frameLocator(".epub-host iframe").first().locator("p[id]").evaluateAll((paragraphs) => paragraphs.filter((paragraph) => [...paragraph.getClientRects()].some((rect) => rect.right > 0 && rect.left < innerWidth && rect.bottom > 0 && rect.top < innerHeight)).map((paragraph) => paragraph.id));
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
  const before = await savedPosition(page);
  const passages = await visibleParagraphs(page);
  await page.reload();
  await expect(page.getByRole("button", { name: "Contents", exact: true })).toBeEnabled({ timeout: 45000 });
  // CFI and passage continuity are durable. Page ordinals can move at a column
  // boundary after reflow, especially with large fonts in mobile WebKit.
  expect((await savedPosition(page)).location.cfi).toBe(before.location.cfi);
  await expect(page.locator(".reader-footer [role=status]")).toContainText(`${Math.round(before.percentage * 100)}%`);
  if (passages.length) expect((await visibleParagraphs(page)).some((id) => passages.includes(id))).toBe(true);
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
    const shared = await savedPosition(page);
    await expect(other.locator(".reader-footer [role=status]")).toContainText(`${Math.round(shared.percentage * 100)}%`);
    await other.getByRole("button", { name: "Next", exact: true }).click();
    await expect(other.locator(".reader-save-note")).toHaveText("Synced");
    // First device still has its old base revision. It must not overwrite.
    await page.getByRole("button", { name: "Previous", exact: true }).click();
    await expect(page.getByRole("button", { name: "Load saved position", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Load saved position", exact: true }).click();
    await expect(status).toHaveText("Synced");
    const resolved = await savedPosition(other);
    await expect(page.locator(".reader-footer [role=status]")).toContainText(`${Math.round(resolved.percentage * 100)}%`);
    expect((await savedPosition(page)).location.cfi).toBe(resolved.location.cfi);
  } finally { await second.close(); }
  expect(page.url()).toBe(bookUrl);
});
