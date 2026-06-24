import { useState } from "react";
import type { Change, ImpactAnalysis, PreChangeValidation, AiRecommendation } from "@/lib/types";

import {
  Sparkles, RotateCw, ShieldAlert, CheckCircle2, XCircle, AlertTriangle,
  GitBranch, Activity, Users, Clock, ArrowRight, Radio, ChevronDown,
  ClipboardCheck, Route as RouteIcon, Gauge,
} from "lucide-react";
import { toast } from "sonner";

export function ImpactAnalysis({ change, onReanalyze }: { change: Change; onReanalyze?: () => void }) {
  const a = change.analysis;
  if (!a) {
    return <p className="text-sm text-muted-foreground">Analysis not available yet.</p>;
  }

  return (
    <div className="space-y-4">
      {/* Header strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-card px-4 py-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1 rounded-md bg-primary/15 px-2 py-1 text-primary">
            <Sparkles className="size-3" /> LLM + graph trace
          </span>
          <span className="text-muted-foreground">attempt {change.analysis_attempts} · stage {change.analysis_stage}</span>
        </div>
        <button
          onClick={() => { if (onReanalyze) onReanalyze(); else toast.success("Re-analysis enqueued"); }}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs hover:bg-accent"
        >
          <RotateCw className="size-3" /> Re-analyze
        </button>
      </div>

      {/* Row 0 — AI recommendation (senior reviewer verdict) */}
      {a.recommendation && <Recommendation rec={a.recommendation} />}

      {/* Row 1 — blast radius + risk waterfall */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <BlastRadius change={change} />
        </div>
        <PredictedIncidents items={a.risk_factors} />
      </div>

      {/* Row 2 — live pre-change validations + path before/after */}
      {a.pre_change_validation?.supported && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <PreChangeChecks v={a.pre_change_validation} />
          <PathComparison v={a.pre_change_validation} />
        </div>
      )}

      {/* Row 3 — services */}
      <Services services={a.services ?? []} />

    </div>
  );
}

/* -------------------- Blast radius -------------------- */

