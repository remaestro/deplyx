import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { changesQuery } from "@/lib/queries";
import { api } from "@/lib/api";
import type { Change, ChangeStatus } from "@/lib/types";
import { Plus, Search, LayoutGrid, List, Columns3, X } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/changes/")({
  head: () => ({ meta: [{ title: "Changes — Deplyx" }] }),
  component: ChangesList,
});

type View = "table" | "card" | "kanban";

function ChangesList() {
  const qc = useQueryClient();
  const [view, setView] = useState<View>("table");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [envFilter, setEnvFilter] = useState<string>("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { data: items = [], isLoading, error } = useQuery(changesQuery());

  const createMut = useMutation({
    mutationFn: (input: Partial<Change>) => api.createChange(input),
    onSuccess: () => {
      toast.success("Change created as Draft");
      qc.invalidateQueries({ queryKey: ["changes"] });
      setDrawerOpen(false);
    },
    onError: () => toast.error("Failed to create change"),
  });

  const envs = useMemo(() => Array.from(new Set(items.map((c) => c.environment))), [items]);

  const filtered = items.filter((c) =>
    (!q || c.title.toLowerCase().includes(q.toLowerCase()) || c.id.includes(q)) &&
    (!statusFilter || c.status === statusFilter) &&
    (!envFilter || c.environment === envFilter)
  );

  return (
    <>
      <PageHeader
        title="Changes"
        description={isLoading ? "Loading…" : `${items.length} changes in pipeline`}
        actions={
          <button
            onClick={() => setDrawerOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            <Plus className="size-3.5" /> Create change
          </button>
        }
      />

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-8 py-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search title or id…"
            className="w-64 rounded-md border border-input bg-input/40 py-1.5 pl-8 pr-3 text-sm outline-none focus:border-ring"
          />
        </div>
        <select
          value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-md border border-input bg-input/40 px-2 py-1.5 text-sm"
        >
          <option value="">All statuses</option>
          {["Draft", "Pending", "Analyzing", "Approved", "Rejected", "Executing", "Completed", "RolledBack"].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={envFilter} onChange={(e) => setEnvFilter(e.target.value)}
          className="rounded-md border border-input bg-input/40 px-2 py-1.5 text-sm"
        >
          <option value="">All environments</option>
          {envs.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className="ml-auto flex rounded-md border border-border bg-card p-0.5">
          {([["table", List], ["card", LayoutGrid], ["kanban", Columns3]] as const).map(([v, Icon]) => (
            <button
              key={v} onClick={() => setView(v)}
              className={`rounded p-1.5 ${view === v ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              aria-label={v}
            >
              <Icon className="size-4" />
            </button>
          ))}
        </div>
      </div>

      <div className="p-8">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading changes…</p>
        ) : error ? (
          <p className="text-sm text-destructive-foreground">Failed to load changes.</p>
        ) : (
          <>
            {view === "table" && <TableView items={filtered} />}
            {view === "card" && <CardView items={filtered} />}
            {view === "kanban" && <KanbanView items={filtered} />}
          </>
        )}
      </div>

      {drawerOpen && (
        <CreateDrawer
          onClose={() => setDrawerOpen(false)}
          onCreate={(c) => createMut.mutate(c)}
        />
      )}
    </>
  );
}

function TableView({ items }: { items: Change[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground">
            <th className="px-4 py-2 font-medium">Title</th>
            <th className="px-2 py-2 font-medium">Type</th>
            <th className="px-2 py-2 font-medium">Env</th>
            <th className="px-2 py-2 font-medium">Risk</th>
            <th className="px-2 py-2 font-medium">Status</th>
            <th className="px-2 py-2 font-medium">Created</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id} className="border-t border-border/60 hover:bg-accent/40">
              <td className="px-4 py-2.5">
                <Link to="/changes/$id" params={{ id: c.id }} className="font-medium hover:text-primary">
                  {c.title}
                </Link>
                <div className="font-mono text-[10px] text-muted-foreground">{c.id.slice(0, 8)}</div>
              </td>
              <td className="px-2 py-2.5 text-xs text-muted-foreground">{c.change_type}</td>
              <td className="px-2 py-2.5 text-xs text-muted-foreground">{c.environment}</td>
              <td className="px-2 py-2.5">
                {c.risk_score != null ? (
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs">{c.risk_score}</span>
                    {c.risk_level && <StatusBadge value={c.risk_level} />}
                  </div>
                ) : <span className="text-xs text-muted-foreground">—</span>}
              </td>
              <td className="px-2 py-2.5"><StatusBadge value={c.status} /></td>
              <td className="px-2 py-2.5 text-xs text-muted-foreground">{new Date(c.created_at).toLocaleString()}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-muted-foreground">No changes match the current filters.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function CardView({ items }: { items: Change[] }) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {items.map((c) => (
        <Link
          key={c.id} to="/changes/$id" params={{ id: c.id }}
          className="group rounded-lg border border-border bg-card p-4 transition hover:border-primary/40"
        >
          <div className="mb-2 flex items-center justify-between">
            <StatusBadge value={c.status} />
            {c.risk_level && <StatusBadge value={c.risk_level} />}
          </div>
          <h3 className="text-sm font-medium leading-snug group-hover:text-primary">{c.title}</h3>
          <p className="mt-1.5 line-clamp-2 text-xs text-muted-foreground">{c.description}</p>
          <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>{c.change_type} · {c.environment}</span>
            <span className="font-mono">{c.id.slice(0, 8)}</span>
          </div>
        </Link>
      ))}
    </div>
  );
}

function KanbanView({ items }: { items: Change[] }) {
  const cols: ChangeStatus[] = ["Draft", "Pending", "Approved", "Executing", "Completed"];
  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {cols.map((col) => {
        const list = items.filter((i) => i.status === col);
        return (
          <div key={col} className="flex w-72 shrink-0 flex-col rounded-lg border border-border bg-card/50">
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <span className="text-xs font-medium">{col}</span>
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{list.length}</span>
            </div>
            <div className="space-y-2 p-2">
              {list.map((c) => (
                <Link
                  key={c.id} to="/changes/$id" params={{ id: c.id }}
                  className="block rounded-md border border-border bg-card p-3 text-sm transition hover:border-primary/40"
                >
                  <div className="mb-2 line-clamp-2 font-medium">{c.title}</div>
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>{c.environment}</span>
                    {c.risk_level && <StatusBadge value={c.risk_level} />}
                  </div>
                </Link>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CreateDrawer({ onClose, onCreate }: { onClose: () => void; onCreate: (c: Partial<Change>) => void }) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    title: "", change_type: "Firewall", action: "add_rule", environment: "prod",
    description: "", execution_plan: "", rollback_plan: "",
    maintenance_window_start: "", maintenance_window_end: "",
    target_components: "",
  });

  const submit = () => {
    onCreate({
      title: form.title || "Untitled change",
      change_type: form.change_type, environment: form.environment, action: form.action,
      description: form.description, execution_plan: form.execution_plan, rollback_plan: form.rollback_plan,
      maintenance_window_start: form.maintenance_window_start || new Date().toISOString(),
      maintenance_window_end: form.maintenance_window_end || new Date(Date.now() + 3600_000).toISOString(),
      impacted_components: form.target_components.split(",").map((t) => t.trim()).filter(Boolean).map((t) => ({
        graph_node_id: t, component_type: "Device", impact_level: "direct" as const, display_name: t,
      })),
    });
  };

  const labels = ["Basics", "Plans", "Window"];

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <aside className="flex w-full max-w-md flex-col border-l border-border bg-card">
        <header className="flex items-center justify-between border-b border-border px-5 py-3">
          <div>
            <h2 className="text-sm font-semibold">Create change</h2>
            <p className="text-[11px] text-muted-foreground">Step {step + 1} of 3 · {labels[step]}</p>
          </div>
          <button onClick={onClose} className="rounded p-1 hover:bg-accent"><X className="size-4" /></button>
        </header>

        <div className="flex gap-1 px-5 pt-3">
          {labels.map((_, i) => (
            <div key={i} className={`h-1 flex-1 rounded-full ${i <= step ? "bg-primary" : "bg-muted"}`} />
          ))}
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-5 text-sm">
          {step === 0 && (
            <>
              <Field label="Title">
                <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className={inputCls} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Type">
                  <select value={form.change_type} onChange={(e) => setForm({ ...form, change_type: e.target.value })} className={inputCls}>
                    {["Preventive", "Evolution", "Corrective", "Firewall", "Switch", "VLAN", "Port", "Rack", "CloudSG"].map((s) => <option key={s}>{s}</option>)}
                  </select>
                </Field>
                <Field label="Environment">
                  <select value={form.environment} onChange={(e) => setForm({ ...form, environment: e.target.value })} className={inputCls}>
                    {["prod", "pre-prod", "Prod", "Preprod", "DC1", "DC2"].map((s) => <option key={s}>{s}</option>)}
                  </select>
                </Field>
              </div>
              <Field label="Action">
                <input value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })} className={inputCls} />
              </Field>
              <Field label="Target components (comma-separated IDs)">
                <input value={form.target_components} onChange={(e) => setForm({ ...form, target_components: e.target.value })} placeholder="ftd-01, sw-core-1" className={inputCls} />
              </Field>
              <Field label="Description">
                <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={3} className={inputCls} />
              </Field>
            </>
          )}
          {step === 1 && (
            <>
              <Field label="Execution plan">
                <textarea value={form.execution_plan} onChange={(e) => setForm({ ...form, execution_plan: e.target.value })} rows={6} className={`${inputCls} font-mono`} />
              </Field>
              <Field label="Rollback plan">
                <textarea value={form.rollback_plan} onChange={(e) => setForm({ ...form, rollback_plan: e.target.value })} rows={6} className={`${inputCls} font-mono`} />
              </Field>
            </>
          )}
          {step === 2 && (
            <>
              <Field label="Maintenance window — start">
                <input type="datetime-local" value={form.maintenance_window_start} onChange={(e) => setForm({ ...form, maintenance_window_start: e.target.value })} className={inputCls} />
              </Field>
              <Field label="Maintenance window — end">
                <input type="datetime-local" value={form.maintenance_window_end} onChange={(e) => setForm({ ...form, maintenance_window_end: e.target.value })} className={inputCls} />
              </Field>
            </>
          )}
        </div>

        <footer className="flex items-center justify-between border-t border-border px-5 py-3">
          <button
            onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}
            className="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground disabled:opacity-40"
          >Back</button>
          {step < 2 ? (
            <button onClick={() => setStep(step + 1)} className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">Next</button>
          ) : (
            <button onClick={submit} className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">Create</button>
          )}
        </footer>
      </aside>
    </div>
  );
}

const inputCls = "w-full rounded-md border border-input bg-input/40 px-2.5 py-1.5 text-sm outline-none focus:border-ring";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}
