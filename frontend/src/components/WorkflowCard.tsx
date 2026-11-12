import { Check, Loader2, Play, X } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";

import type { SourceDocument, Workflow } from "../types/rag";

const STATUS_STYLE: Record<string, string> = {
  running: "bg-blue-500/20 text-blue-300",
  awaiting_approval: "bg-amber-500/20 text-amber-300",
  completed: "bg-emerald-500/20 text-emerald-300",
  insufficient_context: "bg-zinc-500/20 text-zinc-300",
  rejected: "bg-red-500/20 text-red-300",
  failed: "bg-red-500/20 text-red-300",
  interrupted: "bg-orange-500/20 text-orange-300",
};

type Props = {
  workflow: Workflow;
  onResume: (payload: { approved?: boolean; comment?: string }) => Promise<void>;
};

export function WorkflowCard({ workflow, onResume }: Props) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const m = workflow.metrics;
  // 실패/중단 상태라도 남은 node가 있을 때만 checkpoint에서 재개할 수 있다.
  const canResume = ["failed", "interrupted"].includes(workflow.status) && workflow.next_nodes.length > 0;

  async function resume(payload: { approved?: boolean; comment?: string }) {
    setBusy(true);
    setError(null);
    try {
      await onResume(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="ml-auto w-fit max-w-[80%] rounded-2xl bg-zinc-800 px-4 py-2 text-zinc-100">
        {workflow.question}
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 text-sm">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={`rounded px-2 py-0.5 font-medium ${STATUS_STYLE[workflow.status] ?? ""}`}>
            {workflow.status}
          </span>
          <span className="text-zinc-500">mode: {workflow.mode}</span>
          {workflow.current_node && (
            <span className="flex items-center gap-1 text-blue-300">
              {workflow.status === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
              node: {workflow.current_node}
            </span>
          )}
          {workflow.mode === "advanced" && <span className="text-zinc-500">retries: {workflow.retry_count}</span>}
          {workflow.failure_category && <span className="text-red-300">failure: {workflow.failure_category}</span>}
          <span className="ml-auto font-mono text-zinc-600">{workflow.thread_id.slice(0, 8)}</span>
        </div>

        {workflow.validation_result && !workflow.validation_result.valid && (
          <p className="mt-2 text-xs text-amber-300">last validation: {workflow.validation_result.reason}</p>
        )}
        {workflow.error && <p className="mt-2 text-xs text-red-400">{workflow.error}</p>}

        {workflow.answer && (
          <div className="mt-3 space-y-2 text-zinc-100">
            <ReactMarkdown>{workflow.answer}</ReactMarkdown>
          </div>
        )}
        <Citations sources={workflow.source_documents} />

        {workflow.status === "awaiting_approval" && workflow.pending_approval && (
          <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
            <p className="mb-2 text-xs font-semibold text-amber-300">Draft answer — approval required</p>
            <div className="whitespace-pre-wrap text-zinc-200">{workflow.pending_approval.draft_answer}</div>
            <Citations sources={workflow.pending_approval.source_documents} />
            <input
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Comment (optional)"
              className="mt-3 w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs outline-none"
            />
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void resume({ approved: true, comment: comment || undefined })}
                className="flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1 text-xs text-white disabled:opacity-50"
              >
                <Check className="h-3 w-3" /> Approve
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void resume({ approved: false, comment: comment || undefined })}
                className="flex items-center gap-1 rounded-md bg-red-600 px-3 py-1 text-xs text-white disabled:opacity-50"
              >
                <X className="h-3 w-3" /> Reject
              </button>
            </div>
          </div>
        )}

        {canResume && (
          <button
            type="button"
            disabled={busy}
            onClick={() => void resume({})}
            className="mt-3 flex items-center gap-1 rounded-md bg-orange-600 px-3 py-1 text-xs text-white disabled:opacity-50"
          >
            <Play className="h-3 w-3" /> Resume from checkpoint ({workflow.next_nodes.join(", ")})
          </button>
        )}
        {error && <p className="mt-2 text-xs text-red-400">{error}</p>}

        <details className="mt-3 text-xs text-zinc-500">
          <summary className="cursor-pointer">Metrics</summary>
          <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
            <span>total: {m.total_duration_ms} ms</span>
            <span>retrieval: {m.retrieval_latency_ms} ms</span>
            <span>llm: {m.llm_latency_ms} ms</span>
            <span>input tokens: {m.input_tokens}</span>
            <span>output tokens: {m.output_tokens}</span>
            <span>cost: ${m.estimated_cost_usd}</span>
          </div>
          <ul className="mt-2 space-y-0.5">
            {m.node_timings.map((t, i) => (
              <li key={i}>
                {t.node}: {t.duration_ms} ms
              </li>
            ))}
          </ul>
        </details>
      </div>
    </div>
  );
}

function Citations({ sources }: { sources: SourceDocument[] }) {
  if (sources.length === 0) return null;
  return (
    <div className="mt-3 space-y-1">
      <p className="text-xs font-semibold text-zinc-400">Sources</p>
      {sources.map((source) => (
        <details key={source.id} className="rounded-md bg-zinc-950 px-2 py-1 text-xs text-zinc-400">
          <summary className="cursor-pointer">
            {source.filename}
            {source.page ? ` · p.${source.page}` : ""} · chunk {source.chunk_index} · score {source.score}
          </summary>
          <p className="mt-1 whitespace-pre-wrap text-zinc-500">{source.content}</p>
        </details>
      ))}
    </div>
  );
}
