import { ReportDetailWorkspace } from "@/components/report-detail-workspace";

export default async function ReportDetailPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = await params;
  let decodedReportId = reportId;
  try { decodedReportId = decodeURIComponent(reportId); } catch { /* Preserve malformed input for the normal 404 state. */ }
  return <ReportDetailWorkspace reportId={decodedReportId} />;
}
