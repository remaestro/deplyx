import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { connectorsQuery } from "@/lib/queries";
import { api } from "@/lib/api";
import type { Connector } from "@/lib/types";
import { useSyncContext } from "@/lib/sync-context";
import { cn } from "@/lib/utils";
import { Plus, RefreshCw, Trash2, ScrollText, X, Radar, Loader2 } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/connectors")({
  head: () => ({ meta: [{ title: "Connectors — Deplyx" }] }),
  component: ConnectorsPage,
});

const TYPES = [
  "paloalto", "fortinet", "cisco", "cisco-ftd", "cisco-nxos", "cisco-router", "cisco-wlc",
  "juniper", "checkpoint", "aruba-switch", "aruba-ap", "vyos", "strongswan", "snort",
  "openldap", "nginx", "postgres", "redis", "elasticsearch", "grafana", "prometheus",
];

function ConnectorsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"connectors" | "discovery">("connectors");
  const { data: items = [], isLoading, error } = useQuery(connectorsQuery());
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [typeFilter, setTypeFilter] = useState("");
  const { syncingIds, startSync, finishSync, startBatch } = useSyncContext();

  const filtered = items.filter((c) => !typeFilter || c.connector_type === typeFilter);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["connectors"] });
  const syncMut = useMutation({
    mutationFn: async (id: number) => {
      startSync(id);
      try {
        return await api.syncConnector(id);
      } finally {
        finishSync(id);
      }
    },
    onSuccess: () => { toast.success("Sync complete"); invalidate(); },
    onError: () => toast.error("Sync failed"),
  });
  const deleteMut = useMutation({
    mutationFn: (id: number) => api.deleteConnector(id),
    onSuccess: () => { toast.success("Connector deleted"); invalidate(); },
  });
  const createMut = useMutation({
    mutationFn: (c: Partial<Connector>) => api.createConnector(c),
    onSuccess: () => { toast.success("Connector created"); invalidate(); setDrawerOpen(false); },
  });
  const syncOne = (id: number) => syncMut.mutate(id);
  const syncAll = () => {
    const ids = items.map((c) => c.id);
    startBatch(ids);
    ids.forEach((id) => syncMut.mutate(id));
  };
  const del = (id: number) => deleteMut.mutate(id);
  const isSyncing = syncingIds.size > 0;

  return (
    <>
      <PageHeader
        title="Connectors"
        description={isLoading ? "Loading…" : `${items.length} connectors · ${items.filter((c) => c.status === "active").length} active`}
        actions={
          <>
            <button onClick={syncAll} disabled={isSyncing} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50 disabled:pointer-events-none">
              <RefreshCw className={cn("size-3.5", isSyncing && "animate-spin")} /> Sync{isSyncing ? `ing (${syncingIds.size})` : " all"}
            </button>
            <button onClick={() => setDrawerOpen(true)} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">
              <Plus className="size-3.5" /> Add connector
            </button>
          </>
        }
      />

      <div className="flex gap-1 border-b border-border px-8">
        {(["connectors", "discovery"] as const).map((t) => (
          <button
            key={t} onClick={() => setTab(t)}
            className={`relative px-3 py-2.5 text-sm capitalize transition-colors ${tab === t ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
          >
            {t}
            {tab === t && <span className="absolute inset-x-3 -bottom-px h-px bg-primary" />}
          </button>
        ))}
      </div>

      {tab === "connectors" ? (
        <div className="space-y-3 p-8">
          <select
            value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
            className="rounded-md border border-input bg-input/40 px-2 py-1.5 text-sm"
          >
            <option value="">All types</option>
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading connectors…</p>
          ) : error ? (
            <p className="text-sm text-destructive-foreground">Failed to load connectors.</p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">No connectors yet. Click <em>Add connector</em> to configure one.</p>
          ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((c) => (
              <div key={c.id} className={cn("group rounded-lg border bg-card p-4 transition", syncingIds.has(c.id) ? "border-primary/60" : "border-border hover:border-primary/40")}>
                <div className="mb-3 flex items-start justify-between">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {syncingIds.has(c.id) ? (
                        <Loader2 className="size-3.5 animate-spin text-primary" />
                      ) : (
                        <span className={`size-1.5 rounded-full ${c.status === "active" ? "bg-success animate-pulse" : c.status === "error" ? "bg-destructive" : "bg-muted-foreground"}`} />
                      )}
                      <h3 className="truncate text-sm font-medium">{c.name}</h3>
                    </div>
                    <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{c.connector_type}</div>
                  </div>
                  {syncingIds.has(c.id) ? (
                    <span className="text-[10px] font-medium text-primary">Syncing…</span>
                  ) : (
                    <StatusBadge value={c.status} />
                  )}
                </div>
                <div className="space-y-1 text-[11px] text-muted-foreground">
                  <div>Sync mode: <span className="text-foreground/80">{c.sync_mode}</span></div>
                  <div>Interval: <span className="text-foreground/80">{c.sync_interval_minutes || "—"}m</span></div>
                  <div>Last sync: <span className="text-foreground/80">{c.last_sync_at ? new Date(c.last_sync_at).toISOString().replace("T", " ").slice(0, 19) + " UTC" : "never"}</span></div>
                  {c.last_error && !syncingIds.has(c.id) && <div className="text-destructive-foreground/80">⚠ {c.last_error}</div>}
                </div>
                <div className="mt-3 flex gap-1.5">
                  <button onClick={() => syncOne(c.id)} disabled={syncingIds.has(c.id)} className="inline-flex flex-1 items-center justify-center gap-1 rounded-md border border-border bg-background py-1.5 text-xs hover:bg-accent disabled:opacity-40 disabled:pointer-events-none">
                    {syncingIds.has(c.id) ? <Loader2 className="size-3 animate-spin" /> : <RefreshCw className="size-3" />} Sync
                  </button>
                  <button onClick={() => toast.info("History panel — not yet implemented")} className="inline-flex items-center justify-center rounded-md border border-border bg-background p-1.5 text-xs hover:bg-accent">
                    <ScrollText className="size-3.5" />
                  </button>
                  <button onClick={() => del(c.id)} className="inline-flex items-center justify-center rounded-md border border-border bg-background p-1.5 text-xs hover:bg-destructive/20 hover:text-destructive-foreground">
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
          )}
        </div>
      ) : (
        <DiscoveryPanel />
      )}

      {drawerOpen && <AddDrawer onClose={() => setDrawerOpen(false)} onCreate={(c) => createMut.mutate(c)} />}
    </>
  );
}

function DiscoveryPanel() {
  const [targets, setTargets] = useState("");
  const [sessions, setSessions] = useState<{ id: number; name: string; status: string; targets: number; results: { host: string; reachable: boolean; suggested: string }[] }[]>([]);

  const start = () => {
    const id = sessions.length + 1;
    setSessions((s) => [{ id, name: `Session ${id}`, status: "running", targets: targets.split(",").length, results: [] }, ...s]);
    toast.success("Discovery started");
    setTimeout(() => {
      setSessions((s) => s.map((x) => x.id === id ? { ...x, status: "completed", results: [
        { host: targets.split(",")[0]?.trim(), reachable: true, suggested: "cisco" },
      ]} : x));
    }, 1500);
  };

  return (
    <div className="space-y-4 p-8">
      <div className="rounded-lg border border-border bg-card p-5">
        <div className="mb-3 flex items-center gap-2">
          <Radar className="size-4 text-primary" />
          <h3 className="text-sm font-medium">Start a discovery</h3>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]">
          <input
            value={targets} onChange={(e) => setTargets(e.target.value)}
            placeholder="IPs or CIDRs, comma-separated"
            className="w-full rounded-md border border-input bg-input/40 px-3 py-2 text-sm outline-none focus:border-ring"
          />
          <button onClick={start} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90">
            Start discovery
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {sessions.map((s) => (
          <div key={s.id} className="rounded-lg border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{s.name}</span>
                <StatusBadge value={s.status === "completed" ? "active" : s.status === "running" ? "Analyzing" : "inactive"} />
              </div>
              <div className="text-[11px] text-muted-foreground">{s.targets} targets · {s.results.length} results</div>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2 font-medium">Host</th>
                  <th className="px-2 py-2 font-medium">Reachable</th>
                  <th className="px-2 py-2 font-medium">Suggested type</th>
                  <th className="px-2 py-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {s.results.map((r) => (
                  <tr key={r.host} className="border-t border-border/60">
                    <td className="px-4 py-2 font-mono text-xs">{r.host}</td>
                    <td className="px-2 py-2"><StatusBadge value={r.reachable ? "active" : "error"} /></td>
                    <td className="px-2 py-2 font-mono text-xs">{r.suggested || "—"}</td>
                    <td className="px-2 py-2 text-right">
                      {r.reachable && r.suggested && (
                        <button onClick={() => toast.success(`Bootstrapped ${r.suggested}`)} className="rounded-md border border-border bg-background px-2.5 py-1 text-xs hover:bg-accent">
                          Bootstrap
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}

function AddDrawer({ onClose, onCreate }: { onClose: () => void; onCreate: (c: Partial<Connector>) => void }) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({ name: "", type: "cisco", host: "", username: "", password: "" });

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <aside className="flex w-full max-w-md flex-col border-l border-border bg-card">
        <header className="flex items-center justify-between border-b border-border px-5 py-3">
          <div>
            <h2 className="text-sm font-semibold">Add connector</h2>
            <p className="text-[11px] text-muted-foreground">Step {step + 1} of 2</p>
          </div>
          <button onClick={onClose} className="rounded p-1 hover:bg-accent"><X className="size-4" /></button>
        </header>
        <div className="flex-1 space-y-3 p-5 text-sm">
          {step === 0 ? (
            <>
              <label className="block">
                <span className="mb-1 block text-[11px] font-medium text-muted-foreground">Type</span>
                <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="w-full rounded-md border border-input bg-input/40 px-2.5 py-1.5 text-sm">
                  {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-[11px] font-medium text-muted-foreground">Name</span>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="w-full rounded-md border border-input bg-input/40 px-2.5 py-1.5 text-sm" />
              </label>
            </>
          ) : (
            <>
              <label className="block">
                <span className="mb-1 block text-[11px] font-medium text-muted-foreground">Host</span>
                <input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} placeholder="10.0.0.1" className="w-full rounded-md border border-input bg-input/40 px-2.5 py-1.5 text-sm" />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="mb-1 block text-[11px] font-medium text-muted-foreground">Username</span>
                  <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="w-full rounded-md border border-input bg-input/40 px-2.5 py-1.5 text-sm" />
                </label>
                <label className="block">
                  <span className="mb-1 block text-[11px] font-medium text-muted-foreground">Password / Token</span>
                  <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="w-full rounded-md border border-input bg-input/40 px-2.5 py-1.5 text-sm" />
                </label>
              </div>
            </>
          )}
        </div>
        <footer className="flex items-center justify-between border-t border-border px-5 py-3">
          <button onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0} className="text-sm text-muted-foreground hover:text-foreground disabled:opacity-40">Back</button>
          {step === 0 ? (
            <button onClick={() => setStep(1)} className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">Next</button>
          ) : (
            <button
              onClick={() => onCreate({
                name: form.name || "New connector", connector_type: form.type,
                sync_mode: "on-demand", sync_interval_minutes: 60,
              })}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
            >Create</button>
          )}
        </footer>
      </aside>
    </div>
  );
}
