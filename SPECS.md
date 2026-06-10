# Deplyx — Spécifications fonctionnelles complètes

## Architecture générale

```
Frontend (React + Vite :5173)
  │
  └─▶ API Backend (FastAPI :8000/api/v1)
        │
        ├─▶ PostgreSQL (données relationnelles)
        ├─▶ Neo4j (graphe réseau)
        ├─▶ Redis (Celery broker)
        └─▶ Workers Celery (pipeline analyse)
```

**Pages supprimées :** Lab (toute la rubrique), Topology V1/V2/V4/V5 (on garde V3 uniquement)

---

## Navigation (sidebar)

```
Operations
  ├── Dashboard       /               icône: LayoutDashboard
  ├── Changes         /changes        icône: GitPullRequest
  └── Topology        /graph-v3       icône: Layers

Configuration
  ├── Connectors      /connectors     icône: Plug
  ├── Policies        /policies       icône: ShieldCheck
  └── Audit Log       /audit-log      icône: FileText
```

---

## 1. LOGIN

### Route : `/login`

### Objets API

```
POST /api/v1/auth/register
  Body: { email: string, password: string, role?: string }
  Response 201: { access_token: string, token_type: "bearer" }

POST /api/v1/auth/login
  Body: { email: string, password: string }
  Response 200: { access_token: string, token_type: "bearer" }

GET /api/v1/auth/me
  Headers: Authorization: Bearer <token>
  Response 200: { id: number, email: string, role: string, is_active: bool }
```

### Écran
- 60% left : fond animé / canvas topologie
- 40% right : carte glassmorphism avec formulaire login
- Toggle Login / Register
- Sur login OK : store token + navigate vers `/`

### Store
```
token: string | null
user: { id, email, role } | null
isAuthenticated: boolean
login(token, user)
logout()
```

---

## 2. DASHBOARD

### Route : `/`

### Objets API

```
GET /api/v1/dashboard/kpis
  Headers: Authorization: Bearer <token>
  Response 200: {
    total_changes: number,
    auto_approved_pct: float,
    avg_validation_minutes: float,
    incidents_post_change_pct: float,
    scoring_precision_pct: float,
    core_changes_detected_pct: float,
    definitions: { [key]: string }
  }

GET /api/v1/changes?status=&env=&change_type=&mine=
  Query: status?, env?, change_type?, mine?(bool)
  Response 200: [
    {
      id: string,
      title: string,
      change_type: string,
      environment: string,
      status: string,
      risk_score: float | null,
      risk_level: string | null,
      analysis_stage: string,
      analysis_attempts: int,
      created_by: int,
      created_at: datetime
    }
  ]

GET /api/v1/audit-log?limit=20
  Response 200: [
    { id: int, change_id: string | null, user_id: int | null,
      action: string, details: object | null, timestamp: datetime }
  ]
```

### Écran
- Bandeau titre : "Dashboard" + sélecteur de plage temporelle (24h/7d/30d/All)
- 6 cartes KPIs (chacune avec sparkline) :
  - Total Changes
  - Auto-approved %
  - Avg Validation (minutes)
  - Post-change Incidents %
  - Scoring Precision %
  - Core Changes Detected %
- Pie chart distribution des risques + Bar chart changes par statut
- Tableau des derniers changements (avec switch Table/Kanban)
- Timeline activité (8 dernières entrées audit-log)

---

## 3. CHANGES — Liste

### Route : `/changes`

### Objets API

```
POST /api/v1/changes
  Body: {
    title: string,
    change_type: "Preventive"|"Evolution"|"Corrective"|"Firewall"|"Switch"|"VLAN"|"Port"|"Rack"|"CloudSG",
    environment: "prod"|"pre-prod"|"Prod"|"Preprod"|"DC1"|"DC2",
    action: string (ChangeActionEnum),
    description: string,
    execution_plan: string,
    rollback_plan: string,
    maintenance_window_start: datetime,
    maintenance_window_end: datetime,
    target_components: string[]
  }
  Response 201: ChangeRead

GET /api/v1/graph/devices
  Response 200: [ { id, hostname, type, vendor, ip, criticality, ... } ]

GET /api/v1/graph/search?q=&limit=20
  Response 200: [ { id, label, display_name, ... } ]
```

