import { expect, test } from "@playwright/test";

test("主题趋势为 unknown 时保持可用", async ({ page }) => {
  await page.route("**/api/themes?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        themes: [{
          id: "theme_robotics",
          slug: "robotics",
          title: "智能机器人",
          englishTitle: "Intelligent Robotics",
          description: "用于验证历史快照不足时的趋势展示。",
          sector: "industrials",
          sources: ["research"],
          stage: "deep_research",
          trend: "unknown",
          metrics: { themeScore: 52, researchMomentum: 50, commercialAdoption: 45, etfWhiteSpace: 0, companies: 2 },
          latestCatalyst: "暂无",
          latestEvidence: "已有一个快照",
          mainRisk: "历史数据不足",
          evidenceCount: 2,
          sourceTypeCount: 1,
          updatedAt: "刚刚"
        }],
        totalBeforeFilters: 1,
        generatedAt: new Date().toISOString(),
        coverageNote: "历史不足时不推断趋势"
      })
    });
  });

  await page.goto("/theme-radar");
  await expect(page.getByText("智能机器人")).toBeVisible();
  await expect(page.getByText("历史不足 · Unknown")).toBeVisible();
});

test("真实能力契约展示 7/8 来源且不渲染空 logo", async ({ page }) => {
  const apiRequests: string[] = [];
  const emptySourceErrors: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/api/")) apiRequests.push(request.url()); });
  page.on("console", (message) => {
    if (message.type() === "error" && /empty string|src attribute/i.test(message.text())) emptySourceErrors.push(message.text());
  });

  await page.goto("/");
  await expect(page).toHaveURL("http://127.0.0.1:3000/");
  await expect(page.getByText("数据覆盖 7/8")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("专利公开发现", { exact: true })).toBeVisible();
  await expect(page.getByText("发行人官方持仓", { exact: true })).toBeVisible();
  await expect(page.getByText("ETF 资讯发现", { exact: true })).toBeVisible();
  await expect(page.locator('img[src=""]')).toHaveCount(0);
  expect(apiRequests.some((url) => url.endsWith("/api/capabilities"))).toBe(true);
  expect(emptySourceErrors).toEqual([]);
});
