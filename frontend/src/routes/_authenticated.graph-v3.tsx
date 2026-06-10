import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { topologyQuery, changeQuery, impactQuery } from "@/lib/queries";
import type { GraphNode } from "@/lib/types";
import { ArrowLeft, X } from "lucide-react";
import { z } from "zod";

const searchSchema = z.object({ changeId: z.string().optional() });

export const Route = createFileRoute("/_authenticated/graph-v3")({
  head: () => ({ meta: [{ title: "Topology — Deplyx" }] }),
  validateSearch: searchSchema,
  component: TopologyPage,
});

function isMainNode(n: { id: string }): boolean {
  if (n.id.startsWith("FTD-RULE-")) return false;
  return n.id.startsWith("DEV-") || n.id.startsWith("FTD-") || n.id.startsWith("SVC-") || n.id.startsWith("APP-");
}

function layerForNode(n: GraphNode): string {
  if (n.layer) return n.layer;
  if (n.id.startsWith("SVC-") || n.id.startsWith("APP-")) return "application";
  if (n.id.startsWith("FTD-")) return "security";
  const type = (n.properties.type ?? "").toLowerCase();
  if (type.includes("firewall") || type.includes("ftd") || type.includes("security")) return "security";
  return "network";
}

function shortLabel(n: GraphNode): string {
  const raw = n.display_name || n.label || n.id;
  const paren = raw.indexOf(" (");
  const name = paren > 0 ? raw.slice(0, paren) : raw;
  return name.length > 13 ? name.slice(0, 11) + "…" : name;
}

function shortType(n: GraphNode): string {
  const t = n.properties.type || "device";
  return t.length > 14 ? t.slice(0, 12) + "…" : t;
}

function computeLayout(nodes: GraphNode[]) {
  const layers = { security: 80, network: 260, application: 460 } as const;
  const groups: Record<string, GraphNode[]> = { security: [], network: [], application: [] };
  nodes.filter(isMainNode).forEach((n) => {
    const l = layerForNode(n);
    if (!groups[l]) groups[l] = [];
    groups[l].push(n);
  });
  const positions: Record<string, { x: number; y: number }> = {};
  const W = 1000;
  for (const [layer, list] of Object.entries(groups)) {
    if (!list.length) continue;
    const step = W / (list.length + 1);
    list.forEach((n, i) => {
      positions[n.id] = { x: step * (i + 1), y: layers[layer as keyof typeof layers] ?? 260 };
    });
  }
  return positions;
}