### Résultat ChangeRead complet
```
ChangeRead {
  id: string,
  title: string,
  change_type: string,
  environment: string,
  action: string | null,
  description: string,
  execution_plan: string,
  rollback_plan: string | null,
  maintenance_window_start: datetime | null,
  maintenance_window_end: datetime | null,
  status: "Draft"|"Pending"|"Analyzing"|"Approved"|"Rejected"|"Executing"|"Completed"|"RolledBack",
  risk_score: float | null,
  risk_level: "low"|"medium"|"high"|null,
  analysis_stage: string,
  analysis_attempts: int,
  analysis_last_error: string | null,
  analysis_trace_id: string | null,
  reject_reason: string | null,
  created_by: int,
  created_at: datetime,
  updated_at: datetime,
  impacted_components: [
    { graph_node_id: string, component_type: string, impact_level: "direct"|"indirect",
      display_name: string | null, label: string | null }
  ]
}
```

### Écran
- **3 vues** : Table (checkbox), Card, Kanban (5 colonnes: Draft/Pending/Approved/Executing/Completed)
- **Filtres** : statut, environnement, recherche texte
- **Bouton "Create Change"** → drawer slide-in avec wizard 3 étapes :
  1. Basics : titre, type, action, target components (NodePicker search), description
  2. Plans : execution plan + rollback plan (textarea)
  3. Window : maintenance start/end datetime
- Click ligne → navigate `/changes/:id`

---

## 4. CHANGE DETAIL

### Route : `/changes/:id`

### Objets API

```
GET /api/v1/changes/:id → ChangeRead

PUT /api/v1/changes/:id
  Body: { title?, action?, description?, execution_plan?, rollback_plan?,
          maintenance_window_start?, maintenance_window_end?, target_components? }
  Response 200: ChangeRead

POST /api/v1/changes/:id/reject
  Body: { reason: string }

GET /api/v1/changes/:id/impact
  Query: refresh? (bool)
  Response 200: {
    change_id: string,
    impact: ImpactPayload
  }

POST /api/v1/risk/calculate
  Body: { change_id: string }
  Response 200: { change_id, impact: dict, risk: { risk_score, risk_level } }
```

### ImpactPayload (réponse LLM)
```
ImpactPayload {
  directly_impacted: [ { id, label, properties } ],
  indirectly_impacted: [ { id, label, properties } ],
  affected_applications: [ { id, label, properties } ],
  affected_services: [ { id, label, properties } ],
  affected_vlans: [ { id, label, properties } ],
  total_dependency_count: int,
  max_criticality: string,
  llm_powered: bool,

  action_analysis: {
    action: string,
    traversal_strategy: string,
    explanation: string
  },

  risk_assessment: {
    severity: "critical"|"high"|"medium"|"low",
    summary: string,
    factors: string[],
    mitigations: string[]
  },

  blast_radius: {
    total_impacted: int,
    critical_services_at_risk: string[],
    redundancy_available: bool,
    redundancy_details: string,
    redundancy_per_application?: { [appId]: {
      has_alternate_protection: bool,
      summary: string,
      alternate_protectors: [{ rule_id, rule_display_name, device_id, device_display_name, device_vendor }]
    }}
  }
}
```

### Écran — 2 onglets

#### Overview
Header : titre + status badge + back button

| Champ | Affichage |
|---|---|
| Description | text |
| Target | IDs des composants cibles |
| Environment | badge |
| Maintenance Window | plage datetime |
| Execution Plan | CodeBlock |
| Rollback Plan | CodeBlock |
| Reject reason | bannière rouge (si rejeté) |

