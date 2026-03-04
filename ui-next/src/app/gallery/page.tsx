"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Problem } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { formatDate, truncateId } from "@/lib/utils";

export default function GalleryPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<string>("all");
  const problems = useQuery({ queryKey: ["problems"], queryFn: api.problems.list });

  const deleteMutation = useMutation({
    mutationFn: api.problems.delete,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["problems"] }),
  });

  const cleanupMutation = useMutation({
    mutationFn: api.problems.cleanup,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["problems"] }),
  });

  const startMutation = useMutation({
    mutationFn: api.problems.start,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["problems"] }),
  });

  const filtered = problems.data?.filter(
    (p) => filter === "all" || p.status === filter
  );

  const statusCounts: Record<string, number> = {};
  problems.data?.forEach((p) => {
    statusCounts[p.status] = (statusCounts[p.status] || 0) + 1;
  });

  return (
    <div>
      <div className="page-header flex items-start justify-between">
        <div>
          <h1 className="page-title">Problem Gallery</h1>
          <p className="page-subtitle">
            All submitted problems and their pipeline status.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            loading={cleanupMutation.isPending}
            onClick={() => cleanupMutation.mutate()}
          >
            Clean Stale
          </Button>
          <Link href="/submit">
            <Button size="sm">New Problem</Button>
          </Link>
        </div>
      </div>

      {cleanupMutation.data && (
        <div className="mb-4 rounded-lg bg-sky-50 border border-sky-200 px-4 py-2 text-sm text-sky-700">
          Cleaned {cleanupMutation.data.cleaned} of {cleanupMutation.data.total_checked} stale problems.
        </div>
      )}

      {/* Filter tabs */}
      <div className="mb-6 flex gap-1 rounded-lg bg-slate-100 p-1 w-fit">
        {["all", "pending", "active", "complete", "failed"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              filter === s
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
            {s !== "all" && statusCounts[s] ? ` (${statusCounts[s]})` : ""}
            {s === "all" ? ` (${problems.data?.length ?? 0})` : ""}
          </button>
        ))}
      </div>

      {/* Problem list */}
      {problems.isLoading && (
        <div className="empty-state">
          <p className="text-sm text-slate-500">Loading problems...</p>
        </div>
      )}

      {filtered && filtered.length === 0 && (
        <div className="empty-state">
          <svg className="h-12 w-12 text-slate-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>
          <p className="text-sm font-medium text-slate-600">No problems found</p>
          <p className="text-xs text-slate-400 mt-1">Submit a new problem to get started.</p>
        </div>
      )}

      <div className="space-y-3">
        {filtered?.map((p) => (
          <ProblemRow
            key={p.id}
            problem={p}
            onDelete={() => {
              if (confirm(`Delete problem "${p.title}"? This cannot be undone.`)) {
                deleteMutation.mutate(p.id);
              }
            }}
            onStart={() => startMutation.mutate(p.id)}
            isStarting={startMutation.isPending}
          />
        ))}
      </div>
    </div>
  );
}

function ProblemRow({
  problem: p,
  onDelete,
  onStart,
  isStarting,
}: {
  problem: Problem;
  onDelete: () => void;
  onStart: () => void;
  isStarting: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between py-4">
        <Link
          href={`/problems/${p.id}`}
          className="flex items-center gap-4 flex-1 min-w-0"
        >
          <StatusBadge status={p.status} />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-slate-900 truncate">{p.title}</p>
            <p className="text-xs text-slate-400 mt-0.5">
              {truncateId(p.id)} &middot; {formatDate(p.created_at)}
            </p>
          </div>
        </Link>
        <div className="flex items-center gap-2 ml-4 shrink-0">
          {p.status === "pending" && (
            <Button variant="primary" size="sm" onClick={onStart} loading={isStarting}>
              Start
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={onDelete}>
            <svg className="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" /></svg>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
