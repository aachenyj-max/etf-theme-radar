import { Archive, LockKeyhole } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";

export default function ProductStudioPage() {
  return (
    <div className="mx-auto max-w-[1500px] px-5 py-10 sm:px-8 sm:py-14 xl:px-12">
      <PageHeader index="06" eyebrow="Archived route" title="ETF 产品工作室已迁移" description="ETF 产品工作室不再是系统入口。主题研究和 ETF 格局请在主题详情、ETF 预览与研究工作台中查看。" actions={<Badge className="border-amber/20 bg-amber/[0.08] px-3 py-2 text-amber"><LockKeyhole className="mr-1.5 h-3.5 w-3.5" />只读兼容</Badge>} />
      <div className="mt-10"><EmptyState icon={Archive} eyebrow="Read-only compatibility" title="旧产品工作室不再创建任务" description="不会创建产品任务或发行建议；该旧链接仅保留迁移说明。" action="返回主题雷达" /></div>
    </div>
  );
}