Bouton Edit : ouvre formulaire inline pour les champs (Draft/Pending uniquement)

#### Impact Analysis

**Header bar** : `[AI] LLM analysis` | `Topology` button | `Re-analyze` button

**Action Analysis** : badge action + strategy + texte explicatif

**Risk Assessment** : severity badge + summary + factors (tags rouges) + mitigations (tags verts)

**Blast Radius** : 3 métriques compactes (Total Impacted, Critical Services, Redundancy) + détails

### Navigation
- `Topology` button → navigate `/graph-v3?changeId=xxx`
- `Back` arrow → `/changes`

---

## 5. TOPOLOGY V3

### Route : `/graph-v3`
Peut recevoir `?changeId=xxx` pour visualiser l'impact d'un changement

### Objets API

```
GET /api/v1/graph/topology?depth=5
  Response 200: {
    nodes: [
      { id: string, label: string (Neo4j label), display_name: string | null,
        properties: { type, vendor, hostname, ip, role, criticality, ... } }
    ],
    edges: [
      { id: string, source: string, target: string,
        rel_type: "CONNECTED_TO"|"PROTECTS"|"RUNS",
        properties: { local_port?, neighbor_port?, ... } }
    ]
  }

GET /api/v1/changes/:id/impact → ImpactPayload (quand ?changeId=xxx)
```

### Écran
Affichage SVG avec 3 couches fonctionnelles superposées :

```
┌─────────────────────────────────────────────┐
│  Security (firewalls)   ─── bg: #312033     │
│    [FTD-01] [FTD-02]                        │
├─────────────────────────────────────────────┤
│  Network (routers/switches) ─── bg: #143046 │
│    [R5] [SW1] [SW2]                         │
├─────────────────────────────────────────────┤
│  Application (services) ─── bg: #173524     │
│    [App1] [App2]                            │
└─────────────────────────────────────────────┘
```

**Contrôles toolbar :**
- Toggles : CDP | PROTECTS | RUNS (visibilité des liens)
- Mode impact local : bouton "Impact" → clic nœud pour simuler panne
- En mode change : bouton "Back to change detail" + bannière impact

**Interaction nœud** :
- Click → drawer latéral (infos nœud : role, IP, vendor, interfaces, routes, rules, VLANs, services, relations)
- En mode impact (local ou change) : coloration des nœuds :
  - Direct = red ring
  - Indirect = amber ring
  - Unaffected = grisé

**Liens :**
- CDP = trait plein teal
- PROTECTS = tireté red
- RUNS = tireté green

**Layout :** `computeLayout()` distribue les nœuds horizontalement par couche :
- Security : centrés en haut
- Network : core routers au milieu, access switches en dessous
- Application : alignés sous leur device propriétaire

**Bannière impact change (quand ?changeId=) :**
```
┌──────────────────────────────────────────────────────┐
│ ⚠ Change #8143a5f1 | Direct: 2 | Indirect: 5 | ... │
│ Criticality: medium            [Back to change detail]│
└──────────────────────────────────────────────────────┘
```

---

## 6. CONNECTEURS

### Route : `/connectors`

### Objets API

