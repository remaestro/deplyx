import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { policiesQuery } from "@/lib/queries";
import { api } from "@/lib/api";
import type { Policy } from "@/lib/types";
import { Plus, Trash2, Clock, ShieldCheck, Ban, Search } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/policies")({
  head: () => ({ meta: [{ title: "Policies — Deplyx" }] }),
  component: PoliciesPage,
});

const ICON: Record<Policy["rule_type"], React.ComponentType<{ className?: string }>> = {
  time_restriction: Clock,
  double_validation: ShieldCheck,
  auto_block: Ban,
};

function PoliciesPage() {
  const qc = useQueryClient();
  const { data: items = [], isLoading, error } = useQuery(policiesQuery());
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const filtered = items.filter((p) =>
    (!q || p.name.toLowerCase().includes(q.toLowerCase())) &&
    (!typeFilter || p.rule_type === typeFilter)
  );

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => api.togglePolicy(id, enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["policies"] }),
  });
  const deleteMut = useMutation({
    mutationFn: (id: number) => api.deletePolicy(id),
    onSuccess: () => { toast.success("Policy deleted"); qc.invalidateQueries({ queryKey: ["policies"] }); },
  });
  const toggle = (p: Policy) => toggleMut.mutate({ id: p.id, enabled: !p.enabled });
  const del = (id: number) => deleteMut.mutate(id);

  return (
    <>
      <PageHeader
        title="Policies"
        description={`${items.length} policies · ${items.filter((p) => p.enabled).length} enabled`}
        actions={
          <button onClick={() => toast.info("Policy wizard — mocked")} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">
            <Plus className="size-3.5" /> New policy
          </button>
        }
      />

      <div className="flex flex-wrap items-center gap-2 border-b border-border px-8 py-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search policies…" className="w-64 rounded-md border border-input bg-input/40 py-1.5 pl-8 pr-3 text-sm outline-none focus:border-ring" />
        </div>
        <div className="flex gap-1">
          {(["", "time_restriction", "double_validation", "auto_block"] as const).map((t) => (
            <button
              key={t || "all"} onClick={() => setTypeFilter(t)}
              className={`rounded-md px-2.5 py-1 text-xs ${typeFilter === t ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >{t || "All"}</button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <p className="p-8 text-sm text-muted-foreground">Loading…</p>
      ) : error ? (
        <p className="p-8 text-sm text-destructive-foreground">Failed to load policies.</p>
      ) : filtered.length === 0 ? (
        <p className="p-8 text-sm text-muted-foreground">No policies yet.</p>
      ) : (
      <div className="grid grid-cols-1 gap-3 p-8 md:grid-cols-2">
        {filtered.map((p) => {
          const Icon = ICON[p.rule_type];
          return (
            <div key={p.id} className="rounded-lg border border-border bg-card p-4">
              <div className="mb-2 flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Icon className="size-4" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-medium">{p.name}</h3>
                    <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">{p.rule_type} · {p.action}</div>
                  </div>
                </div>
                <button
                  onClick={() => toggle(p)}
                  className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition ${p.enabled ? "bg-primary" : "bg-muted"}`}
                  aria-label={p.enabled ? "Disable" : "Enable"}
                >
                  <span className={`inline-block size-4 transform rounded-full bg-background transition ${p.enabled ? "translate-x-4" : "translate-x-0.5"}`} />
                </button>
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">{p.description}</p>
              <details className="mt-3">
                <summary className="cursor-pointer text-[11px] text-muted-foreground hover:text-foreground">Condition</summary>
                <pre className="mt-2 overflow-auto rounded border border-border bg-background p-2 font-mono text-[11px]">{JSON.stringify(p.condition, null, 2)}</pre>
              </details>
              <div className="mt-3 flex items-center justify-between">
                <button onClick={() => toast.info("Simulation panel — mocked")} className="rounded-md border border-border bg-background px-2.5 py-1 text-xs hover:bg-accent">Simulate</button>
                <button onClick={() => del(p.id)} className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/20 hover:text-destructive-foreground">
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
      )}
    </>
  );
}
