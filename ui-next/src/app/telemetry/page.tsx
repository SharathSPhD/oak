"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, MetricCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";

export default function TelemetryPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15_000 });
  const telemetry = useQuery({ queryKey: ["telemetry"], queryFn: api.telemetry, refetchInterval: 10_000 });
  const models = useQuery({ queryKey: ["models"], queryFn: api.agents.models });

  const t = telemetry.data;
  const h = health.data;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Telemetry Dashboard</h1>
        <p className="page-subtitle">
          Real-time agent performance metrics, model routing, and system configuration.
        </p>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <MetricCard
          label="Total Events"
          value={t?.total_events ?? "--"}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" /></svg>}
        />
        <MetricCard
          label="Escalation Rate"
          value={t ? `${t.escalation_rate_pct.toFixed(1)}%` : "--"}
          subtext={`${t?.total_escalations ?? 0} escalations`}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" /></svg>}
        />
        <MetricCard
          label="Active Problems"
          value={t?.active_problems ?? "--"}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
        />
        <MetricCard
          label="System Mode"
          value={h?.oak_mode?.toUpperCase() ?? "--"}
          subtext={h?.routing_strategy ?? ""}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" /></svg>}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Events by type */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-slate-900">Events by Type</h2>
          </CardHeader>
          <CardContent>
            {t?.events_by_type && Object.keys(t.events_by_type).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(t.events_by_type)
                  .sort(([, a], [, b]) => b - a)
                  .map(([type, count]) => {
                    const maxCount = Math.max(...Object.values(t.events_by_type));
                    const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                    return (
                      <div key={type}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-medium text-slate-700">{type}</span>
                          <span className="text-xs text-slate-500">{count}</span>
                        </div>
                        <div className="h-2 rounded-full bg-slate-100">
                          <div
                            className="h-2 rounded-full bg-oak-500 transition-all"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
              </div>
            ) : (
              <p className="text-sm text-slate-500 py-4">No events recorded yet.</p>
            )}
          </CardContent>
        </Card>

        {/* Model routing */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-slate-900">Model Routing</h2>
          </CardHeader>
          <CardContent>
            {models.data ? (
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wider mb-2">Base Models</p>
                  <div className="space-y-2">
                    {Object.entries(models.data.models).map(([role, model]) => (
                      <div key={role} className="flex items-center justify-between">
                        <span className="text-sm text-slate-600 capitalize">{role}</span>
                        <code className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700 font-mono">{model}</code>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="border-t border-slate-100 pt-3">
                  <p className="text-xs text-slate-400 uppercase tracking-wider mb-2">Role Assignments</p>
                  <div className="space-y-2">
                    {Object.entries(models.data.role_routing).map(([role, model]) => (
                      <div key={role} className="flex items-center justify-between">
                        <span className="text-sm text-slate-600">{role}</span>
                        <code className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700 font-mono">{model}</code>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-500">Loading model configuration...</p>
            )}
          </CardContent>
        </Card>

        {/* Feature flags */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-slate-900">Feature Flags</h2>
          </CardHeader>
          <CardContent>
            {h?.feature_flags ? (
              <div className="space-y-3">
                {Object.entries(h.feature_flags).map(([flag, enabled]) => (
                  <div key={flag} className="flex items-center justify-between">
                    <span className="text-sm text-slate-700">
                      {flag.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                    </span>
                    <Badge variant={enabled ? "success" : "secondary"}>
                      {enabled ? "Enabled" : "Disabled"}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">Loading configuration...</p>
            )}
          </CardContent>
        </Card>

        {/* Recent events */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-slate-900">Recent Events</h2>
          </CardHeader>
          <CardContent>
            {t?.recent_events && t.recent_events.length > 0 ? (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {t.recent_events.map((ev, i) => (
                  <div key={i} className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-slate-50">
                    <div className="h-1.5 w-1.5 rounded-full bg-oak-400 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-slate-700 truncate">
                        {ev.event_type as string}
                      </p>
                      <p className="text-[10px] text-slate-400">
                        {ev.agent_id as string} &middot; {formatDate(ev.created_at as string)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 py-4">No recent events.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
