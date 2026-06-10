import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { kpisQuery, changesQuery, auditQuery } from "@/lib/queries";
import { Activity, CheckCircle2, Clock, AlertTriangle, Target, Cpu, ArrowUpRight } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis, Line, LineChart } from "recharts";

export const Route = createFileRoute("/_authenticated/")({
  head: () => ({ meta: [{ title: "Dashboard — Deplyx" }] }),
  component: Dashboard,
});

const sparkData = Array.from({ length: 14 }, (_, i) => ({ d: i, v: 22 + Math.round(Math.sin(i / 2) * 8 + Math.cos(i / 3) * 4) }));

function Dashboard() {
  const [range, setRange] = useState("7d");
  const { data: kpis } = useQuery(kpisQuery());
  const { data: changes = [] } = useQuery(changesQuery());
  const { data: rawAudit } = useQuery(auditQuery());
  const audit = Array.isArray(rawAudit) ? rawAudit : [];

  const kpiCards = [
    { key: "total_changes", label: "Total Changes", icon: Activity, value: kpis?.total_changes ?? "—", suffix: "", delta: "" },
    { key: "auto_approved_pct", label: "Auto-approved", icon: CheckCircle2, value: kpis?.auto_approved_pct ?? "—", suffix: "%", delta: "" },
    { key: "avg_validation_minutes", label: "Avg Validation", icon: Clock, value: kpis?.avg_validation_minutes ?? "—", suffix: " min", delta: "" },
    { key: "incidents_post_change_pct", label: "Post-change Incidents", icon: AlertTriangle, value: kpis?.incidents_post_change_pct ?? "—", suffix: "%", delta: "" },
    { key: "scoring_precision_pct", label: "Scoring Precision", icon: Target, value: kpis?.scoring_precision_pct ?? "—", suffix: "%", delta: "" },
    { key: "core_changes_detected_pct", label: "Core Detected", icon: Cpu, value: kpis?.core_changes_detected_pct ?? "—", suffix: "%", delta: "" },
  ];

  const riskDist = [
    { name: "Low", value: changes.filter((c) => c.risk_level === "low").length, color: "var(--success)" },
    { name: "Medium", value: changes.filter((c) => c.risk_level === "medium").length, color: "var(--warning)" },
    { name: "High", value: changes.filter((c) => c.risk_level === "high").length, color: "var(--destructive)" },
  ];
  const statusDist = ["Draft", "Pending", "Approved", "Executing", "Completed", "Rejected"].map((s) => ({
    name: s, count: changes.filter((c) => c.status === s).length,
  }));

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Pipeline health, risk distribution, and recent activity."
        actions={
          <div className="flex rounded-md border border-border bg-card p-0.5 text-xs">
            {["24h", "7d", "30d", "All"].map((t) => (
              <button
                key={t}
                onClick={() => setRange(t)}
                className={`rounded px-2.5 py-1 ${range === t ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                {t}
              </button>
            ))}
          </div>
        }
      />

      <div className="space-y-6 p-8">
        {/* KPIs */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {kpiCards.map((k) => (
            <div key={k.key} className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-start justify-between">
                <div className="flex size-7 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <k.icon className="size-3.5" />
                </div>
                <span className="text-[10px] font-medium text-success">{k.delta}</span>
              </div>
              <div className="mt-3 font-mono text-xl font-semibold tracking-tight">
                {k.value}<span className="text-sm text-muted-foreground">{k.suffix}</span>
              </div>
              <div className="text-[11px] text-muted-foreground">{k.label}</div>
              <div className="-mx-1 mt-2 h-8">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={sparkData}>
                    <Line type="monotone" dataKey="v" stroke="var(--primary)" strokeWidth={1.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          ))}
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div className="rounded-lg border border-border bg-card p-5 lg:col-span-1">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-medium">Risk distribution</h3>
              <span className="text-[10px] text-muted-foreground">last 7d</span>
            </div>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={riskDist} dataKey="value" innerRadius={42} outerRadius={62} strokeWidth={0}>
                    {riskDist.map((e) => <Cell key={e.name} fill={e.color} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 flex justify-around text-[11px]">
              {riskDist.map((r) => (
                <div key={r.name} className="flex items-center gap-1.5">
                  <span className="size-2 rounded-full" style={{ background: r.color }} />
                  <span className="text-muted-foreground">{r.name}</span>
                  <span className="font-mono">{r.value}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-5 lg:col-span-2">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-medium">Changes by status</h3>
              <span className="text-[10px] text-muted-foreground">current pipeline</span>
            </div>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={statusDist}>
                  <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                  <YAxis hide />
                  <Tooltip cursor={{ fill: "var(--accent)" }} contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", fontSize: 12 }} />
                  <Bar dataKey="count" fill="var(--primary)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Recent changes + activity */}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div className="rounded-lg border border-border bg-card lg:col-span-2">
            <div className="flex items-center justify-between border-b border-border px-5 py-3">
              <h3 className="text-sm font-medium">Recent changes</h3>
              <Link to="/changes" className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                View all <ArrowUpRight className="size-3" />
              </Link>
            </div>
            {changes.length === 0 ? (
              <p className="p-6 text-sm text-muted-foreground">No changes yet.</p>
            ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-5 py-2 font-medium">Title</th>
                  <th className="px-2 py-2 font-medium">Env</th>
                  <th className="px-2 py-2 font-medium">Risk</th>
                  <th className="px-2 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {changes.slice(0, 6).map((c) => (
                  <tr key={c.id} className="border-t border-border/60 hover:bg-accent/40">
                    <td className="px-5 py-2.5">
                      <Link to="/changes/$id" params={{ id: c.id }} className="hover:text-primary">
                        {c.title}
                      </Link>
                      <div className="font-mono text-[10px] text-muted-foreground">{c.id.slice(0, 8)}</div>
                    </td>
                    <td className="px-2 py-2.5 text-xs text-muted-foreground">{c.environment}</td>
                    <td className="px-2 py-2.5">
                      {c.risk_level ? <StatusBadge value={c.risk_level} /> : <span className="text-xs text-muted-foreground">—</span>}
                    </td>
                    <td className="px-2 py-2.5"><StatusBadge value={c.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            )}
          </div>

          <div className="rounded-lg border border-border bg-card">
            <div className="border-b border-border px-5 py-3">
              <h3 className="text-sm font-medium">Activity</h3>
            </div>
            {audit.length === 0 ? (
              <p className="p-5 text-sm text-muted-foreground">No activity yet.</p>
            ) : (
            <ol className="relative space-y-3 px-5 py-4">
              {audit.slice(0, 8).map((a) => (
                <li key={a.id} className="relative pl-5">
                  <span className="absolute left-0 top-1.5 size-2 rounded-full bg-primary/70 ring-4 ring-primary/10" />
                  <div className="text-sm">
                    <span className="font-medium capitalize">{a.action.replace(/_/g, " ")}</span>
                    {a.change_id && <span className="ml-1 font-mono text-[11px] text-muted-foreground">#{a.change_id.slice(0, 8)}</span>}
                  </div>
                  <div className="text-[11px] text-muted-foreground">{new Date(a.timestamp).toISOString().replace("T", " ").slice(0, 19)} UTC</div>
                </li>
              ))}
            </ol>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
