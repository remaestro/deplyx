// Thin HTTP client targeting the Deplyx backend (FastAPI).
// Configure the base URL via VITE_API_BASE_URL (e.g. http://localhost:8000/api/v1).
// Auth: bearer token from localStorage ("deplyx_token"), wire to your auth layer.

import type {
  Change, AuditEntry, Connector, Policy, Topology, Kpis, ImpactPayload,
} from "./types";

const BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ??
  "/api/v1";

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = window.localStorage.getItem("deplyx_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const AUTH_KEY = "deplyx.auth";

function clearSession(): void {
  localStorage.removeItem(AUTH_KEY);
  localStorage.removeItem("deplyx_token");
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeader(),
      ...(init.headers ?? {}),
    },
  });
  if (res.status === 401) {
    clearSession();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Unauthorized");
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/* ---------- Endpoint surface (matches Deplyx spec) ---------- */

export const api = {
  // Dashboard
  kpis: () => request<Kpis>("/dashboard/kpis"),

  // Changes
  listChanges: () => request<Change[]>("/changes"),
  getChange: (id: string) => request<Change>(`/changes/${id}`),
  createChange: (input: Partial<Change>) =>
    request<Change>("/changes", { method: "POST", body: JSON.stringify(input) }),
  updateChange: (id: string, input: Partial<Change>) =>
    request<Change>(`/changes/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
  approveChange: (id: string) =>
    request<Change>(`/changes/${id}/approve`, { method: "POST" }),
  rejectChange: (id: string, reason: string) =>
    request<Change>(`/changes/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  executeChange: (id: string) =>
    request<Change>(`/changes/${id}/execute`, { method: "POST" }),
  rollbackChange: (id: string) =>
    request<Change>(`/changes/${id}/rollback`, { method: "POST" }),
  reanalyzeChange: (id: string) =>
    request<Change>(`/changes/${id}/reanalyze`, { method: "POST" }),
  submitChange: (id: string) =>
    request<Change>(`/changes/${id}/submit`, { method: "POST" }),
  getChangeImpact: (id: string, refresh?: boolean) =>
    request<{ change_id: string; impact: ImpactPayload }>(`/changes/${id}/impact${refresh ? "?refresh=true" : ""}`, { method: "GET" }),
  riskCalculate: (changeId: string) =>
    request<{ change_id: string; impact: ImpactPayload; risk: { risk_score: number; risk_level: string } }>(
      "/risk/calculate", { method: "POST", body: JSON.stringify({ change_id: changeId }) }
    ),

  // Connectors
  listConnectors: () => request<Connector[]>("/connectors"),
  syncConnector: (id: number) =>
    request<Connector>(`/connectors/${id}/sync`, { method: "POST" }),
  deleteConnector: (id: number) =>
    request<void>(`/connectors/${id}`, { method: "DELETE" }),
  createConnector: (input: Partial<Connector>) =>
    request<Connector>("/connectors", { method: "POST", body: JSON.stringify(input) }),

  // Policies
  listPolicies: () => request<Policy[]>("/policies"),
  togglePolicy: (id: number, enabled: boolean) =>
    request<Policy>(`/policies/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),
  deletePolicy: (id: number) =>
    request<void>(`/policies/${id}`, { method: "DELETE" }),

  // Audit
  listAudit: (params?: { range?: string; action?: string }) => {
    const q = new URLSearchParams();
    if (params?.range) q.set("range", params.range);
    if (params?.action) q.set("action", params.action);
    const qs = q.toString();
    return request<AuditEntry[]>(`/audit-log${qs ? `?${qs}` : ""}`);
  },

  // Topology graph
  topology: () => request<Topology>("/graph/topology"),
};
