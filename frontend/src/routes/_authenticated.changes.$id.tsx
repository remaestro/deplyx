import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { changeQuery } from "@/lib/queries";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";
import { ImpactAnalysis } from "@/components/impact-analysis";
import { ArrowLeft, Map, Pencil, X, Check, Play, Undo2, XCircle, Zap, Loader2 } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/changes/$id")({
  head: ({ params }) => ({ meta: [{ title: `Change ${params.id.slice(0, 8)} — Deplyx` }] }),
  component: ChangeDetail,
});

function ChangeDetail() {
  const { id } = Route.useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data: change, isLoading, error } = useQuery(changeQuery(id));
  const [tab, setTab] = useState<"overview" | "impact">("overview");
  const [editing, setEditing] = useState(false);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["changes"] });
  const approve = useMutation({ mutationFn: () => api.approveChange(id), onSuccess: () => { toast.success("Change approved"); invalidate(); } });
  const reject = useMutation({ mutationFn: () => api.rejectChange(id, "Rejected via UI"), onSuccess: () => { toast.error("Change rejected"); invalidate(); } });
  const execute = useMutation({ mutationFn: () => api.executeChange(id), onSuccess: () => { toast.success("Execution started"); invalidate(); } });
  const rollback = useMutation({ mutationFn: () => api.rollbackChange(id), onSuccess: () => { toast.info("Rollback enqueued"); invalidate(); } });
  const reanalyze = useMutation({
    mutationFn: () => api.reanalyzeChange(id),
    onSuccess: () => { toast.success("Re-analysis complete"); qc.invalidateQueries({ queryKey: ["changes", id] }); invalidate(); },
    onError: () => toast.error("Re-analysis failed"),
  });
  const submitAnalysis = useMutation({
    mutationFn: () => api.submitChange(id),
    onSuccess: () => { toast.success("Analysis started"); qc.invalidateQueries({ queryKey: ["changes", id] }); invalidate(); },
    onError: (err) => toast.error("Failed to start analysis"),
  });

  if (isLoading) {
    return <div className="p-10 text-sm text-muted-foreground">Loading change…</div>;
  }
  if (error || !change) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-10">
        <p className="text-sm text-muted-foreground">Change not found.</p>
        <Link to="/changes" className="text-sm text-primary hover:underline">Back to changes</Link>
      </div>
    );
  }

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-8 py-5">
        <div className="min-w-0 flex-1">
          <Link to="/changes" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-3" /> Back
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold tracking-tight">{change.title}</h1>
            <StatusBadge value={change.status} />
            {change.risk_level && <StatusBadge value={change.risk_level} />}
            <AnalysisPipeline stage={change.analysis_stage} />
          </div>
          <div className="mt-1 font-mono text-[11px] text-muted-foreground">{change.id}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {change.status === "Draft" && (
            <button onClick={() => submitAnalysis.mutate()} disabled={submitAnalysis.isPending} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
              <Zap className="size-3.5" /> {submitAnalysis.isPending ? "Analyzing…" : "Run Analysis"}
            </button>
          )}
          {(change.status === "Draft" || change.status === "Pending") && (
            <button onClick={() => setEditing(true)} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-accent">
              <Pencil className="size-3.5" /> Edit
            </button>
          )}
          <button
            onClick={() => nav({ to: "/graph-v3", search: { changeId: change.id } as never })}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-accent"
          >
            <Map className="size-3.5" /> Topology
          </button>
          {change.status === "Pending" && (
            <>
              <button onClick={() => toast.error("Change rejected")} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-destructive/15 hover:text-destructive-foreground">
                <XCircle className="size-3.5" /> Reject
              </button>
              <button onClick={() => toast.success("Change approved")} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">
                <Check className="size-3.5" /> Approve
              </button>
            </>
          )}
          {change.status === "Approved" && (
            <button onClick={() => toast.success("Execution started")} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">
              <Play className="size-3.5" /> Execute
            </button>
          )}
          {(change.status === "Completed" || change.status === "Executing") && (
            <button onClick={() => toast.info("Rollback enqueued")} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-accent">
              <Undo2 className="size-3.5" /> Rollback
            </button>
          )}
        </div>
      </header>

      <div className="flex gap-1 border-b border-border px-8">
        {(["overview", "impact"] as const).map((t) => (
          <button
            key={t} onClick={() => setTab(t)}
            className={`relative px-3 py-2.5 text-sm transition-colors ${
              tab === t ? "text-foreground" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t === "overview" ? "Overview" : "Impact Analysis"}
            {tab === t && <span className="absolute inset-x-3 -bottom-px h-px bg-primary" />}
          </button>
        ))}
      </div>

      <div className="p-8">
        {tab === "overview" ? (
          <div className="space-y-4">
            {change.reject_reason && (
              <div className="rounded-md border border-[color-mix(in_oklab,var(--destructive)_30%,transparent)] bg-[color-mix(in_oklab,var(--destructive)_12%,transparent)] p-3 text-sm">
                <span className="font-medium text-[color-mix(in_oklab,var(--destructive)_90%,white)]">Rejected — </span>
                {change.reject_reason}
              </div>
            )}

            <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
              <Field label="Description" wide>{change.description}</Field>
              <Field label="Type">{change.change_type}</Field>
              <Field label="Environment">{change.environment}</Field>
              <Field label="Action">{change.action}</Field>
              <Field label="Maintenance window" wide>
                <span className="font-mono text-xs">
                  {new Date(change.maintenance_window_start).toLocaleString()} → {new Date(change.maintenance_window_end).toLocaleString()}
                </span>
              </Field>
              <Field label="Target components" wide>
                <div className="flex flex-wrap gap-1.5">
                  {change.impacted_components.length ? change.impacted_components.map((c) => (
                    <span key={c.graph_node_id} className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px]">
                      {c.display_name}
                    </span>
                  )) : <span className="text-xs text-muted-foreground">No targets</span>}
                </div>
              </Field>
            </div>

            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <CodeBlock title="Execution plan" body={change.execution_plan} />
              <CodeBlock title="Rollback plan" body={change.rollback_plan} />
            </div>
          </div>
        ) : (
          <ImpactAnalysis change={change} onReanalyze={() => reanalyze.mutate()} />
        )}
      </div>

      {editing && <EditDrawer onClose={() => setEditing(false)} />}
    </>
  );
}

const PIPELINE = ["pending", "fetching_data", "computing_impact", "scoring_risk", "routing_workflow", "finalised"];

function AnalysisPipeline({ stage }: { stage: string }) {
  if (!stage || stage === "pending") return null;

  const idx = PIPELINE.indexOf(stage);
  const done = idx;
  const complete = done === PIPELINE.length - 1;
  const failed = stage === "failed";

  return (
    <div className="flex items-center gap-1.5">
      {PIPELINE.slice(1).map((s, i) => {
        const step = i + 1;
        const isDone = step < done || complete;
        const isCurrent = step === done && !complete;
        const active = isCurrent && !failed;

        return (
          <div key={s} className="flex items-center gap-1.5">
            <div
              className={`flex size-5 items-center justify-center rounded-full text-[9px] font-bold ${
                failed ? "bg-destructive/20 text-destructive" :
                isDone ? "bg-primary/20 text-primary" :
                active ? "bg-primary/20 text-primary" :
                "bg-muted text-muted-foreground"
              }`}
              title={s}
            >
              {failed ? "✕" : isDone ? "✓" : active ? <Loader2 className="size-3 animate-spin" /> : step}
            </div>
            <span className={`hidden text-[10px] sm:inline ${active ? "text-foreground" : "text-muted-foreground"}`}>
              {s.replace(/_/g, " ")}
            </span>
            {step < PIPELINE.length - 1 && <span className="h-px w-2 bg-border" />}
          </div>
        );
      })}
    </div>
  );
}

function Field({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className={`rounded-lg border border-border bg-card p-4 ${wide ? "lg:col-span-3" : ""}`}>
      <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function CodeBlock({ title, body }: { title: string; body: string }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{title}</div>
      <pre className="overflow-auto p-4 font-mono text-xs leading-relaxed text-foreground/90">{body || "—"}</pre>
    </div>
  );
}

function EditDrawer({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <aside className="flex w-full max-w-md flex-col border-l border-border bg-card">
        <header className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold">Edit change</h2>
          <button onClick={onClose} className="rounded p-1 hover:bg-accent"><X className="size-4" /></button>
        </header>
        <div className="flex-1 p-5 text-sm text-muted-foreground">
          Inline editor mock — wire to your API to update title, plans, and target components.
        </div>
        <footer className="border-t border-border px-5 py-3 text-right">
          <button onClick={() => { toast.success("Saved"); onClose(); }} className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">Save</button>
        </footer>
      </aside>
    </div>
  );
}
