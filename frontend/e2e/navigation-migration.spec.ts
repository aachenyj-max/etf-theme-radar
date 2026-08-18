import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/session", (route) => route.fulfill({
    json: { enabled: false, authenticated: true, username: "local" },
  }));
  await page.route("**/api/capabilities", (route) => route.fulfill({
    json: { connectors: [] },
  }));
});

test("主导航不再提供证据浏览器或 ETF 产品工作室入口", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("navigation", { name: "主导航" }).getByText("证据浏览器")).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "主导航" }).getByText("ETF 产品工作室")).toHaveCount(0);
});

test("旧证据浏览器路由不再提供独立页面", async ({ page }) => {
  await page.goto("/evidence");

  await expect(page.getByText("404")).toBeVisible();
});

test("旧 ETF 产品工作室 URL 只显示迁移说明", async ({ page }) => {
  await page.goto("/product-studio");

  await expect(page.getByRole("heading", { name: "ETF 产品工作室已迁移" })).toBeVisible();
  await expect(page.getByText("不会创建产品任务或发行建议")).toBeVisible();
});

test("旧报告库 URL 不再承担个人资料管理", async ({ page }) => {
  await page.goto("/reports");

  await expect(page.getByRole("heading", { name: "报告库已迁移" })).toBeVisible();
  await expect(page.getByText("个人保存资料已迁入个人知识库")).toBeVisible();
});