function BlastRadius({ change }: { change: Change }) {
  const isMain = (id: string) => {
    if (id.startsWith("FTD-RULE-")) return false;
    return id.startsWith("DEV-") || id.startsWith("FTD-") || id.startsWith("SVC-") || id.startsWith("APP-");
  };
  const direct = change.impacted_components.filter((c) => c.impact_level === "direct" && isMain(c.graph_node_id));
  const indirect = change.impacted_components.filter((c) => c.impact_level === "indirect" && isMain(c.graph_node_id));
  const hidden = change.impacted_components.length - direct.length - indirect.length;
  const cx = 220, cy = 150;

  return (
    <Card title="Blast radius" icon={<Radio className="size-3.5" />} subtitle={`${direct.length} direct · ${indirect.length} downstream${hidden > 0 ? ` · ${hidden} children` : ""}`}>
      <div className="relative">
        <svg viewBox="0 0 440 300" className="h-[280px] w-full">
          {/* concentric rings */}
          {[120, 80, 40].map((r) => (
            <circle key={r} cx={cx} cy={cy} r={r}
              className="fill-none stroke-border" strokeDasharray="3 4" />
          ))}
          {/* edges */}
          {direct.map((d, i) => {
            const angle = (i / Math.max(direct.length, 1)) * Math.PI * 2 - Math.PI / 2;
            const x = cx + Math.cos(angle) * 80;
            const y = cy + Math.sin(angle) * 80;
            return (
              <g key={d.graph_node_id}>
                <line x1={cx} y1={cy} x2={x} y2={y}
                  className="stroke-primary/60" strokeWidth={1.5} />
                <circle cx={x} cy={y} r={9} className="fill-primary" />
                <text x={x} y={y + 22} textAnchor="middle" className="fill-foreground text-[9px] font-medium">
                  {d.display_name}
                </text>
              </g>
            );
          })}
          {indirect.map((d, i) => {
            const angle = (i / Math.max(indirect.length, 1)) * Math.PI * 2;
            const x = cx + Math.cos(angle) * 120;
            const y = cy + Math.sin(angle) * 120;
            return (
              <g key={d.graph_node_id}>
                <line x1={cx} y1={cy} x2={x} y2={y}
                  className="stroke-muted-foreground/40" strokeWidth={1} strokeDasharray="2 3" />
                <circle cx={x} cy={y} r={6} className="fill-muted-foreground/60" />
                <text x={x} y={y - 10} textAnchor="middle" className="fill-muted-foreground text-[9px]">
                  {d.display_name}
                </text>
              </g>
            );
          })}
          {/* epicenter */}
          <circle cx={cx} cy={cy} r={14} className="fill-destructive" />
          <circle cx={cx} cy={cy} r={14} className="fill-none stroke-destructive/60" strokeWidth={2}>
            <animate attributeName="r" values="14;26;14" dur="2.4s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.6;0;0.6" dur="2.4s" repeatCount="indefinite" />
          </circle>
          <text x={cx} y={cy + 4} textAnchor="middle" className="fill-destructive-foreground text-[9px] font-bold">CHG</text>
        </svg>
        <div className="absolute right-2 top-2 flex flex-col gap-1 text-[10px]">
          <Legend color="bg-destructive" label="Epicenter" />
          <Legend color="bg-primary" label="Ring 1 — direct" />
          <Legend color="bg-muted-foreground/60" label="Ring 2 — downstream" />
          {hidden > 0 && <span className="mt-1 text-muted-foreground/60">+{hidden} child nodes</span>}
        </div>
      </div>
    </Card>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5 rounded-md bg-card/80 px-1.5 py-0.5 backdrop-blur">
      <span className={`size-2 rounded-full ${color}`} />
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}

/* -------------------- Predicted incidents -------------------- */

const SEV_STYLE = {
  blocker: { dot: "bg-destructive", text: "text-destructive", chip: "bg-destructive/15 text-destructive border-destructive/30", label: "Blocker", Icon: XCircle },
  warning: { dot: "bg-warning",     text: "text-warning",     chip: "bg-warning/15 text-warning border-warning/30",         label: "Warning", Icon: AlertTriangle },
  info:    { dot: "bg-muted-foreground", text: "text-muted-foreground", chip: "bg-muted text-muted-foreground border-border", label: "Side-effect", Icon: Activity },
} as const;

const PROBA_STYLE = {
  high:   "bg-destructive/15 text-destructive border-destructive/30",
  medium: "bg-warning/15 text-warning border-warning/30",
  low:    "bg-success/15 text-success border-success/30",
} as const;

function PredictedIncidents({ items }: { items: ImpactAnalysis["risk_factors"] }) {
  const [open, setOpen] = useState<string | null>(items[0]?.label ?? null);
  const counts = items.reduce<Record<string, number>>((acc, i) => ({ ...acc, [i.severity]: (acc[i.severity] ?? 0) + 1 }), {});
  const blockers = counts.blocker ?? 0;

  return (
    <Card title="Predicted incidents" icon={<ShieldAlert className="size-3.5" />}
      subtitle={
        <span className="flex items-center gap-1.5">
          {(["blocker", "warning", "info"] as const).map((s) => counts[s] ? (
            <span key={s} className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] ${SEV_STYLE[s].chip}`}>
              <span className={`size-1.5 rounded-full ${SEV_STYLE[s].dot}`} />
              {counts[s]} {SEV_STYLE[s].label.toLowerCase()}
            </span>
          ) : null)}
        </span>
      }
    >
      {blockers > 0 && (
        <div className="mb-2 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-2.5 py-1.5 text-[11px] text-destructive">
          <XCircle className="mt-0.5 size-3.5 shrink-0" />
          <span><strong>{blockers} blocker</strong> must be resolved before this change can be approved.</span>
        </div>
      )}

      <div className="space-y-1.5">
        {items.map((f) => {
          const sev = SEV_STYLE[f.severity];
          const isOpen = open === f.label;
          return (
            <div key={f.label} className="rounded-md border border-border bg-background/40">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : f.label)}
                className="flex w-full items-start gap-2 px-2.5 py-2 text-left transition hover:bg-accent/50"
                aria-expanded={isOpen}
              >
                <sev.Icon className={`mt-0.5 size-3.5 shrink-0 ${sev.text}`} />
                <span className="flex-1 text-[12px] leading-snug">{f.label}</span>
                {f.probability && (
                  <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wider ${PROBA_STYLE[f.probability]}`} title="Probability of occurrence">
                    P·{f.probability}
                  </span>
                )}
                <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wider ${sev.chip}`}>{sev.label}</span>
                <ChevronDown className={`mt-0.5 size-3 shrink-0 text-muted-foreground transition-transform ${isOpen ? "" : "-rotate-90"}`} />
              </button>
              {isOpen && (
                <div className="space-y-2 border-t border-border px-3 py-2.5 text-[11px]">
                  {f.policy && (
                    <div className="flex items-center gap-1.5">
                      <span className="text-[9px] uppercase tracking-wider text-muted-foreground">detector</span>
                      <span className="font-mono text-[10px]">{f.policy}</span>
                    </div>
                  )}
                  {f.reason && <p className="text-foreground/80 leading-relaxed">{f.reason}</p>}
                  {f.evidence && f.evidence.length > 0 && (
                    <div>
                      <div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">Evidence</div>
                      <ul className="space-y-0.5">
                        {f.evidence.map((e, i) => (
                          <li key={i} className="font-mono text-[10px] text-muted-foreground before:mr-1.5 before:text-foreground/40 before:content-['›']">{e}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

/* -------------------- Config diff & conflicts -------------------- */

function ConfigDiff({ diff, conflicts }: { diff: ImpactAnalysis["config_diff"]; conflicts: ImpactAnalysis["conflicts"] }) {
  return (
    <Card title="Config diff & conflicts" icon={<GitBranch className="size-3.5" />} subtitle={`${conflicts.length} signal(s)`}>
      <pre className="overflow-auto rounded-md border border-border bg-background/60 p-3 font-mono text-[11px] leading-relaxed">
        {diff.map((line, i) => (
          <div key={i} className={
            line.kind === "add" ? "text-success" :
            line.kind === "remove" ? "text-destructive" :
            "text-muted-foreground"
          }>{line.text}</div>
        ))}
      </pre>
      <div className="mt-3 space-y-1.5">
        {conflicts.map((c, i) => {
          const Icon = c.severity === "error" ? XCircle : c.severity === "warn" ? AlertTriangle : CheckCircle2;
          const cls = c.severity === "error"
            ? "border-destructive/40 bg-destructive/10 text-destructive"
            : c.severity === "warn"
            ? "border-warning/40 bg-warning/10 text-warning"
            : "border-border bg-muted text-muted-foreground";
          return (
            <div key={i} className={`flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-xs ${cls}`}>
              <Icon className="mt-0.5 size-3.5 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="font-medium uppercase tracking-wider text-[10px]">{c.kind.replace("_", " ")}</div>
                <div className="text-foreground/90">{c.message}</div>
                {c.reference && <div className="mt-0.5 font-mono text-[10px] opacity-70">{c.reference}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

/* -------------------- Reachability proofs -------------------- */

function Reachability({ rows }: { rows: ImpactAnalysis["reachability"] }) {
  return (
    <Card title="Reachability proofs" icon={<ArrowRight className="size-3.5" />} subtitle={`${rows.length} flow(s)`}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <th className="py-1.5 font-medium">Source</th>
              <th className="py-1.5 font-medium">Destination</th>
              <th className="py-1.5 font-medium">Port</th>
              <th className="py-1.5 font-medium">Before</th>
              <th className="py-1.5 font-medium">After</th>
              <th className="py-1.5 font-medium">Path</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-border/60">
                <td className="py-1.5 font-mono">{r.src}</td>
                <td className="py-1.5 font-mono">{r.dst}</td>
                <td className="py-1.5 font-mono text-muted-foreground">{r.port}</td>
                <td className="py-1.5"><Verdict v={r.before} /></td>
                <td className="py-1.5"><Verdict v={r.after} /></td>
                <td className="py-1.5 font-mono text-[10px] text-muted-foreground">{r.path.join(" → ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Verdict({ v }: { v: "allow" | "deny" }) {
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] ${
      v === "allow" ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive"
    }`}>{v.toUpperCase()}</span>
  );
}

