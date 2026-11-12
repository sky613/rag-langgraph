import { FileText, Loader2, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ragApi } from "../api/ragApi";
import type { DocumentItem } from "../types/rag";

export function DocumentPanel() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = () =>
    ragApi
      .listDocuments()
      .then(setDocuments)
      .catch((err: Error) => setError(err.message));

  useEffect(() => {
    void refresh();
  }, []);

  async function handleUpload(file: File) {
    setUploading(true);
    setError(null);
    try {
      await ragApi.uploadDocument(file);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleDelete(doc: DocumentItem) {
    if (!window.confirm(`"${doc.filename}" 문서를 삭제할까요?`)) return;
    setError(null);
    try {
      await ragApi.deleteDocument(doc.id);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <aside className="flex w-80 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 p-4">
      <h2 className="mb-3 text-sm font-semibold text-zinc-300">Documents</h2>
      <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-700 px-3 py-4 text-sm text-zinc-400 hover:border-zinc-500 hover:text-zinc-200">
        {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
        {uploading ? "Indexing..." : "Upload PDF / TXT / MD"}
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.md,.markdown"
          className="hidden"
          disabled={uploading}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleUpload(file);
          }}
        />
      </label>
      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
      <ul className="mt-4 flex-1 space-y-2 overflow-y-auto">
        {documents.length === 0 && <li className="text-xs text-zinc-500">No documents yet.</li>}
        {documents.map((doc) => (
          <li key={doc.id} className="flex items-center gap-2 rounded-md bg-zinc-900 px-3 py-2 text-sm">
            <FileText className="h-4 w-4 shrink-0 text-zinc-500" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-zinc-200">{doc.filename}</p>
              <p className="text-xs text-zinc-500">
                {doc.chunk_count} chunks · {(doc.size_bytes / 1024).toFixed(1)} KB
              </p>
            </div>
            <button
              type="button"
              aria-label={`Delete ${doc.filename}`}
              onClick={() => void handleDelete(doc)}
              className="text-zinc-500 hover:text-red-400"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
