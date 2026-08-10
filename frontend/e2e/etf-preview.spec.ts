import { expect, test } from "@playwright/test";

const baseItem = {
  code: "050025", name: "博时标普500ETF联接A", c_code: "006075", operating_fee: 0.6,
  scale_billion: 112.34, scale_date: "2026-06-30", return_2025: 18.26, rolling_1y: 22.4,
  yesterday_return: -0.31, tracking_error: 1.17, tracking_error_date: "2026-08-03",
  daily_limit_yuan: 1000, purchase_status: "开放申购", source_url: "https://fund.eastmoney.com/050025.html",
};

test("ETF 预览支持三类切换、搜索且桌面端不横向溢出", async ({ page }) => {
  await page.route("**/api/etf-preview/refresh", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ poll_url: "/api/sync-runs/preview" }) }));
  await page.route("**/api/sync-runs/preview", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "completed" }) }));
  await page.route("**/api/etf-preview?**", async (route) => {
    const url = new URL(route.request().url());
    const category = url.searchParams.get("category") ?? "sp500";
    const query = url.searchParams.get("q") ?? "";
    const item = category === "exchange" ? { ...baseItem, code: "513500", name: "标普500ETF博时", tracking_index: "标普500指数", premium_rate: 2.35, average_turnover_billion_20d: 7.62 } : category === "active" ? { ...baseItem, code: "000043", name: "嘉实美国成长股票人民币", c_code: "" } : baseItem;
    const items = query && !`${item.code}${item.name}`.includes(query) ? [] : [item];
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ state: "ready", source: "天天基金网", source_homepage: "https://1234567.com.cn/", market_as_of: "2026-08-03", counts: { sp500: 7, exchange: 25, active: 34 }, items, filtered_count: items.length, total: 66 }) });
  });

  await page.goto("/etf-preview");
  await expect(page.getByRole("heading", { name: "ETF 预览" })).toBeVisible();
  await expect(page.getByText("66 只")).toBeVisible();
  await expect(page.getByText("博时标普500ETF联接A")).toBeVisible();
  await page.getByRole("tab", { name: /场内 ETF/ }).click();
  await expect(page.getByText("标普500ETF博时")).toBeVisible();
  await expect(page.getByText("+2.35%")).toBeVisible();
  await page.getByLabel("搜索基金名称或代码").fill("不存在");
  await expect(page.getByText("没有匹配的基金")).toBeVisible();
  await page.getByRole("button", { name: "刷新数据" }).click();
  await expect(page.getByText("行情已更新")).toBeVisible({ timeout: 10_000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});
