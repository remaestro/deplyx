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
import { Plus, RefreshCw, Trash2, ScrollText, X, Loader2 } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/connectors")({
  head: () => ({ meta: [{ title: "Connectors — Deplyx" }] }),
  component: ConnectorsPage,
});



function ConnectorsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"connectors" | "setup">("connectors");
  const { data: raw = [], isLoading, error } = useQuery(connectorsQuery());
  const { data: TYPES = [] } = useQuery({ queryKey: ["connector-types"], queryFn: () => api.listConnectorTypes() });
  const items: Connector[] = Array.isArray(raw) ? raw : [];
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
        {(["connectors", "setup"] as const).map((t) => (
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
        <QuickSetup />
      )}

      {drawerOpen && <AddDrawer onClose={() => setDrawerOpen(false)} onCreate={(c) => createMut.mutate(c)} />}
    </>
  );
}

function QuickSetup() {
  const qc = useQueryClient();
  const [ips, setIps] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [apiUsername, setApiUsername] = useState("");
  const [apiPassword, setApiPassword] = useState("");
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<{ host: string; status: string; type?: string; id?: number; error?: string }[]>([]);

  const generateMut = useMutation({
    mutationFn: async (host: string) => {
      const r = await api.generateProfile({
        host,
        username: username || undefined,
        password: password || undefined,
        api_username: apiUsername || undefined,
        api_password: apiPassword || undefined,

      });
      return { host, ...r };
    },
    onSuccess: (data) => {
      setResults((prev) => prev.map((r) =>
        r.host === data.host ? { ...r, status: data.status === "ok" ? "ok" : "error", type: data.connector?.connector_type, id: data.connector?.id, error: data.errors?.join("; ") } : r
      ));
    },
    onError: (err: Error, host) => {
      setResults((prev) => prev.map((r) =>
        r.host === host ? { ...r, status: "error", error: err.message } : r
      ));
    },
  });

  const start = async () => {
    const hosts = ips.split(",").map((s) => s.trim()).filter(Boolean);
    if (!hosts.length || !username || !password) {
      toast.error("IPs, SSH username, and SSH password are required");
      return;
    }
    setRunning(true);
    setResults(hosts.map((h) => ({ host: h, status: "running" })));
    for (const host of hosts) {
      await generateMut.mutateAsync(host);
    }
    setRunning(false);
    qc.invalidateQueries({ queryKey: ["connectors"] });
    toast.success(`${hosts.length} device(s) processed`);
  };

  return (
    <div className="space-y-4 p-8">
      <div className="rounded-lg border border-border bg-card p-5">
        <h3 className="mb-3 text-sm font-medium">Quick setup — scan &amp; create connectors</h3>
        <div className="grid grid-cols-1 gap-3">
          <input
            value={ips} onChange={(e) => setIps(e.target.value)}
            placeholder="IPs, comma-separated (e.g. 192.168.1.1, 10.0.0.1)"
            className="w-full rounded-md border border-input bg-input/40 px-3 py-2 text-sm outline-none focus:border-ring"
            disabled={running}
          />
          <div className="grid grid-cols-2 gap-3">
            <input
              value={username} onChange={(e) => setUsername(e.target.value)}
              placeholder="SSH username"
              className="w-full rounded-md border border-input bg-input/40 px-3 py-2 text-sm outline-none focus:border-ring"
              disabled={running}
            />
            <input
              value={password} onChange={(e) => setPassword(e.target.value)}
              type="password"
              placeholder="SSH password"
              className="w-full rounded-md border border-input bg-input/40 px-3 py-2 text-sm outline-none focus:border-ring"
              disabled={running}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <input
              value={apiUsername} onChange={(e) => setApiUsername(e.target.value)}
              placeholder="API username (optional)"
              className="w-full rounded-md border border-input bg-input/40 px-3 py-2 text-sm outline-none focus:border-ring"
              disabled={running}
            />
            <input
              value={apiPassword} onChange={(e) => setApiPassword(e.target.value)}
              type="password"
              placeholder="API password (optional)"
              className="w-full rounded-md border border-input bg-input/40 px-3 py-2 text-sm outline-none focus:border-ring"
              disabled={running}
            />
          </div>
          <button
            onClick={start}
            disabled={running}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {running ? <><Loader2 className="mr-1.5 inline size-3.5 animate-spin" /> Scanning…</> : "Scan & create connectors"}
          </button>
        </div>
      </div>

      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((r) => (
            <div key={r.host} className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-2.5">
              <div className="flex items-center gap-3">
                <span className="font-mono text-sm">{r.host}</span>
                {r.status === "running" && <Loader2 className="size-3.5 animate-spin text-primary" />}
                {r.status === "ok" && <StatusBadge value="active" />}
                {r.status === "error" && <StatusBadge value="error" />}
                {r.type && <span className="text-[11px] text-muted-foreground">{r.type}</span>}
              </div>
              <div className="text-xs text-muted-foreground">
                {r.status === "ok" && r.id && `Connector #${r.id} created`}
                {r.status === "error" && r.error && <span className="text-destructive">{r.error}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
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
