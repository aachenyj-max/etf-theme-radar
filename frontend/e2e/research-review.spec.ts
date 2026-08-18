import { expect, test, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/session", route => route.fulfill({ json: { enabled: false, authenticated: true, username: "local" } }));
  await page.route("**/api/conversations", route => route.fulfill({ status: 404, json: { detail: "not available in legacy fixture" } }));
});

const request = { topic:"机器人",objective:"analyze_etf_landscape_and_track_industry_momentum",sources:[],timeRange:"multi_horizon",outputType:"theme_report" };
function run(status:string,stage:string,progress:number){return {run_id:"run-e2e",status,stage,progress,created_at:new Date().toISOString(),updated_at:new Date().toISOString(),request,result:{theme_definition:{theme_id:"robotics",name:"机器人",description:"机器人产业采用研究",aliases:["robotics"],research_questions:["采用？","反方？","覆盖？"],model_used:false}},approvals:[],agent_runs:[],tool_calls:[],steps:[]};}
async function mockResearchApi(page:Page){
  let status="awaiting_theme_review"; let stage="theme_review"; let progress=12;
  await page.route("**/api/dashboard",route=>route.fulfill({json:{runs:[]}}));
  await page.route("**/api/capabilities",route=>route.fulfill({json:{connectors:[],llm:{configured:false},playwright_mcp:{configured:false},output_types:{theme_report:true,quick_scan:true,etf_opportunity_analysis:true}}}));
  await page.route("**/api/themes?**",route=>route.fulfill({json:{themes:[{id:"theme_robotics",slug:"robotics",title:"智能机器人",englishTitle:"Intelligent Robotics",description:"机器人产业研究",sector:"industrials",sources:[],stage:"validating",trend:"stable",metrics:{themeScore:74,researchMomentum:76,commercialAdoption:68,etfWhiteSpace:58,companies:31},latestCatalyst:"产业信号",latestEvidence:"跨来源证据",mainRisk:"商业化节奏",evidenceCount:108,sourceTypeCount:6,updatedAt:"刚刚",currentConclusion:"产业动量仍需持续核验",reportVersion:2,lastVerifiedAt:"2026-08-05"}],candidates:[],totalBeforeFilters:1,generatedAt:new Date().toISOString(),coverageNote:"系统自动调度"}}));
  await page.route("**/api/research-runs",async route=>{
    if(route.request().method()==="GET")return route.fulfill({json:{runs:[],total:0,limit:50,offset:0,has_more:false}});
    return route.fulfill({status:202,json:{run_id:"run-e2e"}});
  });
  await page.route("**/api/research-runs/run-e2e/stream",async route=>{if(status==="queued"){status="awaiting_report_review";stage="report_review";progress=92;}const body=`event: run_snapshot\ndata: ${JSON.stringify(run(status,stage,progress))}\n\n`;await route.fulfill({contentType:"text/event-stream",body});});
  await page.route("**/api/research-runs/run-e2e/theme-review",async route=>{status="queued";stage="collecting";progress=15;await route.fulfill({json:run(status,stage,progress)});});
  await page.route("**/api/research-runs/run-e2e/report-review",async route=>{const payload=route.request().postDataJSON();status=payload.decision==="return"?"returned":"completed";stage=status==="returned"?"report_review":"completed";progress=status==="completed"?100:92;await route.fulfill({json:run(status,stage,progress)});});
  await page.route("**/api/research-runs/run-e2e/rerun",async route=>{status="queued";stage="collecting";progress=15;await route.fulfill({json:{run_id:"run-e2e",status:"queued"}});});
  await page.route("**/api/research-runs/run-e2e",async route=>route.fulfill({json:run(status,stage,progress)}));
}

test("主题确认、报告退回、重跑与通过",async({page})=>{
  await mockResearchApi(page); await page.goto("/research");
  await expect(page.locator("select")).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"分析 ETF 格局、跟踪产业动量"})).toBeVisible();
  await expect(page.getByRole("button",{name:/继续研究已确认主题/})).toBeVisible();
  await expect(page.getByText("选择情报来源")).toHaveCount(0);
  await page.getByPlaceholder("例如：先进封装与 Chiplet").fill("机器人");
  await page.getByRole("button",{name:/确认研究边界/}).click();
  await expect(page.getByRole("button",{name:"确认并深入研究"})).toBeVisible();
  await page.getByRole("button",{name:"确认并深入研究"}).click();
  await expect(page.getByText("报告已生成，等待你的复核")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button",{name:"要求补充研究"}).click();
  await page.getByRole("textbox",{name:"复核备注"}).fill("缺少订单兑现证据，会影响对产业景气持续性的判断");
  await page.getByRole("button",{name:"提交并重新排队"}).click();
  await expect(page.getByText("报告已生成，等待你的复核")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button",{name:"确认并发布"}).click();
  await expect(page.getByRole("link",{name:/查看主题报告/})).toBeVisible();
});

