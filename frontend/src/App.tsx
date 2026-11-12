import { Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ragApi } from "./api/ragApi";
import { DocumentPanel } from "./components/DocumentPanel";
import { WorkflowCard } from "./components/WorkflowCard";
import type { ResumePayload, Workflow, WorkflowMode } from "./types/rag";

const POLL_INTERVAL_MS = 1000;

function App() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<WorkflowMode>("advanced");
  const [requireApproval, setRequireApproval] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const upsert = (workflow: Workflow) =>
    setWorkflows((prev) => {
      const exists = prev.some((w) => w.thread_id === workflow.thread_id);
      return exists ? prev.map((w) => (w.thread_id === workflow.thread_id ? workflow : w)) : [...prev, workflow];
    });

  // 실행 중인 workflow만 주기적으로 조회해 현재 node와 상태를 갱신한다.
  const runningIds = workflows.filter((w) => w.status === "running").map((w) => w.thread_id).join(",");
  useEffect(() => {
    if (!runningIds) return;
    const timer = window.setInterval(() => {
      runningIds.split(",").forEach((id) => {
        ragApi.getWorkflow(id).then(upsert).catch((err: Error) => setError(err.message));
      });
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [runningIds]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [workflows.length]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;
    setError(null);
    try {
      upsert(await ragApi.startChat({ question: trimmed, mode, require_approval: requireApproval }));
      setQuestion("");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleResume(threadId: string, payload: ResumePayload) {
    upsert(await ragApi.resumeWorkflow(threadId, payload));
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-[#212121] text-zinc-100">
      <DocumentPanel />
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
          {workflows.length === 0 && (
            <p className="mt-24 text-center text-zinc-500">문서를 업로드한 뒤 질문해 보세요.</p>
          )}
          {workflows.map((workflow) => (
            <WorkflowCard
              key={workflow.thread_id}
              workflow={workflow}
              onResume={(payload) => handleResume(workflow.thread_id, payload)}
            />
          ))}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={handleSubmit} className="border-t border-zinc-800 p-4">
          <div className="mb-2 flex flex-wrap items-center gap-4 text-xs text-zinc-400">
            <label className="flex items-center gap-1">
              Mode
              <select
                value={mode}
                onChange={(event) => setMode(event.target.value as WorkflowMode)}
                className="rounded border border-zinc-700 bg-zinc-900 px-1 py-0.5"
              >
                <option value="basic">basic (retrieve → generate)</option>
                <option value="advanced">advanced (check · validate · retry)</option>
              </select>
            </label>
            <label className={`flex items-center gap-1 ${mode === "basic" ? "opacity-40" : ""}`}>
              <input
                type="checkbox"
                checked={requireApproval}
                disabled={mode === "basic"}
                onChange={(event) => setRequireApproval(event.target.checked)}
              />
              Require human approval
            </label>
          </div>
          <div className="flex gap-2">
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask about your documents..."
              maxLength={4000}
              className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 outline-none focus:border-zinc-500"
            />
            <button
              type="submit"
              aria-label="Send"
              disabled={!question.trim()}
              className="rounded-lg bg-zinc-100 px-3 text-zinc-900 disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        </form>
      </main>
    </div>
  );
}

export default App;