```
GET /api/v1/connectors
  Response 200: [
    {
      id: int, name: string, connector_type: string,
      config: object, sync_mode: "pull"|"webhook"|"on-demand",
      sync_interval_minutes: int,
      last_sync_at: datetime | null,
      last_sync_detail: object | null,
      status: "active"|"inactive"|"error",
      last_error: string | null,
      created_at: datetime, updated_at: datetime
    }
  ]

POST /api/v1/connectors
  Body: {
    name: string,
    connector_type: string,
    config: object (host, credentials),
    sync_mode?: "pull"|"webhook"|"on-demand" (default: "on-demand"),
    sync_interval_minutes?: int (default: 60)
  }
  Response 201: ConnectorRead

DELETE /api/v1/connectors/:id → 204

POST /api/v1/connectors/:id/sync
  Response 200: { status: "synced"|"partial"|"error", synced: {...}, failed: {...}, errors: [...] }

POST /api/v1/connectors/sync-all
  → Wipe Neo4j + resync all connectors
  Response 200: { status, duration_seconds, total, results }

GET /api/v1/connectors/:id/sync-history?limit=20
  Response 200: [ { id, connector_id, timestamp, status, devices_synced, duration_ms, error } ]

POST /api/v1/connectors/:id/operations
  Body: {
    contract_version: "2.0",
    operation: "sync"|"validate"|"simulate"|"apply"|"custom",
    action?: string, input?: {}, context?: {}, target?: {}
  }
  Response 200: {
    contract_version: "2.0", operation: string, connector_type: string,
    ok: bool, status: "success"|"failed"|"partial"|"accepted",
    summary: string, data: {}, changes: [], artifacts: {}, metrics: {},
    errors: [{ code, message, retryable, field }]
  }
```

### Discovery API

```
POST /api/v1/discovery/sessions
  Body: {
    name?: string, targets: string[], cidrs?: string[],
    inventory?: [{ host, name?, connector_type?, metadata? }],
    ports?: int[], timeout_seconds?: int (default: 3), max_targets?: int (default: 128)
  }
  Response 201: DiscoverySessionDetail (id, status, results, ...)

GET /api/v1/discovery/sessions → list[DiscoverySessionRead]

GET /api/v1/discovery/sessions/:id → DiscoverySessionDetail

POST /api/v1/discovery/sessions/:id/bootstrap
  Body: {
    connector_defaults?: { [type]: config },
    default_config?: {},
    sync_mode?: "on-demand" (default),
    sync_interval_minutes?: int (default: 60),
    run_sync?: bool (default: true),
    allow_ambiguous?: bool (default: false),
    on_existing?: "skip" (default),
    items: [{ result_id: int, connector_type?: string, run_sync?: bool }]
  }
  Response 200: { session_id, processed, created, synced, skipped, errors, items: [...] }
```

### Types de connecteurs supportés (22)

| Type | Vendeur | Méthode | Données collectées |
|---|---|---|---|
| `paloalto` | Palo Alto | API XML/REST | Système, interfaces, règles security |
| `fortinet` | Fortinet | API REST FortiOS | Système, interfaces, policies firewall |
| `cisco` | Cisco IOS/IOS-XE | SSH (NAPALM/netmiko) | Interfaces, VLANs, ARP, CDP/LLDP, routes, BGP |
| `cisco-ftd` | Cisco FTD | API FDM REST + SSH | Interfaces, règles, VPN, objets réseau |
| `cisco-nxos` | Cisco NX-OS | SSH (NAPALM) | Interfaces, VLANs, MAC, CDP/LLDP, routes, spanning-tree |
| `cisco-router` | Cisco routers | SSH (netmiko) | Interfaces, routes, BGP, OSPF, ACLs, HSRP |
| `cisco-wlc` | Cisco WLC | SSH (netmiko) | APs, WLANs, clients |
| `juniper` | Juniper JunOS | SSH (NAPALM) | Interfaces, VLANs, MAC, ARP, routes, BGP |
| `checkpoint` | Check Point | API Web | Gateways, règles access-layer |
| `aruba-switch` | Aruba Switch | SSH (netmiko) | Interfaces, VLANs, MAC, LLDP |
| `aruba-ap` | Aruba AP | SSH (netmiko) | AP status, radios, clients |
| `vyos` | VyOS | SSH (netmiko) | Interfaces, routes, NAT, firewall |
| `strongswan` | strongSwan | SSH | tunnels VPN |
| `snort` | Snort IDS | SSH | Règles IDS, alertes |
| `openldap` | OpenLDAP | SSH | Entrées annuaire |
| `nginx` | Nginx | SSH | Virtual hosts |
| `postgres` | PostgreSQL | SSH | Bases, tables, schémas |
| `redis` | Redis | SSH | Info, keyspace |
| `elasticsearch` | Elasticsearch | SSH | Cluster, indices |
| `grafana` | Grafana | SSH | Dashboards, datasources |
| `prometheus` | Prometheus | SSH | Targets, scrape configs |

