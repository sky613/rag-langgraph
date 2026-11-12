// 백엔드 schemas.py의 응답 형태와 1:1로 대응한다.
export type WorkflowMode = "basic" | "advanced";

export type WorkflowStatus =
  | "running"
  | "awaiting_approval"
  | "completed"
  | "insufficient_context"
  | "rejected"
  | "failed"
  | "interrupted";

export type DocumentItem = {
  id: string;
  filename: string;
  size_bytes: number;
  chunk_count: number;
  created_at: string;
};

export type SourceDocument = {
  id: string;
  document_id: string;
  filename: string;
  chunk_index: number;
  page: number | null;
  content: string;
  score: number;
};

export type WorkflowMetrics = {
  node_timings: { node: string; duration_ms: number }[];
  total_duration_ms: number;
  retrieval_latency_ms: number;
  llm_latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
};

export type Workflow = {
  thread_id: string;
  mode: WorkflowMode;
  question: string;
  require_approval: boolean;
  status: WorkflowStatus;
  current_node: string | null;
  next_nodes: string[];
  failure_category: string | null;
  error: string | null;
  answer: string | null;
  source_documents: SourceDocument[];
  retry_count: number;
  validation_result: { valid: boolean; reason: string | null; cited: number[] } | null;
  approval_status: string | null;
  pending_approval: {
    question: string;
    draft_answer: string | null;
    source_documents: SourceDocument[];
  } | null;
  metrics: WorkflowMetrics;
  created_at: string;
  updated_at: string;
};

export type ChatPayload = {
  question: string;
  mode: WorkflowMode;
  require_approval: boolean;
};

export type ResumePayload = {
  approved?: boolean;
  comment?: string;
};
