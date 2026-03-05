"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, MetricCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const DOMAINS = [
  "sales", "pricing", "marketing", "supply_chain", "customer",
  "finance", "operations", "human_capital", "product",
];

function statusColor(status: string): string {
  const map: Record<string, string> = {
    idle: "bg-slate-100 text-slate-600",
    perceiving: "bg-blue-100 text-blue-700",
    deciding: "bg-amber-100 text-amber-700",
    running: "bg-oak-100 text-oak-700",
    resting: "bg-slate-100 text-slate-500",
    paused: "bg-yellow-100 text-yellow-700",
    deferred: "bg-indigo-100 text-indigo-700",
    error: "bg-red-100 text-red-700",
    stopped: "bg-red-100 text-red-700",
  };
  return map[status] ?? "bg-slate-100 text-slate-600";
}

function statusDot(status: string): string {
  const pulsing = ["perceiving", "deciding", "running"];
  return pulsing.includes(status) ? "animate-pulse" : "";
}

function breakerBadge(state: string) {
  if (state === "halted") return <Badge variant="danger">HALTED</Badge>;
  if (state === "degraded") return <Badge variant="warning">DEGRADED</Badge>;
  return <Badge variant="success">CLOSED</Badge>;
}

function timeAgo(isoStr: string | undefined): string {
  if (!isoStr) return "--";
  const diff = Date.now() - new Date(isoStr).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m ago`;
}

export default function BuilderPage() {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["builder-status"],
    queryFn: api.builder.status,
    refetchInterval: 3_000,
  });
  const history = useQuery({
    queryKey: ["builder-history"],
    queryFn: api.builder.history,
    refetchInterval: 10_000,
  });
  const thoughts = useQuery({
    queryKey: ["builder-thoughts"],
    queryFn: api.builder.thoughts,
    refetchInterval: 5_000,
  });

  const startMutation = useMutation({
    mutationFn: api.builder.startSprint,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["builder-status"] }),
  });
  const pauseMutation = useMutation({
    mutationFn: api.builder.pause,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["builder-status"] }),
  });
  const resumeMutation = useMutation({
    mutationFn: api.builder.resume,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["builder-status"] }),
  });
  const stopMutation = useMutation({
    mutationFn: api.builder.stop,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["builder-status"] });
      queryClient.invalidateQueries({ queryKey: ["builder-thoughts"] });
    },
  });

  const s = status.data;
  const h = history.data;
  const cb = s?.circuit_breaker;
  const sprints = h?.recent_sprints ?? [];
  const thoughtsList = thoughts.data?.thoughts ?? [];

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Self-Build</h1>
        <p className="page-subtitle">
          Autonomous cortex lifecycle, skill acquisition, and release management.
        </p>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <MetricCard
          label="Cortex Status"
          value={s?.status?.toUpperCase() ?? "--"}
          subtext={s?.last_action ? `Action: ${s.last_action}` : undefined}
          icon={
            <div className={`inline-flex items-center justify-center h-5 w-5 rounded-full ${statusColor(s?.status ?? "idle")}`}>
              <div className={`h-2 w-2 rounded-full bg-current ${statusDot(s?.status ?? "idle")}`} />
            </div>
          }
        />
        <MetricCard
          label="Cycle Count"
          value={s?.cycle_count ?? h?.sprint_count ?? 0}
          subtext={s?.last_action_time ? timeAgo(s.last_action_time) : undefined}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" /></svg>}
        />
        <MetricCard
          label="Total Skills"
          value={h?.total_skills ?? 0}
          subtext={`${h?.total_commits ?? 0} commits`}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>}
        />
        <MetricCard
          label="Circuit Breaker"
          value={cb?.state?.toUpperCase() ?? "CLOSED"}
          subtext={`${cb?.consecutive_failures ?? 0} consecutive failures`}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" /></svg>}
        />
      </div>

      {/* Controls + Last result */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 mb-8">
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-slate-900">Controls</h2>
          </CardHeader>
          <CardContent>
            <div className="flex gap-3 flex-wrap">
              <button
                className="rounded-lg bg-oak-600 px-4 py-2 text-sm font-medium text-white hover:bg-oak-700 disabled:opacity-50 transition-colors"
                onClick={() => startMutation.mutate()}
                disabled={startMutation.isPending}
              >
                {startMutation.isPending ? "Triggering..." : "Start Sprint"}
              </button>
              <button
                className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50 transition-colors"
                onClick={() => pauseMutation.mutate()}
                disabled={pauseMutation.isPending}
              >
                Pause
              </button>
              <button
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                onClick={() => resumeMutation.mutate()}
                disabled={resumeMutation.isPending}
              >
                Resume / Reset CB
              </button>
              <button
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                onClick={() => {
                  if (confirm("Stop the builder? This will halt the cortex and clean up all harness containers.")) {
                    stopMutation.mutate();
                  }
                }}
                disabled={stopMutation.isPending}
              >
                {stopMutation.isPending ? "Stopping..." : "Stop Builder"}
              </button>
            </div>
            {stopMutation.isSuccess && (
              <div className="mt-3 rounded-lg bg-red-50 border border-red-200 p-3">
                <p className="text-sm text-red-700 font-medium">Builder stopped successfully.</p>
              </div>
            )}
            {s?.last_action_result && (
              <div className="mt-4 rounded-lg bg-slate-50 p-3">
                <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Last Result</p>
                <p className="text-sm text-slate-700 font-mono">{s.last_action_result}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Domain coverage */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <h2 className="text-sm font-semibold text-slate-900">Domain Coverage</h2>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {DOMAINS.map((d) => {
                const baseline = h?.domain_baselines?.[d];
                const pct = baseline != null ? Math.round(baseline * 100) : 0;
                return (
                  <div key={d}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-slate-700 capitalize">
                        {d.replace(/_/g, " ")}
                      </span>
                      <span className="text-xs text-slate-500">
                        {baseline != null ? `${(baseline * 100).toFixed(0)}%` : "--"}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100">
                      <div
                        className="h-2 rounded-full bg-oak-500 transition-all"
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Thoughts log */}
      <Card className="mb-8">
        <CardHeader>
          <h2 className="text-sm font-semibold text-slate-900">
            Cortex Thoughts
            {thoughts.data && (
              <span className="ml-2 text-xs text-slate-400 font-normal">
                ({thoughts.data.total} total, showing last {thoughtsList.length})
              </span>
            )}
          </h2>
        </CardHeader>
        <CardContent>
          {thoughtsList.length > 0 ? (
            <div className="max-h-64 overflow-y-auto space-y-1 font-mono text-xs">
              {[...thoughtsList].reverse().map((t, i) => {
                const isError = t.toLowerCase().includes("error") || t.toLowerCase().includes("failed");
                const isSuccess = t.toLowerCase().includes("result: ") && !isError;
                const isDecision = t.toLowerCase().includes("llm chose") || t.toLowerCase().includes("executing:");
                return (
                  <div
                    key={i}
                    className={`px-2 py-1 rounded ${
                      isError ? "bg-red-50 text-red-700" :
                      isSuccess ? "bg-emerald-50 text-emerald-700" :
                      isDecision ? "bg-blue-50 text-blue-700" :
                      "text-slate-600"
                    }`}
                  >
                    {t}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-slate-500 py-4">No thoughts recorded yet. The cortex will log its decisions here.</p>
          )}
        </CardContent>
      </Card>

      {/* Action history */}
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-slate-900">
            Action History
            {h && <span className="ml-2 text-xs text-slate-400 font-normal">({h.sprint_count} cycles)</span>}
          </h2>
        </CardHeader>
        <CardContent>
          {sprints.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="py-2 px-3 text-left text-xs font-medium text-slate-500">Cycle</th>
                    <th className="py-2 px-3 text-left text-xs font-medium text-slate-500">Time</th>
                    <th className="py-2 px-3 text-left text-xs font-medium text-slate-500">Action</th>
                    <th className="py-2 px-3 text-left text-xs font-medium text-slate-500">Summary</th>
                    <th className="py-2 px-3 text-center text-xs font-medium text-slate-500">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {[...sprints].reverse().map((sp, idx) => (
                    <tr key={idx} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="py-2 px-3 font-mono text-xs">#{sp.sprint_number}</td>
                      <td className="py-2 px-3 text-xs text-slate-600">{timeAgo(sp.started_at)}</td>
                      <td className="py-2 px-3 text-xs">
                        <span className="font-medium text-slate-800">{sp.action ?? "unknown"}</span>
                      </td>
                      <td className="py-2 px-3 text-xs text-slate-600 max-w-xs truncate">
                        {sp.summary ?? "--"}
                      </td>
                      <td className="py-2 px-3 text-center">
                        {sp.success ? (
                          <Badge variant="success">Pass</Badge>
                        ) : (
                          <Badge variant="danger">Fail</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-500 py-4">No actions recorded yet. Start a sprint to begin self-improvement.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