test("过期主题复核状态显示页内错误且不触发运行时异常",async({page})=>{
  const pageErrors:string[]=[];
  page.on("pageerror",error=>pageErrors.push(error.message));
  await mockResearchApi(page);
  await page.route("**/api/research-runs/run-e2e/theme-review",route=>route.fulfill({status:409,json:{detail:"当前不在主题复核阶段"}}));
  await page.goto("/research");
  await page.getByPlaceholder("例如：先进封装与 Chiplet").fill("机器人");
  await page.getByRole("button",{name:/确认研究边界/}).click();
  await page.getByRole("button",{name:"确认并深入研究"}).click();
  await expect(page.getByText("当前不在主题复核阶段",{exact:true})).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("旧版任务列表接口给出明确重启提示",async({page})=>{
  await page.route("**/api/research-runs?**",route=>route.fulfill({status:405,headers:{Allow:"POST"},json:{detail:"Method Not Allowed"}}));
  await page.route("**/api/capabilities",route=>route.fulfill({json:{connectors:[],output_types:{theme_report:true,quick_scan:true,etf_opportunity_analysis:true}}}));
  await page.goto("/research");
  await expect(page.getByText("当前运行的是旧版 API，请关闭旧服务并重新启动 ETF 主题雷达。")).toBeVisible();
});

test("任务详情瞬时断线会重试且不触发运行时异常",async({page})=>{
  let detailRequests=0;
  const pageErrors:string[]=[];
  page.on("pageerror",error=>pageErrors.push(error.message));
  await page.route("**/api/capabilities",route=>route.fulfill({json:{connectors:[],output_types:{theme_report:true,quick_scan:true,etf_opportunity_analysis:true}}}));
  await page.route("**/api/research-runs?**",route=>route.fulfill({json:{runs:[{run_id:"run-e2e",topic:"机器人",status:"completed",stage:"completed",progress:100,created_at:new Date().toISOString(),updated_at:new Date().toISOString(),needs_attention:false,output_type:"theme_report"}],total:1,limit:50,offset:0,has_more:false}}));
  await page.route("**/api/research-runs/run-e2e",async route=>{
    detailRequests+=1;
    if(detailRequests===1)return route.abort("connectionreset");
    return route.fulfill({json:run("completed","completed",100)});
  });
  await page.goto("/research");
  await page.getByRole("button",{name:/机器人/}).click();
  await expect(page.getByText("研究任务已完成")).toBeVisible();
  expect(detailRequests).toBe(2);
  expect(pageErrors).toEqual([]);
});

test("旧报告库路由只显示迁移说明",async({page})=>{
  await page.goto("/reports");
  await expect(page.getByRole("heading",{name:"报告库已迁移"})).toBeVisible();
  await expect(page.getByText("旧报告库不再支持重命名、归档或删除。")).toBeVisible();
  await expect(page.getByRole("link",{name:"前往主题雷达"})).toBeVisible();
});

test("研究台以对话流显示默认状态线与按需抽屉",async({page})=>{
  const conversation={conversation_id:"conversation-a",user_id:"local",selected_theme_id:"robotics",title:"机器人产业链",status:"active",created_at:"2026-08-17T00:00:00+00:00",updated_at:"2026-08-17T00:01:00+00:00"};
  await page.route("**/api/conversations",route=>route.fulfill({json:{conversations:[conversation,{...conversation,conversation_id:"conversation-b",title:"机器人 ETF 格局"}]}}));
  await page.route("**/api/conversations/conversation-a/messages",route=>route.fulfill({json:{conversation_id:"conversation-a",messages:[{message_id:"message-a",conversation_id:"conversation-a",message_seq:1,role:"user",content:"产业链的反方证据是什么？",idempotency_key:"turn-a",goal_id:"goal-a",created_at:"2026-08-17T00:00:00+00:00"}]}}));
  await page.route("**/api/conversations/conversation-a/events?**",route=>route.fulfill({json:{conversation_id:"conversation-a",last_event_id:2,events:[{event_id:1,goal_id:"goal-a",kind:"action_status",created_at:"2026-08-17T00:00:01+00:00",action:"正在验证引用",status:"running",elapsed_ms:840,source_count:2,tool_name:"",tool_status:"",safe_summary:"",raw_added:0,relevant_added:0,answer_chunk:""},{event_id:2,goal_id:"goal-a",kind:"answer_chunk",created_at:"2026-08-17T00:00:02+00:00",action:"",status:"",elapsed_ms:0,source_count:0,tool_name:"",tool_status:"",safe_summary:"",raw_added:0,relevant_added:0,answer_chunk:"现有证据仍不足以确认产业趋势。"}]}}));
  await page.route("**/api/conversations/conversation-a/links",route=>route.fulfill({json:{conversation_id:"conversation-a",linked_conversation_ids:[],summaries:[]}}));
  await page.goto("/research");

  await expect(page.getByRole("complementary",{name:"研究对话"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"机器人产业链"})).toBeVisible();
  await expect(page.getByText("正在验证引用")).toBeVisible();
  await expect(page.getByText("来源 2")).toBeVisible();
  await expect(page.getByText("现有证据仍不足以确认产业趋势。")).toBeVisible();
  await page.getByRole("button",{name:"打开研究抽屉"}).click();
  await expect(page.getByRole("complementary",{name:"研究抽屉"})).toBeVisible();
  await expect(page.getByText("没有显式关联其他对话")).toBeVisible();
});
