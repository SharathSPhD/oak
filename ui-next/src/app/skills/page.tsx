"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge, Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";

export default function SkillsPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const skills = useQuery({
    queryKey: ["skills", query, category, statusFilter],
    queryFn: () => api.skills.list({ query: query || undefined, category, status: statusFilter }),
  });

  const promoteMutation = useMutation({
    mutationFn: api.skills.promote,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["skills"] }),
  });

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Skill Library</h1>
        <p className="page-subtitle">
          Reusable patterns extracted from solved problems. Skills start as probationary
          and get promoted to permanent after proving useful across multiple problems.
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap gap-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search skills..."
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm focus:border-oak-500 focus:ring-2 focus:ring-oak-500/20 focus:outline-none w-64"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white focus:border-oak-500 focus:ring-2 focus:ring-oak-500/20 focus:outline-none"
        >
          <option value="all">All Categories</option>
          <option value="etl">ETL</option>
          <option value="analysis">Analysis</option>
          <option value="ml">ML</option>
          <option value="ui">UI</option>
          <option value="infra">Infra</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white focus:border-oak-500 focus:ring-2 focus:ring-oak-500/20 focus:outline-none"
        >
          <option value="all">All Status</option>
          <option value="permanent">Permanent</option>
          <option value="probationary">Probationary</option>
        </select>
      </div>

      {/* Skills grid */}
      {skills.isLoading && <p className="text-sm text-slate-500">Loading skills...</p>}

      {skills.data && skills.data.length === 0 && (
        <div className="empty-state">
          <svg className="h-12 w-12 text-slate-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}><path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
          <p className="text-sm font-medium text-slate-600">No skills found</p>
          <p className="text-xs text-slate-400 mt-1">Skills are extracted automatically after problems are solved.</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {skills.data?.map((skill) => (
          <Card key={skill.id}>
            <CardContent className="py-4">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">{skill.name}</h3>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant="secondary">{skill.category}</Badge>
                    <StatusBadge status={skill.status} />
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-lg font-bold text-slate-900">{skill.use_count}</p>
                  <p className="text-[10px] text-slate-400 uppercase tracking-wider">uses</p>
                </div>
              </div>
              <p className="text-xs text-slate-600 leading-relaxed line-clamp-3 mb-3">
                {skill.description}
              </p>
              {skill.trigger_keywords && skill.trigger_keywords.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-3">
                  {skill.trigger_keywords.map((kw) => (
                    <span key={kw} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 font-mono">
                      {kw}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                <span className="text-[10px] text-slate-400">{formatDate(skill.created_at)}</span>
                {skill.status === "probationary" && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => promoteMutation.mutate(skill.id)}
                    loading={promoteMutation.isPending}
                  >
                    Promote
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
