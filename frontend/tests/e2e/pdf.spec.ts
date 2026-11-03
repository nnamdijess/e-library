import { test, expect } from "@playwright/test";

test("PDF page and normalized position survive reopening", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill("testowner");
  await page.getByLabel("Password", { exact: true }).fill("local-reader-test-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: /Read book\s*:\s*A PDF fixture/ }).click();
  const next = page.getByRole("button", { name: "Next", exact: true });
  const previous = page.getByRole("button", { name: "Previous", exact: true });
  await expect.poll(async () => await next.isEnabled() || await previous.isEnabled(), { timeout: 45000 }).toBe(true);
  if (await previous.isEnabled()) await previous.click();
  await expect(next).toBeEnabled();
  await expect(page.getByRole("img", { name: "PDF page 1" })).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByRole("img", { name: "PDF page 2" })).toBeVisible();
  await expect(page.locator(".reader-save-note")).toHaveText("Synced");
  await page.setViewportSize({ width: 844, height: 390 });
  await page.getByLabel("Zoom").selectOption("fit-page");
  await expect.poll(() => page.locator(".pdf-viewport").evaluate((host) => {
    const canvas = host.querySelector("canvas")!.getBoundingClientRect();
    return canvas.height <= host.clientHeight - 24 && canvas.width <= host.clientWidth - 24;
  })).toBe(true);
  await expect(page.locator(".pdf-viewport")).toHaveAttribute("aria-busy", "false");
  await page.screenshot({ path: testInfo.outputPath("pdf-fit-page.png") });
  await page.getByLabel("Zoom").selectOption("300");
  // This generated fixture has a 160 x 240 point MediaBox.
  await expect(page.locator(".pdf-viewport canvas")).toHaveCSS("height", "720px");
  await expect(page.locator(".pdf-viewport")).toHaveAttribute("aria-busy", "false");
  await expect(page.getByRole("button", { name: "Previous", exact: true })).toBeEnabled();
  await page.locator(".pdf-viewport").evaluate((host) => { host.scrollTop = 150; });
  await expect.poll(() => page.evaluate(async () => (await (await fetch(`/api/v1/books/${location.pathname.split('/').pop()}/progress`)).json()).location.offset)).toBeGreaterThan(0);
  await expect(page.locator(".reader-save-note")).toHaveText("Synced");
  const position = await page.evaluate(async () => (await fetch(`/api/v1/books/${location.pathname.split('/').pop()}/progress`)).json());
  expect(position.location.page).toBe(2);
  expect(position.location.offset).toBeGreaterThan(0);
  await page.reload();
  await expect(page.getByRole("button", { name: "Previous", exact: true })).toBeEnabled({ timeout: 45000 });
  await expect(page.getByRole("img", { name: "PDF page 2" })).toBeVisible();
  await expect.poll(() => page.locator(".pdf-viewport").evaluate((host) => host.scrollTop)).toBeGreaterThan(0);
  expect(errors).toEqual([]);
});
