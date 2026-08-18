export type KnowledgeItem = {
  knowledge_item_id: string;
  title: string;
  kind: string;
  theme_id: string;
  current_version: number;
  updated_at: string;
  mime_type: string;
  original_filename: string;
  visibility: "private" | "shared";
};

export type KnowledgeOperation = {
  operation_id: string;
  operation_type: "share" | "revoke_share" | "move" | "delete" | "restore";
  target_id: string;
  target_version: number;
  preview: { changes: Record<string, string> };
  confirmation_token: string;
  status: "pending_confirmation" | "completed";
};
