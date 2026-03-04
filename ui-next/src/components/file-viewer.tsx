"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { api } from "@/lib/api";

interface FileViewerProps {
  problemId: string;
  file: { name: string; size: number };
}

function extOf(name: string): string {
  const parts = name.split(".");
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : "";
}

function langFor(ext: string): string {
  const map: Record<string, string> = {
    py: "python",
    js: "javascript",
    ts: "typescript",
    tsx: "tsx",
    jsx: "jsx",
    json: "json",
    yaml: "yaml",
    yml: "yaml",
    sh: "bash",
    sql: "sql",
    toml: "toml",
    csv: "csv",
    r: "r",
  };
  return map[ext] || "text";
}

const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "svg", "webp"]);
const CODE_EXTS = new Set(["py", "js", "ts", "tsx", "jsx", "json", "yaml", "yml", "sh", "sql", "toml", "r"]);

export function FileViewer({ problemId, file }: FileViewerProps) {
  const [expanded, setExpanded] = useState(false);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const ext = extOf(file.name);
  const fileUrl = api.problems.fileUrl(problemId, file.name);
  const isImage = IMAGE_EXTS.has(ext);
  const isMd = ext === "md";
  const isCode = CODE_EXTS.has(ext);
  const isCsv = ext === "csv";
  const isViewable = isImage || isMd || isCode || isCsv;

  async function loadText() {
    if (textContent !== null) return;
    setLoading(true);
    try {
      const res = await fetch(fileUrl);
      if (res.ok) {
        setTextContent(await res.text());
      } else {
        setTextContent(`[Error loading file: ${res.status}]`);
      }
    } catch {
      setTextContent("[Error loading file]");
    } finally {
      setLoading(false);
    }
  }

  function toggleExpand() {
    if (!expanded && textContent === null) {
      loadText();
    }
    setExpanded(!expanded);
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden">
      <div
        className={`flex items-center justify-between px-4 py-2.5 ${
          expanded ? "bg-slate-100 border-b border-slate-200" : "hover:bg-slate-50"
        } ${isViewable ? "cursor-pointer" : ""}`}
        onClick={isViewable ? toggleExpand : undefined}
      >
        <div className="flex items-center gap-3 min-w-0">
          <FileIcon ext={ext} />
          <span className="text-sm text-slate-700 font-mono truncate">{file.name}</span>
          {isViewable && (
            <span className="text-xs text-slate-400">{expanded ? "▼" : "▶"}</span>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs text-slate-400">{formatSize(file.size)}</span>
          <a
            href={fileUrl}
            download
            onClick={(e) => e.stopPropagation()}
            className="text-xs text-sky-600 hover:text-sky-800 font-medium"
          >
            Download
          </a>
        </div>
      </div>

      {expanded && (
        <div className="max-h-[600px] overflow-auto">
          {loading && (
            <div className="p-6 text-center text-sm text-slate-400">Loading...</div>
          )}

          {isImage && (
            <div className="p-4 flex justify-center bg-slate-50">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={fileUrl}
                alt={file.name}
                className="max-w-full max-h-[500px] rounded shadow-sm"
              />
            </div>
          )}

          {isMd && textContent !== null && (
            <div className="p-6 prose prose-sm prose-slate max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {textContent}
              </ReactMarkdown>
            </div>
          )}

          {isCode && textContent !== null && (
            <SyntaxHighlighter
              language={langFor(ext)}
              style={oneDark}
              customStyle={{ margin: 0, borderRadius: 0, fontSize: "0.8rem" }}
              showLineNumbers
            >
              {textContent}
            </SyntaxHighlighter>
          )}

          {isCsv && textContent !== null && (
            <div className="overflow-x-auto">
              <CsvTable csv={textContent} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FileIcon({ ext }: { ext: string }) {
  const isImage = IMAGE_EXTS.has(ext);
  const isMd = ext === "md";
  const isCode = CODE_EXTS.has(ext);

  let color = "text-slate-400";
  if (isImage) color = "text-purple-400";
  else if (isMd) color = "text-sky-400";
  else if (isCode) color = "text-emerald-400";
  else if (ext === "csv") color = "text-amber-400";

  return (
    <svg className={`h-4 w-4 ${color} shrink-0`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  );
}

function CsvTable({ csv }: { csv: string }) {
  const lines = csv.trim().split("\n").slice(0, 50);
  if (lines.length === 0) return null;
  const headers = lines[0].split(",");
  const rows = lines.slice(1).map((l) => l.split(","));

  return (
    <table className="w-full text-xs border-collapse">
      <thead>
        <tr className="bg-slate-100">
          {headers.map((h, i) => (
            <th key={i} className="px-3 py-2 text-left font-medium text-slate-600 border-b border-slate-200">
              {h.trim()}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((cells, ri) => (
          <tr key={ri} className={ri % 2 === 0 ? "" : "bg-slate-50"}>
            {cells.map((c, ci) => (
              <td key={ci} className="px-3 py-1.5 text-slate-700 border-b border-slate-100">
                {c.trim()}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
      {lines.length >= 50 && (
        <tfoot>
          <tr>
            <td colSpan={headers.length} className="px-3 py-2 text-slate-400 text-center italic">
              Showing first 50 rows
            </td>
          </tr>
        </tfoot>
      )}
    </table>
  );
}
