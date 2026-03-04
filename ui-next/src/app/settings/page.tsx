"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function SettingsPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 30_000 });
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.agents.status, refetchInterval: 15_000 });

  const h = health.data;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">System Settings</h1>
        <p className="page-subtitle">
          Current system configuration and service status. Settings are controlled via
          environment variables in the Docker Compose configuration.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* System health */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-slate-900">System Health</h2>
            <div className={`h-2.5 w-2.5 rounded-full ${h ? "bg-emerald-500" : "bg-red-500"}`} />
          </CardHeader>
          <CardContent>
            {h ? (
              <div className="space-y-3">
                <Row label="Status" value={h.status} />
                <Row label="Platform Mode" value={h.oak_mode.toUpperCase()} />
                <Row label="Routing Strategy" value={h.routing_strategy} />
                <Row label="API Key Present" value={h.api_key_present ? "Yes" : "No"} />
                <Row label="Max Agents / Problem" value={String(h.max_agents_per_problem)} />
                <Row label="Max Concurrent Problems" value={String(h.max_concurrent_problems)} />
              </div>
            ) : (
              <p className="text-sm text-slate-500">Unable to reach API</p>
            )}
          </CardContent>
        </Card>

        {/* Active agents */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-slate-900">Active Agents</h2>
            <Badge variant={agents.data && agents.data.length > 0 ? "success" : "secondary"}>
              {agents.data?.length ?? 0} running
            </Badge>
          </CardHeader>
          <CardContent>
            {agents.data && agents.data.length > 0 ? (
              <div className="space-y-2">
                {agents.data.map((agent) => (
                  <div key={agent.agent_id} className="flex items-center justify-between rounded-lg border border-slate-100 px-4 py-3">
                    <div>
                      <p className="text-sm font-medium text-slate-900">{agent.role}</p>
                      <p className="text-xs text-slate-400">{agent.agent_id}</p>
                    </div>
                    <Badge variant={agent.status === "running" ? "success" : agent.status === "idle" ? "warning" : "danger"}>
                      {agent.status}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 py-4">No agents currently active.</p>
            )}
          </CardContent>
        </Card>

        {/* Configuration reference */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <h2 className="text-sm font-semibold text-slate-900">Configuration Reference</h2>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg bg-slate-50 p-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left py-2 pr-4 text-xs font-medium text-slate-500 uppercase tracking-wider">Variable</th>
                    <th className="text-left py-2 pr-4 text-xs font-medium text-slate-500 uppercase tracking-wider">Description</th>
                    <th className="text-left py-2 text-xs font-medium text-slate-500 uppercase tracking-wider">Default</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {configVars.map(({ name, desc, def }) => (
                    <tr key={name}>
                      <td className="py-2 pr-4 font-mono text-xs text-slate-700">{name}</td>
                      <td className="py-2 pr-4 text-xs text-slate-600">{desc}</td>
                      <td className="py-2 font-mono text-xs text-slate-400">{def}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-slate-600">{label}</span>
      <span className="text-sm font-medium text-slate-900">{value}</span>
    </div>
  );
}

const configVars = [
  { name: "OAK_MODE", desc: "Platform profile", def: "dgx" },
  { name: "OAK_ROOT", desc: "Host path to OAK repo", def: "/app" },
  { name: "OAK_WORKSPACE_BASE", desc: "Host path for problem workspaces", def: "/workspaces" },
  { name: "META_AGENT_ENABLED", desc: "Enable self-improvement agent", def: "true" },
  { name: "CODER_MODEL", desc: "Model for code generation tasks", def: "qwen3-coder" },
  { name: "ANALYSIS_MODEL", desc: "Model for analysis tasks", def: "glm-4.7" },
  { name: "REASONING_MODEL", desc: "Model for orchestration/judge", def: "llama3.3:70b" },
  { name: "MAX_AGENTS_PER_PROBLEM", desc: "Max agent containers per problem", def: "10" },
  { name: "MAX_CONCURRENT_PROBLEMS", desc: "Max simultaneous problems", def: "3" },
  { name: "OAK_DAEMON_POLL_INTERVAL", desc: "Daemon health check interval (seconds)", def: "60" },
];