function TopologyPage() {
  const { changeId } = Route.useSearch();
  const { data: topology } = useQuery(topologyQuery());
  const { data: change } = useQuery({ ...changeQuery(changeId ?? ""), enabled: !!changeId });
  const { data: impactData } = useQuery({ ...impactQuery(changeId ?? ""), enabled: !!changeId });

  const [showCDP, setShowCDP] = useState(true);
  const [showProtects, setShowProtects] = useState(true);
  const [showRuns, setShowRuns] = useState(true);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [impactNode, setImpactNode] = useState<string | null>(null);

  const mainNodeIds = useMemo(() => new Set((topology?.nodes ?? []).filter(isMainNode).map((n) => n.id)), [topology]);
  const allNodes = topology?.nodes ?? [];
  const allEdges = topology?.edges ?? [];
  const nodes = allNodes.filter((n) => mainNodeIds.has(n.id));
  const edges = allEdges.filter((e) => {
    if (e.rel_type === "CONNECTED_TO" || e.rel_type === "PROTECTS") return mainNodeIds.has(e.source) && mainNodeIds.has(e.target);
    if (e.rel_type === "RUNS") return mainNodeIds.has(e.source) && mainNodeIds.has(e.target);
    return false;
  });
  const positions = useMemo(() => computeLayout(nodes), [nodes]);

  // Build rules per device lookup
  const rulesByDevice = useMemo(() => {
    const m = new Map<string, { id: string; name: string }[]>();
    allEdges.filter((e) => e.rel_type === "HAS_RULE").forEach((e) => {
      const ruleNode = allNodes.find((n) => n.id === e.target);
      if (!ruleNode) return;
      if (!m.has(e.source)) m.set(e.source, []);
      m.get(e.source)!.push({ id: ruleNode.id, name: ruleNode.display_name || ruleNode.label || ruleNode.id });
    });
    return m;
  }, [allEdges, allNodes]);

  // determine affected
  const affectedIds = useMemo(() => {
    const ids: Record<string, "direct" | "indirect"> = {};
    const impact = impactData?.impact;
    if (impact) {
      impact.directly_impacted.forEach((n) => { ids[n.id] = "direct"; });
      impact.indirectly_impacted.forEach((n) => { ids[n.id] = "indirect"; });
    } else if (change) {
      change.impacted_components.forEach((c) => { ids[c.graph_node_id] = c.impact_level; });
    } else if (impactNode) {
      ids[impactNode] = "direct";
      edges.forEach((e) => {
        if (e.source === impactNode) ids[e.target] ??= "indirect";
        if (e.target === impactNode) ids[e.source] ??= "indirect";
      });
    }
    return ids;
  }, [impactData, change, impactNode, edges]);

  const hasImpactMode = !!change || !!impactNode;

  return (
    <>
      <PageHeader
        title="Topology"
        description={change ? `Visualizing impact of change ${change.id.slice(0, 8)}` : "Network graph — security, network, application layers."}
        actions={
          change ? (
            <Link to="/changes/$id" params={{ id: change.id }} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-sm hover:bg-accent">
              <ArrowLeft className="size-3.5" /> Back to change
            </Link>
          ) : (
            <button
              onClick={() => setImpactNode(impactNode ? null : "")}
              className={`rounded-md border px-3 py-1.5 text-sm ${impactNode !== null ? "border-primary bg-primary/15 text-primary" : "border-border bg-card hover:bg-accent"}`}
            >
              {impactNode !== null ? "Cancel impact mode" : "Impact mode"}
            </button>
          )
        }
      />

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-8 py-2.5 text-xs">
        <Toggle on={showCDP} onChange={setShowCDP} color="var(--info)" label="CONNECTED_TO" />
        <Toggle on={showProtects} onChange={setShowProtects} color="var(--destructive)" label="PROTECTS" />
        <Toggle on={showRuns} onChange={setShowRuns} color="var(--success)" label="RUNS" />
        {hasImpactMode && (
          <div className="ml-auto flex items-center gap-3 text-[11px] text-muted-foreground">
            <Legend swatch="var(--destructive)" label="Direct" />
            <Legend swatch="var(--warning)" label="Indirect" />
          </div>
        )}
      </div>

      {/* Impact panel */}
      {change && impactData?.impact && (
        <div className="mx-8 mt-4 rounded-lg border border-border bg-card p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className={`flex size-9 shrink-0 items-center justify-center rounded-lg font-mono text-xs font-bold tracking-wide ${
                impactData.impact.max_criticality === "critical" || impactData.impact.max_criticality === "high"
                  ? "bg-[color-mix(in_oklab,var(--destructive)_18%,transparent)] text-[var(--destructive)]"
                  : impactData.impact.max_criticality === "medium"
                  ? "bg-[color-mix(in_oklab,var(--warning)_18%,transparent)] text-[var(--warning)]"
                  : "bg-[color-mix(in_oklab,var(--success)_18%,transparent)] text-[var(--success)]"
              }`}>{impactData.impact.max_criticality?.toUpperCase() || "—"}</div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-medium">{change.id.slice(0, 8)}</span>
                  <span className="text-xs text-muted-foreground">· {change.action} · {change.change_type}</span>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{impactData.impact.risk_assessment?.summary || change.description}</p>
              </div>
            </div>
            <Link to="/changes/$id" params={{ id: change.id }} className="shrink-0 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs hover:bg-accent">
              <ArrowLeft className="mr-1 inline size-3" /> Detail
            </Link>
          </div>
          <div className="mt-3 grid grid-cols-4 gap-2">
            <div className="rounded-md bg-muted/50 p-2 text-center">
              <div className="font-mono text-sm font-bold">{impactData.impact.directly_impacted?.length ?? 0}</div>
              <div className="text-[10px] text-muted-foreground">Direct</div>
            </div>
            <div className="rounded-md bg-muted/50 p-2 text-center">
              <div className="font-mono text-sm font-bold">{impactData.impact.indirectly_impacted?.length ?? 0}</div>
              <div className="text-[10px] text-muted-foreground">Indirect</div>
            </div>
            <div className="rounded-md bg-muted/50 p-2 text-center">
              <div className="font-mono text-sm font-bold">{impactData.impact.blast_radius?.critical_services_at_risk?.length ?? 0}</div>
              <div className="text-[10px] text-muted-foreground">Critical</div>
            </div>
            <div className="rounded-md bg-muted/50 p-2 text-center">
              <div className="font-mono text-sm font-bold" style={{ color: impactData.impact.blast_radius?.redundancy_available ? "var(--success)" : "var(--destructive)" }}>
                {impactData.impact.blast_radius?.redundancy_available ? "Yes" : "No"}
              </div>
              <div className="text-[10px] text-muted-foreground">Redundancy</div>
            </div>
          </div>
        </div>
      )}

      {change && !impactData?.impact && (
        <div className="mx-8 mt-4 flex items-center gap-3 rounded-md border border-[color-mix(in_oklab,var(--warning)_30%,transparent)] bg-[color-mix(in_oklab,var(--warning)_10%,transparent)] px-4 py-2.5 text-xs">
          <span className="font-mono">⚠ {change.id.slice(0, 8)}</span>
          <span>Direct: {change.impacted_components.filter((c) => c.impact_level === "direct").length}</span>
          <span>Indirect: {change.impacted_components.filter((c) => c.impact_level === "indirect").length}</span>
          <span className="text-muted-foreground">Criticality: {change.risk_level ?? "—"}</span>
        </div>
      )}

      <div className="p-8">
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <svg viewBox="0 0 1080 580" className="block h-[580px] w-full">
            {/* Layer bands */}
            <rect x="0" y="20" width="1080" height="130" fill="oklch(0.22 0.04 350 / 0.35)" />
            <rect x="0" y="180" width="1080" height="160" fill="oklch(0.22 0.06 220 / 0.35)" />
            <rect x="0" y="380" width="1080" height="180" fill="oklch(0.22 0.06 145 / 0.35)" />
            {[["Security", 38, "oklch(0.78 0.13 350)"], ["Network", 198, "oklch(0.78 0.13 220)"], ["Application", 398, "oklch(0.78 0.13 145)"]].map(([label, y, color]) => (
              <text key={label as string} x="14" y={y as number} fill={color as string} fontSize="10" fontFamily="JetBrains Mono" letterSpacing="0.15em">
                {(label as string).toUpperCase()}
              </text>
            ))}

            {/* Edges */}
            {edges.map((e) => {
              if (e.rel_type === "CONNECTED_TO" && !showCDP) return null;
              if (e.rel_type === "PROTECTS" && !showProtects) return null;
              if (e.rel_type === "RUNS" && !showRuns) return null;
              const s = positions[e.source]; const t = positions[e.target];
              if (!s || !t) return null;
              const stroke = e.rel_type === "CONNECTED_TO" ? "oklch(0.7 0.12 220)" : e.rel_type === "PROTECTS" ? "oklch(0.65 0.2 25)" : "oklch(0.7 0.16 145)";
              const dash = e.rel_type === "CONNECTED_TO" ? "0" : e.rel_type === "PROTECTS" ? "5 4" : "3 4";
              return <line key={e.id} x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke={stroke} strokeWidth="1.2" strokeDasharray={dash} opacity="0.7" />;
            })}

            {/* Nodes */}
            {nodes.map((n) => {
              const p = positions[n.id];
              if (!p) return null;
              const impact = affectedIds[n.id];
              const dimmed = hasImpactMode && !impact;
              const ring = impact === "direct" ? "var(--destructive)" : impact === "indirect" ? "var(--warning)" : "transparent";
              return (
                <g
                  key={n.id} transform={`translate(${p.x - 55},${p.y - 18})`}
                  className="cursor-pointer"
                  opacity={dimmed ? 0.35 : 1}
                  onClick={() => {
                    if (impactNode !== null && !change) setImpactNode(n.id);
                    else setSelected(n);
                  }}
                >
                  {impact && <rect x="-3" y="-3" width="116" height="42" rx="8" fill="none" stroke={ring} strokeWidth="2" />}
                  <rect width="110" height="36" rx="6" fill="oklch(0.22 0.01 270)" stroke="oklch(0.4 0.01 270)" strokeWidth="1" />
                  <text x="55" y="14" textAnchor="middle" fontSize="10" fontWeight="600" fill="oklch(0.96 0.005 270)">{shortLabel(n)}</text>
                  <text x="55" y="27" textAnchor="middle" fontSize="8" fontFamily="JetBrains Mono" fill="oklch(0.65 0.01 270)">
                    {shortType(n)}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {selected && (
        <aside className="fixed inset-y-0 right-0 z-40 flex w-[380px] flex-col border-l border-border bg-card shadow-2xl">
          <header className="flex items-start justify-between border-b border-border px-5 py-3">
            <div>
              <h2 className="text-sm font-semibold">{shortLabel(selected)}</h2>
              <p className="font-mono text-[11px] text-muted-foreground">{selected.id}</p>
            </div>
            <button onClick={() => setSelected(null)} className="rounded p-1 hover:bg-accent"><X className="size-4" /></button>
          </header>
          <div className="flex-1 space-y-3 overflow-y-auto p-5 text-sm">
            <Pair k="Label" v={selected.label} />
            <Pair k="Layer" v={selected.layer || (selected.id.startsWith("FTD-") ? "security" : selected.id.startsWith("SVC-") || selected.id.startsWith("APP-") ? "application" : "network")} />
            {Object.entries(selected.properties).filter(([k]) => k !== "type" && k !== "role").map(([k, v]) => v ? <Pair key={k} k={k} v={String(v)} /> : null)}
            <div>
              <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Relations</div>
              <div className="space-y-1">
                {edges.filter((e) => e.source === selected.id || e.target === selected.id).map((e) => (
                  <div key={e.id} className="rounded border border-border bg-muted/40 px-2 py-1 font-mono text-[11px]">
                    {e.source === selected.id ? "→ " : "← "} {e.rel_type} {e.source === selected.id ? e.target : e.source}
                  </div>
                ))}
              </div>
            </div>
            {/* Rules for firewalls */}
            {rulesByDevice.has(selected.id) && (
              <div>
                <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Rules ({rulesByDevice.get(selected.id)!.length})
                </div>
                <div className="space-y-1">
                  {rulesByDevice.get(selected.id)!.map((r) => (
                    <div key={r.id} className="rounded border border-border bg-muted/40 px-2 py-1 font-mono text-[11px]">
                      {r.name}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </aside>
      )}
    </>
  );
}

function Toggle({ on, onChange, color, label }: { on: boolean; onChange: (v: boolean) => void; color: string; label: string }) {
  return (
    <button
      onClick={() => onChange(!on)}
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 transition ${on ? "border-border bg-muted" : "border-border bg-card opacity-50"}`}
    >
      <span className="size-2 rounded-full" style={{ background: color }} />
      <span className="font-mono">{label}</span>
    </button>
  );
}
function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="size-2 rounded-full" style={{ background: swatch }} /> {label}
    </span>
  );
}
function Pair({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[100px_1fr] gap-2">
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{k}</span>
      <span className="font-mono text-[12px]">{v}</span>
    </div>
  );
}
