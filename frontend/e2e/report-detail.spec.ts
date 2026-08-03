import { expect, test } from "@playwright/test";

test("反方来源隐藏内部 ID，ETF 快照展示可审计行情", async ({ page }) => {
  const report = {
    reportId: "report:run-detail", runId: "run-detail", title: "机器人主题研究",
    themeId: "robotics", themeLabel: "智能机器人", status: "WATCH", confidence: "medium",
    lastUpdated: "2026-07-31T00:00:00Z", version: 2, auditPassed: true,
    conclusion: { verdict: "mixed", confidence: "medium", statement: "主题证据与风险信号并存，适合继续核验。", keyEvidenceIds: ["e-1"], limitations: ["资金流未核验"], modelUsed: true },
    executiveSummary: "机器人主题证据仍需持续核验。", investmentThesis: "当前仅形成研究假设。",
    whyNow: ["公开技术活动增加"], keyDrivers: ["自动化需求"], mainRisks: ["商业化延迟"],
    bullCase: [{
      id: "bull-1", evidenceId: "e-1", side: "bull", sourceType: "unknown",
      publisher: "TD Securities", logoUrl: "", claim: "重构 GPU 与 ASIC 的讨论框架",
      evidence: "2025年5月30日，TD Securities 分析师在半导体与 AI 数据中心领域指出，GPU 与 ASIC 的取舍更适合用自研与外购框架分析。",
      limitation: "单一机构观点需要独立来源复核。", confidence: .9, url: "https://example.com/article",
    }],
    bearCase: {
      citations: [{
        id: "bear-1", evidenceId: "internal-secret-id", side: "bear", sourceType: "academic",
        publisher: "Example Research", logoUrl: "", claim: "商业化可能延迟", evidence: "成本仍然较高。",
        limitation: "需要独立来源复核。", confidence: .7, url: "https://example.com/counter",
      }],
      counterArguments: [{ claim: "商业化可能延迟", reason: "成本仍然较高。", sourceUrl: "https://example.com/counter", publisher: "Example Research" }],
      risks: ["量产节奏不确定"], missingData: ["官方订单数据"],
    },
    etfLandscape: {
      existingEtfs: ["BOTZ · Global X · 机器人"], overlap: "unknown", whiteSpace: "unknown", dataStatus: "partial",
      marketSnapshotStatus: "available", marketAsOf: "2026-07-30T00:00:00Z", limitations: [],
      products: [{
        ticker: "BOTZ", issuer: "Global X", category: "机器人", official_url: "https://issuer.example/BOTZ",
        source_url: "https://finance.yahoo.com/quote/BOTZ/", data_status: "available", as_of: "2026-07-30T00:00:00Z",
        last_close: 42.5, currency: "USD", returns: { "1w": .02, "1m": .05, "3m": .08 },
        annualized_volatility_3m: .22, max_drawdown_3m: -.09, average_dollar_volume_20d: 12_500_000,
        activity_trend: "higher", price_trend: "up",
      }],
    },
    companyMap: { purePlays: [], enablers: [], beneficiaries: [], dataStatus: "unknown" },
    decision: { currentStatus: "WATCH", rationale: "继续观察。", nextActions: ["补充官方数据"] },
  };
  await page.route("**/api/reports/report%3Arun-detail/detail", (route) => route.fulfill({ json: report }));
  await page.route("**/api/reports/report%3Arun-detail/versions", (route) => route.fulfill({ json: { versions: [{ version: 2, content_hash: "abcdef012345", created_at: "2026-07-31" }], claims: [] } }));

  await page.goto("/reports/report%3Arun-detail");

  const conclusion = page.getByRole("heading", { name: "研究结论" });
  const summary = page.getByRole("heading", { name: "执行摘要" });
  await expect(conclusion).toBeVisible();
  await expect(page.getByText("结论混合")).toBeVisible();
  expect((await conclusion.boundingBox())!.y).toBeLessThan((await summary.boundingBox())!.y);
  await expect(page.getByRole("heading", { name: "反方论证与证据缺口" })).toBeVisible();
  await expect(page.getByText(/2025年5月30日，TD Securities 分析师/)).toBeVisible();
  await expect(page.getByText(/已按主题相关性和来源质量完成确定性筛选/)).toHaveCount(0);
  await expect(page.getByText("商业化可能延迟").first()).toBeVisible();
  await expect(page.getByText("internal-secret-id")).toHaveCount(0);
  await expect(page.getByText("https://example.com/counter", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /打开 Example Research 来源/ }).first()).toBeVisible();
  await expect(page.getByText("BOTZ", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("+5.0%")).toBeVisible();
  await expect(page.getByText("不代表买入人数或资金净流入", { exact: true })).toBeVisible();
});
