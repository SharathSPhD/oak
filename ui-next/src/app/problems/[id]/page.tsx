"use client";

import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, wsUrl } from "@/lib/api";
import { useWebSocket } from "@/hooks/use-websocket";
import { Card, CardContent, CardHeader, MetricCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { Tabs } from "@/components/ui/tabs";
import { formatDate, formatBytes, truncateId } from "@/lib/utils";

export default function ProblemDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const problem = useQuery({ queryKey: ["problem", id], queryFn: () => api.problems.get(id) });
  const tasks = useQuery({ queryKey: ["tasks", id], queryFn: () => api.tasks.list(id), refetchInterval: 10_000 });
  const logs = useQuery({ queryKey: ["logs", id], queryFn: () => api.problems.logs(id), refetchInterval: 8_000 });
  const containerStatus = useQuery({ queryKey: ["containerStatus", id], queryFn: () => api.problems.status(id), refetchInterval: 10_000 });
  const files = useQuery({ queryKey: ["files", id], queryFn: () => api.problems.files(id), refetchInterval: 15_000 });
  const verdicts = useQuery({ queryKey: ["verdicts", id], queryFn: () => api.judgeVerdicts(id) });

  const ws = useWebSocket(problem.data?.status === "active" ? wsUrl(id) : null);

  const startMutation = useMutation({
    mutationFn: () => api.problems.start(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["problem", id] }),
  });

  const p = problem.data;
  if (problem.isLoading) {
    return <div className="page-container"><p className="text-sm text-slate-500">Loading...</p></div>;
  }
  if (!p) {
    return <div className="page-container"><p className="text-sm text-red-500">Problem not found.</p></div>;
  }

  const taskIcons: Record<string, string> = {
    pending: "text-slate-400",
    claimed: "text-sky-500",
    complete: "text-emerald-500",
    failed: "text-red-500",
  };

  return (
    <div>
      <div className="page-header">
        <div className="flex items-center gap-3 mb-1">
          <StatusBadge status={p.status} />
          <span className="text-xs text-slate-400 font-mono">{truncateId(p.id, 12)}</span>
        </div>
        <h1 className="page-title">{p.title}</h1>
        {p.description && (
          <p className="page-subtitle mt-2 max-w-3xl">{p.description}</p>
        )}
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4 mb-6">
        <MetricCard label="Status" value={p.status.toUpperCase()} />
        <MetricCard label="Created" value={formatDate(p.created_at)} />
        <MetricCard
          label="Container"
          value={containerStatus.data?.container_status?.split(" ")[0] ?? "--"}
        />
        <MetricCard label="Tasks" value={tasks.data?.length ?? 0} />
      </div>

      {p.status === "pending" && (
        <div className="mb-6">
          <Button onClick={() => startMutation.mutate()} loading={startMutation.isPending} size="lg">
            Start Pipeline
          </Button>
        </div>
      )}

      <Tabs
        tabs={[
          {
            id: "tasks",
            label: "Tasks",
            count: tasks.data?.length,
            content: (
              <div className="space-y-2">
                {!tasks.data?.length && (
                  <p className="text-sm text-slate-500 py-4">No tasks created yet.</p>
                )}
                {tasks.data?.map((t) => (
                  <Card key={t.id}>
                    <CardContent className="flex items-center gap-4 py-3">
                      <div className={`h-2.5 w-2.5 rounded-full ${
                        t.status === "complete" ? "bg-emerald-500" :
                        t.status === "failed" ? "bg-red-500" :
                        t.status === "claimed" ? "bg-sky-500" : "bg-slate-300"
                      }`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-900">{t.title}</p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {t.task_type} {t.assigned_to ? `\u2192 ${t.assigned_to}` : ""}
                        </p>
                      </div>
                      <StatusBadge status={t.status} />
                    </CardContent>
                  </Card>
                ))}
              </div>
            ),
          },
          {
            id: "logs",
            label: "Logs",
            content: (
              <div>
                {ws.connected && (
                  <div className="mb-2 flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-xs text-emerald-600 font-medium">Live stream connected</span>
                  </div>
                )}
                <div className="rounded-lg bg-slate-900 p-4 max-h-[600px] overflow-y-auto">
                  <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">
                    {logs.data?.logs || "No logs available yet."}
                    {ws.messages.length > 0 && (
                      <>
                        {"\n--- Live Stream ---\n"}
                        {ws.messages.join("\n")}
                      </>
                    )}
                  </pre>
                </div>
              </div>
            ),
          },
          {
            id: "files",
            label: "Files",
            count: files.data?.files.length,
            content: (
              <div>
                {files.data?.workspace && (
                  <p className="text-xs text-slate-400 mb-3 font-mono">{files.data.workspace}</p>
                )}
                {!files.data?.files.length && (
                  <p className="text-sm text-slate-500 py-4">No files in workspace yet.</p>
                )}
                <div className="space-y-1">
                  {files.data?.files.map((f) => (
                    <div
                      key={f.name}
                      className="flex items-center justify-between rounded-lg px-4 py-2.5 hover:bg-slate-50"
                    >
                      <div className="flex items-center gap-3">
                        <svg className="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                        </svg>
                        <span className="text-sm text-slate-700 font-mono">{f.name}</span>
                      </div>
                      <span className="text-xs text-slate-400">{formatBytes(f.size)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ),
          },
          {
            id: "verdicts",
            label: "Judge Verdicts",
            count: verdicts.data?.length,
            content: (
              <div className="space-y-2">
                {!verdicts.data?.length && (
                  <p className="text-sm text-slate-500 py-4">No judge verdicts yet.</p>
                )}
                {verdicts.data?.map((v) => (
                  <Card key={v.id}>
                    <CardContent className="py-3">
                      <div className="flex items-center gap-3 mb-2">
                        <StatusBadge status={v.verdict === "pass" ? "complete" : "failed"} />
                        <span className="text-xs text-slate-400">{formatDate(v.created_at)}</span>
                      </div>
                      {v.notes && <p className="text-sm text-slate-600">{v.notes}</p>}
                      {Object.keys(v.checks).length > 0 && (
                        <pre className="mt-2 rounded bg-slate-50 p-2 text-xs text-slate-600 overflow-x-auto">
                          {JSON.stringify(v.checks, null, 2)}
                        </pre>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            ),
          },
        ]}
      />

      {p.solution_url && (
        <div className="mt-6 rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3">
          <p className="text-sm text-emerald-700">
            Solution: <a href={p.solution_url} className="underline font-medium">{p.solution_url}</a>
          </p>
        </div>
      )}
    </div>
  );
}
