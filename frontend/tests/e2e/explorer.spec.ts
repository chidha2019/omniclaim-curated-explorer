import { test, expect } from "@playwright/test";
test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore demo workspace →" }).click();
  await expect(
    page.getByRole("heading", { name: "Customer explorer" }),
  ).toBeVisible();
});
test("React to FastAPI browsing, pagination and currency grain", async ({
  page,
}) => {
  await expect(page.getByRole("table")).toBeVisible();
  await page.getByRole("button", { name: "Next →" }).click();
  await expect(page.getByText("Page 2", { exact: false })).toBeVisible();
  await page.getByLabel("Currency", { exact: true }).selectOption("EUR");
  await expect(page.getByText("EUR 800.00", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: /View details for/ })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
test("policy metrics, claims and health views", async ({ page }) => {
  await page
    .getByRole("button", { name: "Policy overview", exact: false })
    .click();
  await expect(
    page.getByRole("columnheader", { name: "Active policies", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Claims explorer", exact: false })
    .click();
  await expect(
    page.getByRole("cell", { name: "UNDER REVIEW", exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Data health", exact: false }).click();
  await expect(page.getByText("Up to date", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Passed", exact: true }),
  ).toHaveCount(3);
});
test("empty results and filter reset", async ({ page }) => {
  await page
    .getByRole("textbox", { name: "Search records" })
    .fill("no-such-customer");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("No matching records")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(25);
});
test("publication changed recovery", async ({ page }) => {
  await page.route("**/api/v1/customers?**", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        code: "publication_changed",
        message: "A new release is available.",
      }),
    }),
  );
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.unroute("**/api/v1/customers?**");
  await page.getByRole("button", { name: "Refresh view" }).click();
  await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(25);
});
test("anonymous requests and writes are rejected", async ({ request }) => {
  expect((await request.get("/api/v1/customers")).status()).toBe(401);
  expect(
    (
      await request.post("/api/v1/claims", {
        headers: { Authorization: "Bearer local-demo" },
        data: {},
      })
    ).status(),
  ).toBe(405);
});