### Écran

**Deux sections dans l'onglet Connecteurs :**

#### A. Connecteurs (grille de cartes)
- Carte par connecteur : nom, type, icône vendeur, status LED (vert=active, rouge=error, gris=inactive)
- Infos : last sync, sync mode, intervale
- Boutons : Sync Now, Log (sync-history), Delete
- Bouton "Sync All" (tête de liste)
- Filtre par type/vendeur
- **Add Connector** : drawer avec wizard 2 étapes :
  1. Type & Name : sélecteur de type + nom
  2. Connection : host, credentials (SSH ou API selon type)

#### B. Discovery (détection réseau)
- **Start Discovery** : formulaire (targets IP, CIDRs, timeout)
- Session list : status badges, target count, ports
- Résultats : filtre par reachability, evidence type, search
- **Bootstrap** : sélectionner des résultats → créer les connecteurs automatiquement

### Flux Discovery → Connector

```
1. User entre des IPs/CIDRs
2. POST /discovery/sessions → probe les targets (TCP, SSH, HTTP, SNMP, LDAP, etc.)
3. Frontend affiche les résultats (host, status, connector type suggéré)
4. User sélectionne les résultats + valide les types
5. POST /discovery/sessions/:id/bootstrap → crée les connecteurs + sync optionnel
```

---

## 7. POLICIES

### Route : `/policies`

### Objets API

```
GET /api/v1/policies?enabled_only=
  Response 200: [
    { id, name, description, rule_type, condition, action, enabled, created_by, created_at, updated_at }
  ]

POST /api/v1/policies
  Body: {
    name: string, description?: string,
    rule_type: "time_restriction"|"double_validation"|"auto_block",
    condition: object, action: "block"|"warn"|"require_double_approval",
    enabled?: bool (default: true)
  }
  Response 201: PolicyRead

PUT /api/v1/policies/:id → PolicyUpdate

DELETE /api/v1/policies/:id → 204

POST /api/v1/policies/evaluate
  Body: { change_id: string }
  Response: { change_id, results: [{ policy_id, policy_name, rule_type, triggered, action, reason }],
              blocked: bool, warnings: [string] }

POST /api/v1/policies/:id/simulate
  Body: { ... change mock ... }
  Response: { would_block, matched_rules, risk_delta }

GET /api/v1/policies/conflicts
  Response: [ ... conflicting policies ... ]
```

### Types de règles
| rule_type | Condition | Action |
|---|---|---|
| `time_restriction` | `{blocked_hours_start, blocked_hours_end, blocked_days, environments}` | `block` |
| `double_validation` | `{environments, change_types, required_approvals}` | `require_double_approval` |
| `auto_block` | `{block_any_any_rules, block_environments, block_change_types}` | `block` |

### Écran
- Cartes de politiques (type icon + badge + toggle enable/disable + delete)
- 3 types : Time Restriction, Double Validation, Auto Block
- **Policy Wizard** : drawer 3 étapes (Basics → Conditions → Preview)
- **Simulation Panel** : sélectionner politique + éditer JSON change mock → run
- **Conflict Detection Panel** : liste conflits entre politiques
- Filtre : search + type filter chips
- Stats bar : total, enabled, disabled

---

## 8. AUDIT LOG

### Route : `/audit-log`

### Objets API

```
GET /api/v1/audit-log?change_id=&user_id=&action=&limit=100
  Response 200: [
    { id, change_id, user_id, action, details, timestamp }
  ]
```

