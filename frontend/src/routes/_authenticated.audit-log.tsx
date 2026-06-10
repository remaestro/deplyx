import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { auditQuery } from "@/lib/queries";
import { Download, Search } from "lucide-react";

export const Route = createFileRoute("/_authenticated/audit-log")({
  head: () => ({ meta: [{ title: "Audit log — Deplyx" }] }),
  component: AuditLogPage,
});

const ACTION_COLOR: Record<string, string> = {
  created: "var(--info)",
  submitted: "var(--info)",
  approved: "var(--success)",
  rejected: "var(--destructive)",
  executed: "var(--primary)",
  rolled_back: "var(--destructive)",
  deleted: "var(--destructive)",
  updated: "var(--warning)",
  viewed: "var(--muted-foreground)",
  login: "var(--muted-foreground)",
  policy_triggered: "var(--warning)",
};

function AuditLogPage() {
  const [q, setQ] = useState("");
  const [action, setAction] = useState("");
  const [range, setRange] = useState("All");
  const { data: entries = [], isLoading, error } = useQuery(auditQuery({ range, action: action || undefined }));

  const filtered = useMemo(() => entries.filter((a) =>
    (!q || JSON.stringify(a).toLowerCase().includes(q.toLowerCase())) &&
    (!action || a.action === action)
  ), [q, action, entries]);

  const exp = (fmt: "json" | "csv") => {
    const blob = fmt === "json"
      ? new Blob([JSON.stringify(filtered, null, 2)], { type: "application/json" })
      : new Blob([
          ["id", "action", "user_id", "change_id", "timestamp"].join(",") + "\n" +
          filtered.map((a) => [a.id, a.action, a.user_id ?? "", a.change_id ?? "", a.timestamp].join(",")).join("\n"),
        ], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `audit-log.${fmt}`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <PageHeader
        title="Audit Log"
        description={`${filtered.length} entries`}
        actions={
          <div className="flex gap-1.5">
            <button onClick={() => exp("json")} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-accent">
              <Download className="size-3.5" /> JSON
            </button>
            <button onClick={() => exp("csv")} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-accent">
              <Download className="size-3.5" /> CSV
            </button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2 border-b border-border px-8 py-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Full-text search…" className="w-64 rounded-md border border-input bg-input/40 py-1.5 pl-8 pr-3 text-sm outline-none focus:border-ring" />
        </div>
        <select value={action} onChange={(e) => setAction(e.target.value)} className="rounded-md border border-input bg-input/40 px-2 py-1.5 text-sm">
          <option value="">All actions</option>
          {Object.keys(ACTION_COLOR).map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <div className="ml-auto flex rounded-md border border-border bg-card p-0.5">
          {["1h", "24h", "7d", "30d", "All"].map((r) => (
            <button
              key={r} onClick={() => setRange(r)}
              className={`rounded px-2.5 py-1 text-xs ${range === r ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >{r}</button>
          ))}
        </div>
      </div>

      <div className="p-8">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="text-sm text-destructive-foreground">Failed to load audit log.</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-muted-foreground">No audit entries.</p>
        ) : (
          <ol className="space-y-1.5">
            {filtered.map((a) => (
              <li key={a.id} className="group rounded-md border border-border bg-card transition hover:border-primary/40">
                <details className="px-4 py-2.5">
                  <summary className="flex cursor-pointer items-center gap-3 text-sm marker:hidden [&::-webkit-details-marker]:hidden">
                    <span className="size-2 rounded-full" style={{ background: ACTION_COLOR[a.action] ?? "var(--muted-foreground)" }} />
                    <span className="font-medium capitalize">{a.action.replace(/_/g, " ")}</span>
                    {a.change_id && <span className="font-mono text-[11px] text-muted-foreground">#{a.change_id.slice(0, 8)}</span>}
                    <span className="ml-auto text-[11px] text-muted-foreground">{new Date(a.timestamp).toISOString().replace("T", " ").slice(0, 19)} UTC</span>
                  </summary>
                  {a.details && (
                    <pre className="mt-3 overflow-auto rounded border border-border bg-background p-2 font-mono text-[11px]">{JSON.stringify(a.details, null, 2)}</pre>
                  )}
                </details>
              </li>
            ))}
          </ol>
        )}
      </div>
    </>
  );
}
