import type { ChatPayload, DocumentItem, ResumePayload, Workflow } from "../types/rag";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  // FormData 업로드는 브라우저가 boundary를 포함한 Content-Type을 직접 설정해야 한다.
  const isForm = options.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: isForm ? options.headers : { "Content-Type": "application/json", ...options.headers },
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const data = await response.json();
      message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch {
      // JSON이 아닌 오류 응답도 있으므로 HTTP 상태 기반 기본 메시지를 유지한다.
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const ragApi = {
  listDocuments() {
    return request<DocumentItem[]>("/api/documents");
  },

  uploadDocument(file: File) {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentItem>("/api/documents", { method: "POST", body: form });
  },

  deleteDocument(id: string) {
    return request<void>(`/api/documents/${id}`, { method: "DELETE" });
  },

  startChat(payload: ChatPayload) {
    return request<Workflow>("/api/chat", { method: "POST", body: JSON.stringify(payload) });
  },

  getWorkflow(threadId: string) {
    return request<Workflow>(`/api/workflows/${threadId}`);
  },

  resumeWorkflow(threadId: string, payload: ResumePayload = {}) {
    return request<Workflow>(`/api/workflows/${threadId}/resume`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