### Écran
- Timeline avec actions colorées (created, approved, rejected, executed, rolled_back, deleted, updated, viewed, login, policy_triggered)
- Expandable entries (JSON details)
- Filtres : full-text search, action type dropdown, user ID, change ID
- Time range pills (1h, 24h, 7d, 30d, All)
- Export : JSON ou CSV

---

## 9. MODÈLES DE DONNÉES (PostgreSQL)

### users
| Column | Type |
|---|---|
| id | int PK |
| email | varchar(255) UNIQUE |
| hashed_password | varchar(255) |
| role | varchar(32) default "Viewer" |
| is_active | bool default true |
| created_at | datetime(tz) |
| updated_at | datetime(tz) |

### changes
| Column | Type |
|---|---|
| id | varchar(36) PK (uuid) |
| title | varchar(255) |
| change_type | varchar(32) |
| environment | varchar(32) |
| action | varchar(64) nullable |
| description | text |
| execution_plan | text |
| rollback_plan | text nullable |
| maintenance_window_start | datetime(tz) nullable |
| maintenance_window_end | datetime(tz) nullable |
| status | varchar(32) default "Draft" |
| risk_score | float nullable |
| risk_level | varchar(16) nullable |
| impact_cache | JSON nullable |
| analysis_stage | varchar(32) default "pending" |
| analysis_attempts | int default 0 |
| analysis_last_error | text nullable |
| analysis_trace_id | varchar(36) nullable |
| created_by | int FK→users |
| reject_reason | text nullable |
| created_at | datetime(tz) |
| updated_at | datetime(tz) |

### change_impacted_components
| Column | Type |
|---|---|
| id | int PK |
| change_id | varchar(36) FK→changes CASCADE |
| graph_node_id | varchar(255) |
| component_type | varchar(64) |
| impact_level | varchar(16) "direct"\|"indirect" |

### approvals
| Column | Type |
|---|---|
| id | int PK |
| change_id | varchar(36) FK→changes CASCADE |
| approver_id | int FK→users nullable |
| role_required | varchar(32) |
| status | varchar(16) "Pending"\|"Approved"\|"Rejected" |
| comment | text nullable |
| decided_at | datetime(tz) nullable |
| timeout_at | datetime(tz) |
| created_at | datetime(tz) |

### audit_logs
| Column | Type |
|---|---|
| id | int PK |
| change_id | varchar(36) FK→changes SET NULL nullable |
| user_id | int FK→users nullable |
| action | varchar(64) |
| details | JSON nullable |
| timestamp | datetime(tz) |

### connectors
| Column | Type |
|---|---|
| id | int PK |
| name | varchar(255) |
| connector_type | varchar(32) |
| config | JSON |
| sync_mode | varchar(16) default "on-demand" |
| sync_interval_minutes | int default 60 |
| last_sync_at | datetime(tz) nullable |
| last_sync_detail | JSON nullable |
| status | varchar(16) default "inactive" |
| last_error | text nullable |
| created_at | datetime(tz) |
| updated_at | datetime(tz) |

### policies
| Column | Type |
|---|---|
| id | int PK |
| name | varchar(255) |
| description | text |
| rule_type | varchar(32) |
| condition | JSON |
| action | varchar(64) default "block" |
| enabled | bool default true |
| created_by | int FK→users nullable |
| created_at | datetime(tz) |
| updated_at | datetime(tz) |

### discovery_sessions
| Column | Type |
|---|---|
| id | int PK |
| name | varchar(255) nullable |
| status | varchar(16) |
| input_payload | JSON |
| ports | JSON |
| timeout_seconds | int default 3 |
| target_count | int default 0 |
| summary | JSON nullable |
| started_at | datetime(tz) nullable |
| completed_at | datetime(tz) nullable |
| last_error | text nullable |
| created_at | datetime(tz) |
| updated_at | datetime(tz) |