/* -------------------- Pre-flight checks -------------------- */

function Preflight({ items }: { items: ImpactAnalysis["preflight"] }) {
  const passed = items.filter((i) => i.status === "pass").length;
  return (
    <Card title="Pre-flight checks" icon={<CheckCircle2 className="size-3.5" />} subtitle={`${passed}/${items.length} passed`}
      action={
        <button onClick={() => toast.success("Re-running checks…")} className="text-[11px] text-primary hover:underline">
          Re-run
        </button>
      }
    >
      <div className="space-y-1.5">
        {items.map((c) => {
          const Icon = c.status === "pass" ? CheckCircle2 : c.status === "fail" ? XCircle : c.status === "warn" ? AlertTriangle : Clock;
          const color = c.status === "pass" ? "text-success" : c.status === "fail" ? "text-destructive" : c.status === "warn" ? "text-warning" : "text-muted-foreground";
          return (
            <div key={c.id} className="flex items-start gap-2 rounded-md border border-border bg-background/40 px-2.5 py-1.5 text-xs">
              <Icon className={`mt-0.5 size-3.5 shrink-0 ${color}`} />
              <div className="min-w-0 flex-1">
                <div className="font-medium">{c.label}</div>
                {c.detail && <div className="mt-0.5 text-[10px] text-muted-foreground">{c.detail}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

/* -------------------- AI recommendation -------------------- */

const VERDICT_STYLE = {
  approve: { cls: "border-success/40 bg-success/10 text-success", label: "APPROVE", Icon: CheckCircle2 },
  approve_with_validations: { cls: "border-warning/40 bg-warning/10 text-warning", label: "APPROVE WITH VALIDATIONS", Icon: AlertTriangle },
  reject: { cls: "border-destructive/40 bg-destructive/10 text-destructive", label: "REJECT", Icon: XCircle },
} as const;

function Recommendation({ rec }: { rec: AiRecommendation }) {
  const v = VERDICT_STYLE[rec.verdict] ?? VERDICT_STYLE.approve_with_validations;
  return (
    <div className={`rounded-md border px-4 py-3 ${v.cls}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <v.Icon className="size-4" />
          <span className="text-sm font-semibold tracking-wide">Recommendation: {v.label}</span>
        </div>
        {typeof rec.confidence === "number" && (
          <span className="inline-flex items-center gap-1.5 rounded-md bg-background/60 px-2 py-1 text-[11px] text-foreground">
            <Gauge className="size-3" /> Confidence {rec.confidence}%
          </span>
        )}
      </div>
      <div className="mt-2 grid grid-cols-1 gap-3 text-[12px] md:grid-cols-2">
        {rec.reasons && rec.reasons.length > 0 && (
          <div>
            <div className="mb-1 text-[9px] uppercase tracking-wider opacity-70">Reasons</div>
            <ul className="space-y-0.5 text-foreground/90">
              {rec.reasons.map((r, i) => (
                <li key={i} className="before:mr-1.5 before:content-['•']">{r}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="space-y-2">
          {rec.residual_risks && rec.residual_risks.length > 0 && (
            <div>
              <div className="mb-1 text-[9px] uppercase tracking-wider opacity-70">Residual risk</div>
              <ul className="space-y-0.5 text-foreground/80">
                {rec.residual_risks.map((r, i) => (
                  <li key={i} className="before:mr-1.5 before:content-['•']">{r}</li>
                ))}
              </ul>
            </div>
          )}
          {rec.required_validations && rec.required_validations.length > 0 && (
            <div>
              <div className="mb-1 text-[9px] uppercase tracking-wider opacity-70">Required validations at execution</div>
              <ul className="space-y-0.5 text-foreground/80">
                {rec.required_validations.map((r, i) => (
                  <li key={i} className="before:mr-1.5 before:content-['•']">{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* -------------------- Live pre-change validations -------------------- */

const CHECK_STYLE = {
  pass: { Icon: CheckCircle2, color: "text-success" },
  fail: { Icon: XCircle, color: "text-destructive" },
  warn: { Icon: AlertTriangle, color: "text-warning" },
  skip: { Icon: Clock, color: "text-muted-foreground" },
} as const;

function PreChangeChecks({ v }: { v: PreChangeValidation }) {
  const passed = v.checks.filter((c) => c.status === "pass").length;
  const failed = v.checks.filter((c) => c.status === "fail").length;
  return (
    <Card
      title="Pre-change validation (live)"
      icon={<ClipboardCheck className="size-3.5" />}
      subtitle={
        <span>
          {passed}/{v.checks.length} passed{failed > 0 ? ` · ${failed} failed` : ""}
          {v.device?.hostname ? ` · collected on ${v.device.hostname} via SSH` : ""}
        </span>
      }
    >
      <div className="space-y-1.5">
        {v.checks.map((c) => {
          const s = CHECK_STYLE[c.status] ?? CHECK_STYLE.skip;
          return (
            <div key={c.name} className="rounded-md border border-border bg-background/40 px-2.5 py-1.5 text-xs">
              <div className="flex items-start gap-2">
                <s.Icon className={`mt-0.5 size-3.5 shrink-0 ${s.color}`} />
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{c.label}</div>
                  {c.detail && <div className="mt-0.5 text-[10px] text-muted-foreground">{c.detail}</div>}
                  {c.evidence && c.evidence.filter(Boolean).length > 0 && (
                    <pre className="mt-1 overflow-auto rounded bg-background/60 px-2 py-1 font-mono text-[10px] text-muted-foreground">
                      {c.evidence.filter(Boolean).join("\n")}
                    </pre>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {v.evidence_collected && v.evidence_collected.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
          <span className="uppercase tracking-wider">Evidence:</span>
          {v.evidence_collected.map((e) => (
            <span key={e} className="rounded bg-muted px-1.5 py-0.5 font-mono">{e}</span>
          ))}
        </div>
      )}
    </Card>
  );
}

/* -------------------- Path before / after -------------------- */

function PathComparison({ v }: { v: PreChangeValidation }) {
  const pc = v.path_comparison;
  if (!pc) return null;
  return (
    <Card title="Path — current vs proposed" icon={<RouteIcon className="size-3.5" />}
      subtitle={pc.delta && (pc.delta.hop_count || pc.delta.rtt_ms)
        ? `Δ hops ${pc.delta.hop_count ?? "—"} · Δ RTT ${pc.delta.rtt_ms ?? "—"}`
        : undefined}
    >
      <div className="space-y-3">
        <PathRow label="Current" info={pc.current} tone="muted" />
        <PathRow label="Proposed" info={pc.proposed} tone="primary" />
        {v.route_table && (v.route_table.before || v.route_table.proposed) && (
          <div>
            <div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">Route table</div>
            <pre className="overflow-auto rounded-md border border-border bg-background/60 p-2 font-mono text-[10px] leading-relaxed">
              {v.route_table.before && <div className="text-destructive">- {v.route_table.before}</div>}
              {v.route_table.proposed && <div className="text-success">+ {v.route_table.proposed}</div>}
            </pre>
          </div>
        )}
      </div>
    </Card>
  );
}

function PathRow({ label, info, tone }: { label: string; info: NonNullable<PreChangeValidation["path_comparison"]>["current"]; tone: "muted" | "primary" }) {
  return (
    <div className="rounded-md border border-border bg-background/40 px-2.5 py-2">
      <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
        <span>{label}</span>
        <span className="flex items-center gap-2 font-mono normal-case">
          {info.hop_count != null && <span>{info.hop_count} hop{info.hop_count > 1 ? "s" : ""}</span>}
          {info.rtt_ms != null && <span>RTT {info.rtt_ms}ms</span>}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1 text-xs">
        {info.hops.map((h, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <ArrowRight className="size-3 text-muted-foreground" />}
            <span className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${
              tone === "primary" && i > 0 ? "bg-primary/15 text-primary" : "bg-muted text-foreground/90"
            }`}>{h}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/* -------------------- Services -------------------- */

function Services({ services }: { services: NonNullable<ImpactAnalysis["services"]> }) {
  if (services.length === 0) return null;
  return (
    <Card title="Impacted services" icon={<Users className="size-3.5" />}
      subtitle={`${services.length} owner(s) to notify`}
      action={
        <button onClick={() => toast.success("Notification sent to service owners")} className="rounded-md border border-border bg-background px-2.5 py-1 text-[11px] hover:bg-accent">
          Notify owners
        </button>
      }
    >
      <div className="overflow-hidden rounded-md border border-border">
        <table className="w-full text-xs">
          <thead className="bg-muted/40 text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Service</th>
              <th className="px-3 py-2 font-medium">Owner</th>
              <th className="px-3 py-2 font-medium">On-call</th>
              <th className="px-3 py-2 font-medium">SLA</th>
              <th className="px-3 py-2 font-medium">RPS</th>
              <th className="px-3 py-2 font-medium">Expected</th>
            </tr>
          </thead>
          <tbody>
            {services.map((s) => (
              <tr key={s.id} className="border-t border-border/60">
                <td className="px-3 py-2 font-medium">{s.name}</td>
                <td className="px-3 py-2 text-muted-foreground">{s.owner}</td>
                <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">{s.on_call}</td>
                <td className="px-3 py-2"><span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">{s.sla_tier}</span></td>
                <td className="px-3 py-2 font-mono">{s.rps.toLocaleString()}</td>
                <td className="px-3 py-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${
                    s.expected_disruption === "full" ? "bg-destructive/15 text-destructive" :
                    s.expected_disruption === "brief" ? "bg-warning/15 text-warning" :
                    "bg-success/15 text-success"
                  }`}>{s.expected_disruption}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* -------------------- Recent activity -------------------- */

function RecentActivity({ items }: { items: ImpactAnalysis["recent_activity"] }) {
  return (
    <Card title="Recent activity on blast radius" icon={<Activity className="size-3.5" />}
      subtitle={`${items.length} change(s) in last 14d`}
    >
      <ol className="relative space-y-2 border-l border-border pl-4">
        {items.map((a) => {
          const color = a.outcome === "ok" ? "bg-success" : a.outcome === "rollback" ? "bg-destructive" : a.outcome === "incident" ? "bg-destructive" : "bg-warning";
          return (
            <li key={a.id} className="relative">
              <span className={`absolute -left-[19px] top-1.5 size-2.5 rounded-full ring-2 ring-background ${color}`} />
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs">
                <div>
                  <span className="font-medium">{a.title}</span>
                  <span className="ml-2 font-mono text-[10px] text-muted-foreground">{a.node}</span>
                </div>
                <span className="font-mono text-[10px] text-muted-foreground">{new Date(a.at).toISOString().replace("T", " ").slice(0, 16)}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                <span className="font-mono">{a.change_id.slice(0, 12)}…</span>
                <span className={`rounded px-1 py-0.5 ${
                  a.outcome === "ok" ? "bg-success/15 text-success" :
                  a.outcome === "rollback" ? "bg-destructive/15 text-destructive" :
                  a.outcome === "incident" ? "bg-destructive/15 text-destructive" :
                  "bg-warning/15 text-warning"
                }`}>{a.outcome}</span>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

/* -------------------- Similar outcome + traffic -------------------- */

function SimilarOutcome({ stats, traffic }: { stats: ImpactAnalysis["similar"]; traffic: number[] }) {
  const maxT = Math.max(...traffic);
  const successPct = Math.round((stats.ok / stats.total) * 100);
  return (
    <Card title="Similar changes" icon={<Sparkles className="size-3.5" />}
      subtitle={`${stats.total} in last 90d · ${successPct}% clean`}
    >
      <div className="grid grid-cols-3 gap-2 text-center">
        <Stat label="Clean" value={stats.ok} accent="text-success" />
        <Stat label="Rolled back" value={stats.rollback} accent="text-destructive" />
        <Stat label="Partial" value={stats.partial} accent="text-warning" />
      </div>
      <div className="mt-3 rounded-md border border-border bg-muted/30 p-2 text-center text-xs">
        <span className="text-muted-foreground">Median execution </span>
        <span className="font-mono font-medium">{stats.median_exec_minutes} min</span>
      </div>
      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between text-[10px] text-muted-foreground">
          <span>Traffic on touched interface · last 24h</span>
          <span className="font-mono">peak {maxT} Mbps</span>
        </div>
        <svg viewBox="0 0 240 60" className="h-14 w-full">
          <polyline
            fill="none"
            className="stroke-primary"
            strokeWidth={1.5}
            points={traffic.map((v, i) => `${(i / (traffic.length - 1)) * 240},${60 - (v / maxT) * 55}`).join(" ")}
          />
          <polygon
            className="fill-primary/15"
            points={`0,60 ${traffic.map((v, i) => `${(i / (traffic.length - 1)) * 240},${60 - (v / maxT) * 55}`).join(" ")} 240,60`}
          />
        </svg>
      </div>
    </Card>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="rounded-md border border-border bg-background/40 p-2">
      <div className={`font-mono text-lg font-semibold ${accent}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  );
}

/* -------------------- Card primitive -------------------- */

function Card({ title, icon, subtitle, action, children }: {
  title: string; icon?: React.ReactNode;
  subtitle?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-1.5 text-xs font-medium">
          {icon && <span className="text-muted-foreground">{icon}</span>}
          {title}
          {subtitle && <span className="ml-1 text-[11px] font-normal text-muted-foreground">· {subtitle}</span>}
        </div>
        {action}
      </header>
      <div className="p-4">{children}</div>
    </div>
  );
}
