import Link from "next/link";
import { Archive, ArrowRight, LibraryBig } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";

export default function ReportLibraryPage() {
  return (
    <div className="mx-auto max-w-[1500px] px-5 py-10 sm:px-8 sm:py-14 xl:px-12">
      <PageHeader
        index="05"
        eyebrow="Migrated route"
        title="报告库已迁移"
        description="个人保存资料已迁入个人知识库。正式主题报告只在主题详情的规范版本链中保留。"
        actions={<Badge className="border-signal/20 bg-signal/[0.08] px-3 py-2 text-signal"><Archive className="mr-1.5 h-3.5 w-3.5" />只读兼容</Badge>}
      />
      <div className="mt-10">
        <EmptyState
          icon={LibraryBig}
          eyebrow="Canonical research assets"
          title="从主题详情查看正式报告"
          description="旧报告库不再支持重命名、归档或删除。个人资料请在个人知识库中管理，正式报告通过主题详情查看冻结版本和引用。"
          action="打开主题雷达"
        />
        <div className="mt-5 flex justify-center">
          <Link href="/theme-radar" className="inline-flex items-center gap-2 text-sm font-semibold text-signal hover:text-ink">前往主题雷达 <ArrowRight className="h-4 w-4" /></Link>
        </div>
      </div>
    </div>
  );
}
