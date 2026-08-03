import { Beaker, LockKeyhole } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";

export default function ProductStudioPage() {
  return (
    <div className="mx-auto max-w-[1500px] px-5 py-10 sm:px-8 sm:py-14 xl:px-12">
      <PageHeader index="06" eyebrow="ETF Product Studio" title="从研究主题到产品假设。" description="该模块将在主题证据、可投资性与市场格局通过审核后开放。目前不会生成 ETF 发行建议、模拟组合或交易建议。" actions={<Badge className="border-amber/20 bg-amber/[0.08] px-3 py-2 text-amber"><LockKeyhole className="mr-1.5 h-3.5 w-3.5" />BETA · 尚未开放</Badge>} />
      <div className="mt-10"><EmptyState icon={Beaker} eyebrow="Controlled access" title="产品工作室仍在封闭测试" description="未来可在这里评估主题的产品空白、指数约束与可投资性。所有结论都将继承上游证据审计，不以模型生成内容代替事实。" action="申请 Beta 访问" /></div>
    </div>
  );
}
