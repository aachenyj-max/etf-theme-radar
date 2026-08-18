import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/session", route => route.fulfill({ json: { enabled: false, authenticated: true, username: "local" } }));
});

test("知识库默认私有，并在共享前展示确认预览", async ({ page }) => {
  let confirmCalls = 0;
  await page.route("**/api/knowledge", route => route.fulfill({ json: { items: [{
    knowledge_item_id: "knowledge-1", title: "机器人供应商会议", kind: "meeting_material",
    theme_id: "robotics", current_version: 2, updated_at: "2026-08-18T00:00:00+00:00",
    mime_type: "text/plain", original_filename: "meeting.txt", visibility: "private",
  }] } }));
  await page.route("**/api/knowledge/knowledge-1/operations/preview", route => route.fulfill({ status: 201, json: {
    operation_id: "operation-1", operation_type: "share", target_id: "knowledge-1", target_version: 2,
    preview: { changes: { subject_type: "user", subject_id: "user-b" } }, confirmation_token: "confirm-1",
    status: "pending_confirmation",
  } }));
  await page.route("**/api/knowledge/operations/operation-1/confirm", route => {
    confirmCalls += 1;
    return route.fulfill({ json: { operation_id: "operation-1", status: "completed" } });
  });

  await page.goto("/knowledge");
  await expect(page.getByRole("heading", { name: "个人知识库" })).toBeVisible();
  await expect(page.getByRole("article").getByText("仅自己可见")).toBeVisible();
  await page.getByLabel("共享对象").fill("user-b");
  await page.getByRole("button", { name: "共享 机器人供应商会议" }).click();
  await expect(page.getByRole("dialog", { name: "确认共享" })).toBeVisible();
  expect(confirmCalls).toBe(0);
  await page.getByRole("button", { name: "确认共享" }).click();
  await expect(page.getByText("共享已更新")).toBeVisible();
  expect(confirmCalls).toBe(1);
});

test("移动资料也必须先展示预览，确认后才发送写操作", async ({ page }) => {
  let confirmCalls = 0;
  await page.route("**/api/knowledge", route => route.fulfill({ json: { items: [{
    knowledge_item_id: "knowledge-2", title: "硬件供应链材料", kind: "upload",
    theme_id: "robotics", current_version: 1, updated_at: "2026-08-18T00:00:00+00:00",
    mime_type: "text/plain", original_filename: "supply-chain.txt", visibility: "private",
  }] } }));
  await page.route("**/api/knowledge/knowledge-2/operations/preview", route => route.fulfill({ status: 201, json: {
    operation_id: "operation-move", operation_type: "move", target_id: "knowledge-2", target_version: 1,
    preview: { changes: { folder_id: "robotics-notes" } }, confirmation_token: "confirm-move",
    status: "pending_confirmation",
  } }));
  await page.route("**/api/knowledge/operations/operation-move/confirm", route => {
    confirmCalls += 1;
    return route.fulfill({ json: { operation_id: "operation-move", status: "completed" } });
  });

  await page.goto("/knowledge");
  await page.getByLabel("移动目标文件夹").fill("robotics-notes");
  await page.getByRole("button", { name: "移动 硬件供应链材料" }).click();
  await expect(page.getByRole("dialog", { name: "确认移动" })).toBeVisible();
  expect(confirmCalls).toBe(0);
  await page.getByRole("button", { name: "确认移动" }).click();
  await expect(page.getByText("移动已完成")).toBeVisible();
  expect(confirmCalls).toBe(1);
});
