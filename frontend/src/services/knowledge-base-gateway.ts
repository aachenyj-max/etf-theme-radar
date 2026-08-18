import type { KnowledgeItem, KnowledgeOperation } from "@/lib/knowledge-base";

const apiBase = process.env.NEXT_PUBLIC_REPORTS_API_BASE_URL?.replace(/\/$/, "") ?? "";

async function responseJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(response.status === 404 ? "资料不存在或无权访问。" : `知识库接口返回 ${response.status}`);
  return await response.json() as T;
}

export const knowledgeBaseGateway = {
  async list(): Promise<KnowledgeItem[]> {
    return (await responseJson<{ items: KnowledgeItem[] }>(await fetch(`${apiBase}/api/knowledge`, { headers: { Accept: "application/json" } }))).items;
  },
  async preview(itemId: string, operationType: KnowledgeOperation["operation_type"], payload: Record<string, string>): Promise<KnowledgeOperation> {
    return responseJson(await fetch(`${apiBase}/api/knowledge/${encodeURIComponent(itemId)}/operations/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation_type: operationType, payload, idempotency_key: `${operationType}:${itemId}:${crypto.randomUUID()}` }),
    }));
  },
  async confirm(operation: KnowledgeOperation): Promise<KnowledgeOperation> {
    return responseJson(await fetch(`${apiBase}/api/knowledge/operations/${encodeURIComponent(operation.operation_id)}/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation_token: operation.confirmation_token }),
    }));
  },
};
