// Domain types — shared between frontend and backend DTOs.
// The backend (FastAPI) is expected to return JSON matching these shapes.

export type ChangeStatus =
  | "Draft" | "Pending" | "Analyzing" | "Approved" | "Rejected" | "Executing" | "Completed" | "RolledBack";
export type RiskLevel = "low" | "medium" | "high";

export type ImpactedComponent = {
  graph_node_id: string;
  component_type: string;
  impact_level: "direct" | "indirect";
  display_name: string;
};

export type IncidentSeverity = "blocker" | "warning" | "info";

export type RiskFactor = {
  label: string;
  severity: IncidentSeverity;
  policy?: string;
  reason?: string;
  evidence?: string[];
};

export type ConfigDiffLine = { kind: "add" | "remove" | "context"; text: string };

export type RuleConflict = {
  severity: "info" | "warn" | "error";
  kind: "shadow" | "shadowed_by" | "duplicate" | "overlap";
  message: string;
  reference?: string;
};

export type ReachabilityCheck = {
  src: string; dst: string; port: string;
  before: "allow" | "deny"; after: "allow" | "deny";
  path: string[];
};

export type PreflightCheck = {
  id: string; label: string;
  status: "pass" | "fail" | "warn" | "pending";
  detail?: string;
};

export type ImpactedService = {
  id: string; name: string; owner: string; on_call: string;
  sla_tier: "T1" | "T2" | "T3"; rps: number;
  expected_disruption: "none" | "brief" | "full";
};

export type ActivityItem = {
  id: string; at: string; node: string; change_id: string;
  title: string; outcome: "ok" | "rollback" | "partial" | "incident";
};

export type SimilarStats = {
  total: number; ok: number; rollback: number; partial: number;
  median_exec_minutes: number;
};

export type ImpactAnalysis = {
  risk_factors: RiskFactor[];
  config_diff: ConfigDiffLine[];
  conflicts: RuleConflict[];
  reachability: ReachabilityCheck[];
  preflight: PreflightCheck[];
  services: ImpactedService[];
  recent_activity: ActivityItem[];
  similar: SimilarStats;
  traffic_sparkline: number[];
};

export type Change = {
  id: string;
  title: string;
  change_type: string;
  environment: string;
  action: string;
  description: string;
  execution_plan: string;
  rollback_plan: string;
  maintenance_window_start: string;
  maintenance_window_end: string;
  status: ChangeStatus;
  risk_score: number | null;
  risk_level: RiskLevel | null;
  analysis_stage: string;
  analysis_attempts: number;
  created_by: number;
  created_at: string;
  reject_reason?: string | null;
  impacted_components: ImpactedComponent[];
  analysis?: ImpactAnalysis;
};

export type AuditEntry = {
  id: number;
  change_id: string | null;
  user_id: number | null;
  action: string;
  details: Record<string, unknown> | null;
  timestamp: string;
};

export type Connector = {
  id: number;
  name: string;
  connector_type: string;
  sync_mode: "pull" | "webhook" | "on-demand";
  sync_interval_minutes: number;
  last_sync_at: string | null;
  status: "active" | "inactive" | "error";
  last_error: string | null;
};

export type Policy = {
  id: number;
  name: string;
  description: string;
  rule_type: "time_restriction" | "double_validation" | "auto_block";
  action: "block" | "warn" | "require_double_approval";
  enabled: boolean;
  condition: Record<string, unknown>;
};

export type GraphNode = {
  id: string;
  label: "Device" | "Application" | "Service";
  layer: "security" | "network" | "application";
  display_name: string;
  properties: {
    type?: string; vendor?: string; role?: string; ip?: string; criticality?: string;
  };
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  rel_type: "CONNECTED_TO" | "PROTECTS" | "RUNS";
};

export type Topology = { nodes: GraphNode[]; edges: GraphEdge[] };

export type ImpactPayload = {
  directly_impacted: { id: string; label: string; properties: Record<string, unknown> }[];
  indirectly_impacted: { id: string; label: string; properties: Record<string, unknown> }[];
  affected_applications: { id: string; label: string; properties: Record<string, unknown> }[];
  affected_services: { id: string; label: string; properties: Record<string, unknown> }[];
  affected_vlans: { id: string; label: string; properties: Record<string, unknown> }[];
  total_dependency_count: number;
  max_criticality: string;
  llm_powered?: boolean;
  action_analysis?: {
    action: string;
    traversal_strategy: string;
    explanation: string;
  };
  risk_assessment?: {
    severity: "critical" | "high" | "medium" | "low";
    summary: string;
    factors: string[];
    mitigations: string[];
  };
  blast_radius?: {
    total_impacted: number;
    critical_services_at_risk: string[];
    redundancy_available: boolean;
    redundancy_details: string;
    redundancy_per_application?: Record<string, {
      has_alternate_protection: boolean;
      summary: string;
    }>;
  };
};

export type Kpis = {
  total_changes: number;
  auto_approved_pct: number;
  avg_validation_minutes: number;
  incidents_post_change_pct: number;
  scoring_precision_pct: number;
  core_changes_detected_pct: number;
};