### discovery_results
| Column | Type |
|---|---|
| id | int PK |
| session_id | int FK→discovery_sessions CASCADE |
| host | varchar(255) |
| name_hint | varchar(255) nullable |
| source_kind | varchar(32) |
| status | varchar(16) |
| selected_connector_type | varchar(64) nullable |
| suggested_connector_types | JSON |
| preflight_status | varchar(16) |
| bootstrap_status | varchar(16) |
| connector_id | int nullable |
| connector_name | varchar(255) nullable |
| probe_detail | JSON |
| facts | JSON |
| classification_reasons | JSON |
| bootstrap_detail | JSON nullable |
| error | text nullable |
| created_at | datetime(tz) |
| updated_at | datetime(tz) |

---

## 10. GRAPHE NEO4J

### Nœuds
| Label | Propriétés clés |
|---|---|
| `Device` | id, hostname, vendor, type, role, ip, serial, model, os_version, display_name, has_redundancy, redundancy_protocol, criticality |
| `Interface` | id, name, status, ip, mask, display_name, acl_in, acl_out, vlans, input_errors, output_errors, crc, input_rate, output_rate |
| `Route` | id, network, display_name |
| `VLAN` | id, vlan_id, name, display_name |
| `Rule` | id, name, source, destination, port, protocol, action, display_name |
| `Application` | id, name, label, criticality, display_name |
| `Service` | id, name, port, protocol, enabled, display_name |
| `ARP` | id, ip_address, mac, interface, display_name |
| `IP` | id, address, subnet, version |
| `Cable` | id, cable_type |

### Relations
| Type | Source → Target | Propriétés |
|---|---|---|
| `HAS_INTERFACE` | Device → Interface | — |
| `HAS_ROUTE` | Device → Route | — |
| `HAS_VLAN` | Device → VLAN | — |
| `HAS_RULE` | Device → Rule | — |
| `HAS_ARP` | Device → ARP | — |
| `HAS_IP` | Device → IP | — |
| `CONNECTED_TO` | Device → Device | source, local_port, neighbor_port |
| `PROTECTS` | Rule → Application (ou Device → Device) | — |
| `RUNS` | Device → Service | — |
| `PART_OF` | (entité enfant) → Device | — |
| `LOCATED_IN` | Device → Datacenter | — |
| `ROUTES_TO` | Device → Device | — |
| `HAS_BGP_PEER` | Device → Device | — |
| `HAS_VRF` | Device → VRF | — |
| `HAS_VPN_TUNNEL` | Device → VPN | — |

### Types de relations autorisées (39)
```
HAS_INTERFACE, HAS_VLAN, HAS_RULE, HOSTS, HAS_IP, HAS_ARP, RUNS,
PROTECTS, CONNECTED_TO, HAS_BGP_PEER, HAS_VRF, HAS_ROUTE,
HAS_VPN_TUNNEL, HAS_WLAN, HAS_AP, SERVES_WLAN, HAS_RADIO,
HAS_VHOST, HAS_INDEX, HAS_DATASOURCE, HAS_SCRAPE_TARGET,
HAS_REPLICA, PART_OF, ROUTES_TO, LOCATED_IN
```

---

## 11. PIPELINE D'ANALYSE (Celery)

### Workflow soumission

