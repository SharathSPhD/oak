const API_BASE =
  typeof window !== "undefined"
    ? (window as unknown as { __OAK_API_URL__?: string }).__OAK_API_URL__ ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// -- Types --

export interface Problem {
  id: string;
  title: string;
  description: string | null;
  status: string;
  solution_url: string | null;
  idempotency_key: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface Task {
  id: string;
  problem_id: string;
  title: string;
  description: string | null;
  task_type: string;
  status: string;
  assigned_to: string | null;
  created_at: string;
}

export interface Agent {
  agent_id: string;
  role: string;
  problem_uuid: string | null;
  status: string;
  container_id: string | null;
  last_seen: string | null;
}

export interface Skill {
  id: string;
  name: string;
  category: string;
  status: string;
  use_count: number;
  description: string;
  created_at: string;
  trigger_keywords?: string[];
  filesystem_path?: string;
}

export interface HealthData {
  status: string;
  oak_mode: string;
  routing_strategy: string;
  models: Record<string, string>;
  feature_flags: Record<string, boolean>;
  api_key_present: boolean;
  max_agents_per_problem: number;
  max_concurrent_problems: number;
}

export interface TelemetryData {
  total_events: number;
  total_escalations: number;
  escalation_rate_pct: number;
  events_by_type: Record<string, number>;
  active_problems: number;
  recent_events: Record<string, unknown>[];
}

export interface JudgeVerdict {
  id: string;
  task_id: string;
  verdict: string;
  checks: Record<string, unknown>;
  notes: string | null;
  created_at: string;
}

export interface WorkspaceFile {
  name: string;
  size: number;
}

// -- API functions --

export const api = {
  health: () => apiFetch<HealthData>("/health"),

  problems: {
    list: () => apiFetch<Problem[]>("/api/problems"),
    get: (id: string) => apiFetch<Problem>(`/api/problems/${id}`),
    create: (data: { title: string; description: string }) =>
      apiFetch<Problem>("/api/problems", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    start: (id: string) =>
      apiFetch<{ id: string; status: string; container_name: string; message: string }>(
        `/api/problems/${id}/start`,
        { method: "POST" }
      ),
    delete: (id: string) =>
      apiFetch<void>(`/api/problems/${id}`, { method: "DELETE" }),
    updateStatus: (id: string, status: string) =>
      apiFetch<Problem>(`/api/problems/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    cleanup: () =>
      apiFetch<{ cleaned: number; total_checked: number }>("/api/problems/cleanup", {
        method: "POST",
      }),
    upload: async (id: string, file: File) => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/api/problems/${id}/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      return res.json();
    },
    logs: (id: string) =>
      apiFetch<{ container: string; logs: string }>(`/api/problems/${id}/logs`),
    status: (id: string) =>
      apiFetch<{ container: string; container_status: string }>(
        `/api/problems/${id}/status`
      ),
    files: (id: string) =>
      apiFetch<{ files: WorkspaceFile[]; workspace: string }>(
        `/api/problems/${id}/files`
      ),
  },

  tasks: {
    list: (problemId: string) =>
      apiFetch<Task[]>(`/api/tasks?problem_id=${problemId}`),
  },

  agents: {
    status: () => apiFetch<Agent[]>("/api/agents/status"),
    models: () => apiFetch<{ models: Record<string, string>; role_routing: Record<string, string> }>("/api/agents/models"),
  },

  skills: {
    list: (params?: { query?: string; category?: string; status?: string }) => {
      const sp = new URLSearchParams();
      if (params?.query) sp.set("query", params.query);
      if (params?.category && params.category !== "all") sp.set("category", params.category);
      if (params?.status && params.status !== "all") sp.set("status", params.status);
      const qs = sp.toString();
      return apiFetch<Skill[]>(`/api/skills${qs ? `?${qs}` : ""}`);
    },
    promote: (id: string) =>
      apiFetch<unknown>(`/api/skills/${id}/promote`, { method: "POST" }),
  },

  telemetry: () => apiFetch<TelemetryData>("/api/telemetry"),

  judgeVerdicts: (problemId: string) =>
    apiFetch<JudgeVerdict[]>(`/api/judge_verdicts/${problemId}`),
};

export function wsUrl(problemId: string): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}/ws/${problemId}`;
}
