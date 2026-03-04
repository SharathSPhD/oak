"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, CardContent, MetricCard } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";

export default function Dashboard() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15_000 });
  const problems = useQuery({ queryKey: ["problems"], queryFn: api.problems.list });
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.agents.status });

  const activeCount = problems.data?.filter((p) => p.status === "active").length ?? 0;
  const completeCount = problems.data?.filter((p) => p.status === "complete").length ?? 0;
  const agentCount = agents.data?.length ?? 0;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">
          System overview and quick actions
        </p>
      </div>

      {/* Health bar */}
      <div className="mb-6 flex items-center gap-3 rounded-lg border px-4 py-2.5 bg-white">
        <div className={`h-2.5 w-2.5 rounded-full ${health.data ? "bg-emerald-500" : "bg-red-500"}`} />
        <span className="text-sm font-medium text-slate-700">
          {health.data ? "System Healthy" : health.isLoading ? "Checking..." : "System Unreachable"}
        </span>
        {health.data && (
          <>
            <span className="text-slate-300">|</span>
            <span className="text-xs text-slate-500">
              Mode: {health.data.oak_mode.toUpperCase()} &middot; Routing: {health.data.routing_strategy}
            </span>
          </>
        )}
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <MetricCard
          label="Total Problems"
          value={problems.data?.length ?? "--"}
          subtext={`${activeCount} active`}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>}
        />
        <MetricCard
          label="Completed"
          value={completeCount}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
        />
        <MetricCard
          label="Active Agents"
          value={agentCount}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" /></svg>}
        />
        <MetricCard
          label="Models"
          value={health.data ? Object.keys(health.data.models).length : "--"}
          subtext={health.data?.models?.coder ?? ""}
          icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25z" /></svg>}
        />
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 mb-8">
        <Link href="/submit" className="group">
          <Card className="h-full border-2 border-dashed border-oak-200 hover:border-oak-400 bg-oak-50/30">
            <CardContent className="flex flex-col items-center py-8">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-oak-100 text-oak-600 group-hover:bg-oak-200 transition-colors">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
              </div>
              <p className="font-semibold text-slate-900">Submit Problem</p>
              <p className="text-xs text-slate-500 mt-1">Start a new analytical pipeline</p>
            </CardContent>
          </Card>
        </Link>
        <Link href="/gallery" className="group">
          <Card className="h-full hover:border-slate-300">
            <CardContent className="flex flex-col items-center py-8">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600 group-hover:bg-slate-200 transition-colors">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6z" /></svg>
              </div>
              <p className="font-semibold text-slate-900">View Gallery</p>
              <p className="text-xs text-slate-500 mt-1">Browse all problems</p>
            </CardContent>
          </Card>
        </Link>
        <Link href="/telemetry" className="group">
          <Card className="h-full hover:border-slate-300">
            <CardContent className="flex flex-col items-center py-8">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-600 group-hover:bg-slate-200 transition-colors">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75z" /></svg>
              </div>
              <p className="font-semibold text-slate-900">Telemetry</p>
              <p className="text-xs text-slate-500 mt-1">Monitor agent performance</p>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* Recent problems */}
      {problems.data && problems.data.length > 0 && (
        <Card>
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900">Recent Problems</h2>
            <Link href="/gallery" className="text-xs text-oak-600 hover:text-oak-700 font-medium">View all</Link>
          </div>
          <div className="divide-y divide-slate-50">
            {problems.data.slice(0, 5).map((p) => (
              <Link
                key={p.id}
                href={`/problems/${p.id}`}
                className="flex items-center justify-between px-6 py-3 hover:bg-slate-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <StatusBadge status={p.status} />
                  <div>
                    <p className="text-sm font-medium text-slate-900">{p.title}</p>
                    <p className="text-xs text-slate-400">{formatDate(p.created_at)}</p>
                  </div>
                </div>
                <svg className="h-4 w-4 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
              </Link>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