```
POST /api/v1/changes → création Change (status=Draft)
POST /api/v1/changes/:id/submit → enqueue analyse Celery

┌─────────────────────────────────────────────────────────────────────┐
│  Celery Chain (5 étapes)                                            │
│                                                                     │
│  1. fetch_change_data                                               │
│     → charge le Change depuis DB                                    │
│     → stage = "fetching_data"                                       │
│                                                                     │
│  2. compute_impact                                                  │
│     → impact_service.analyze_impact()                               │
│       → graph traversal (Neo4j)                                     │
│       → LLM optionnel (si provider configuré)                       │
│     → stocke dans change.impact_cache                               │
│     → stage = "computing_impact"                                    │
│                                                                     │
│  3. score_risk                                                      │
│     → risk_engine.evaluate_change()                                 │
│       → base score from LLM severity (20/40/60/80)                  │
│       → modifiers: environment, core device, dependencies,          │
│         rollback, maintenance window, incident history, action      │
│     → stocke risk_score + risk_level sur le Change                  │
│     → stage = "scoring_risk"                                        │
│                                                                     │
│  4. route_workflow                                                  │
│     → workflow_engine.route_change()                                │
│       → low risk + auto_approve → status = "Approved"                │
│       → medium/high → crée Approval records pour les rôles requis   │
│     → stage = "routing_workflow"                                    │
│                                                                     │
│  5. finalise_analysis                                               │
│     → nettoie analysis_last_error                                   │
│     → stage = "finalised"                                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Tâches périodiques (Celery Beat)

| Tâche | Intervalle | Description |
|---|---|---|
| check_timeouts | 30 min | Vérifie les approvals expirées |
| sync_pull_connectors | 5 min | Sync les connecteurs en mode pull |
| poll_dead_letter | 2 min | Messages morts |
| reconcile_graph_pg | 10 min | Réconciliation Neo4j ↔ PostgreSQL |

### Actions et stratégies de traversée

| Action Groupe | Traversal Strategy | Description |
|---|---|---|
| add_rule, remove_rule, modify_rule, disable_rule, modify_acl, modify_sg | `rule_dependency_trace` | Trace PROTECTS edges, security exposure |
| disable_port, enable_port, shutdown_interface | `port_dependency_trace` | Trace PART_OF/CONNECTED_TO/HAS_INTERFACE |
| change_vlan, delete_vlan, modify_vlan | `vlan_membership_scan` | VLAN membership, devices on VLAN |
| reboot_device, decommission, firmware_upgrade, delete_sg | `full_device_blast_radius` | Full traversal : CONNECTED_TO/HAS_RULE/HOSTS/PROTECTS |
| config_change, modify_sg | `config_neighbor_crawl` | Connected neighbors + services |

### Score risque → mapping
| Score | Level | Auto-Approve |
|---|---|---|
| 0-30 | low | true |
| 31-70 | medium | false |
| 71+ | high | false |

### Modificateurs de score

| Condition | Modificateur |
|---|---|
| Environnement production | +8 |
| Device core/critique | +10 |
| >10 dépendances | +5 |
| Pas de rollback plan | +7 |
| Hors fenêtre maintenance | +8 |
| Historique incidents | +5 |
| Action sévérité (décommission) | +10 |
| Action sévérité (add_rule) | +2 |

---

## 12. ÉTATS D'UN CHANGE

```
Draft ──▶ Pending ──▶ Analyzing ──▶ Approved ──▶ Executing ──▶ Completed
  │                     │              │                            │
  │                     │              ├──▶ RolledBack              │
  │                     │              │                            │
  │                     └──▶ Rejected  └────────────────────────────┘
  │
  └── (edit)
```

### Analyse stages (micro-états pendant Analyzing)
```
pending → fetching_data → computing_impact → scoring_risk → routing_workflow → finalised
                                                                              → failed (si erreur)
```

---

## 13. AUTH & ROLES

### Système
- JWT (HS256, expire 60 min)
- Token dans header `Authorization: Bearer <token>`
- Refresh : nouvelle connexion

### Rôles
| Rôle | Permissions |
|---|---|
| `Admin` | Tout (CRUD connecteurs, policies, graph, discovery, approve/reject/execute/complete/rollback changes) |
| `Network` | Connecteurs (list/get/sync/view history), Graph CRUD (devices, interfaces, VLANs, routes, rules), Discovery sessions, Changes lifecycle |
| `Security` | Policies CRUD, Rules CRUD, Connectors (validate/simulate/apply), Changes approve/reject |
| `Approver` | Changes approve/reject, Policies evaluate |
| `DC_Manager` | Changes approve/reject |
| `Viewer` | Policies (list/get) |
