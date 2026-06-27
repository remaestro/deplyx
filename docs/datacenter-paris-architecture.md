# 🏢 Datacenter Paris — Architecture réseau

> **Dernière mise à jour :** 27 juin 2026
> **Site :** Datacenter Paris (site_id: 2)
> **Total :** 88 devices, 348 interfaces, 1334 nœuds Neo4j

---

## 📐 Architecture globale (5 couches)

```
┌──────────────────────────────────────────────────────────────┐
│  🌐 WAN — ISP Peering (Orange, SFR)                         │
│  🟡 Routeurs WAN → Core Switch                               │
├──────────────────────────────────────────────────────────────┤
│  🟡 Core → Distribution → Access Switches                    │
│  🟡 Load Balancer, Wireless Controller                        │
├──────────────────────────────────────────────────────────────┤
│  🔴 Firewalls (DMZ) → Web Servers                            │
├──────────────────────────────────────────────────────────────┤
│  🖥️ Hyperviseurs (ESXi) → vCenter                           │
│  💾 SAN / NAS / Backup                                       │
├──────────────────────────────────────────────────────────────┤
│  🔧 Management : DNS, NTP, AAA, Bastion, OOB                │
└──────────────────────────────────────────────────────────────┘
```

---

## 1️⃣ 🔴 ZONE SECURITY (DMZ)

| Nœud | Rôle | Connecté à | Impact direct | Impact indirect |
|------|------|-----------|---------------|-----------------|
| `dc-par-fw-01` | Firewall principal | Core switch, LB, DMZ switches | Tout le trafic DMZ | Arrêt de tout le DMZ (web, apps) |
| `dc-par-fw-02` | Firewall secondaire (HA) | Core switch, LB, DMZ switches | Backup firewall | Dégradation si fw-01 tombe |
| `DEV-FG600-FW01` | Firewall FG-600 | DMZ switch | Segment DMZ restreint | Perte de segmentation fine |
| `DEV-FG600-FW02` | Firewall FG-600 backup | DMZ switch | Redondance FW | Aucun si fw-01 fonctionne |
| `dc-par-lb-01` | Load Balancer principal | Firewalls, Web servers | Distribution trafic web | Sites web inaccessible |
| `dc-par-lb-02` | Load Balancer secondaire | Firewalls, Web servers | Redondance LB | Dégradation si lb-01 tombe |
| `DEV-LB-ENT-01` | LB Entreprise 1 | DMZ switches | Apps spécifiques | Perte d'équilibrage local |
| `DEV-LB-ENT-02` | LB Entreprise 2 | DMZ switches | Redondance LB ent. | Aucun si LB-ENT-01 OK |
| `dc-par-srv-web-01` | Serveur Web 1 | LB, DB, Cache | Apps web frontales | Pages web indisponibles |
| `dc-par-srv-web-02` | Serveur Web 2 | LB, DB, Cache | Redondance web | Dégradation si web-01 OK |
| `DEV-51C50DD6` | Serveur DMZ web | DMZ switch | App spécifique | Perte d'un service web |
| `DEV-F99420A9` | Serveur DMZ web | DMZ switch | App spécifique | Perte d'un service web |

### 🔥 Règles firewall typiques
> Les firewalls appliquent les règles `PROTECTS` :
> - **DMZ → Internet :** HTTP/HTTPS sortant (80, 443)
> - **Internet → DMZ :** HTTP/HTTPS entrant (80, 443) vers les LB
> - **DMZ → Interne :** DB (5432), Cache (6379), LDAP (389) — *restreint par IP source*
> - **Interne → DMZ :** SSH (22), SNMP (161), Syslog (514) — *management uniquement*

---

## 2️⃣ 🟡 ZONE NETWORK

### 2.1 🖧 CORE — Cœur de réseau

| Nœud | Rôle | Connecté à | Impact direct | Impact indirect |
|------|------|-----------|---------------|-----------------|
| `dc-par-core-01` | Core Switch 1 | Tous les dist switches, WAN routers | Routage inter-VLAN principal | Split du réseau en 2 |
| `dc-par-core-02` | Core Switch 2 | Tous les dist switches, WAN routers | Redondance L3 | Aucun si core-01 OK |
| `DEV-FXS230001AA` | Core Switch FXS 1 | Dist, WAN, Mgmt | Routage secondaire | Perte de redondance |
| `DEV-FXS230002AA` | Core Switch FXS 2 | Dist, WAN, Mgmt | Routage secondaire | Perte de redondance |

> **📌 Les core switches utilisent VPC / MLAG** pour la redondance L2 entre eux.

### 2.2 📡 DISTRIBUTION

| Nœud (x8) | Rôle | Connecté à | Impact |
|------------|------|-----------|--------|
| `dc-par-dist-01/02` | Dist Switch A | Core, Access switches zone A | Perte de tout un bloc A |
| `dc-par-dist-03/04` | Dist Switch B | Core, Access switches zone B | Perte de tout un bloc B |
| `DEV-CAT95-D01/02` | Dist Switch C | Core, Access spécifiques | Perte segment spécifique |
| `DEV-CAT95-D03/04` | Dist Switch D | Core, Access spécifiques | Redondance segment C |

> **📌 Les dist switches agrègent le trafic des access switches** et font du routage inter-VLAN.

### 2.3 🔌 ACCESS

| Nœud (x16) | Rôle | Connecté à | Impact |
|-------------|------|-----------|--------|
| `dc-par-acc-01` à `08` | Access switch | Dist switches, serveurs | Perte d'un rack de serveurs |
| `DEV-CAT29-ACC01` à `08` | Access switch | Dist switches, équipements | Perte d'un segment utilisateur |

> **📌 Chaque access switch dessert un rack ou une baie.** Les 16 access switches couvrent l'ensemble du datacenter.

### 2.4 🌐 WAN

| Nœud | Rôle | Connecté à | Impact |
|------|------|-----------|--------|
| `dc-par-wan-01` | Routeur WAN 1 | Core, ISP Orange | Connexion internet principale |
| `dc-par-wan-02` | Routeur WAN 2 | Core, ISP SFR | Backup internet |
| `DEV-ISR44-W01` | Routeur ISR 44-1 | Core, WAN | Liaison inter-site |
| `DEV-ISR44-W02` | Routeur ISR 44-2 | Core, WAN | Liaison inter-site backup |
| `DEV-ISP-ORA-001` | ISP Orange | WAN routers | Connexion FAI Orange |
| `DEV-ISP-SFR-001` | ISP SFR | WAN routers | Connexion FAI SFR (backup) |

> **📌 BGP multihoming** : les 2 routeurs WAN peers avec les 2 ISP en BGP. Perte d'un ISP = bascule automatique.

### 2.5 📶 WIRELESS

| Nœud | Rôle | Connecté à | Impact |
|------|------|-----------|--------|
| `dc-par-wlc-01/02` | WLC | Dist switches | Contrôleur WiFi principal/secours |
| `DEV-WLC9800-01/02` | WLC 9800 | Access switches | Points d'accès supplémentaires |

> **📌 Les WLC contrôlent les bornes WiFi** (CAPWAP). Le trafic WiFi est tunnelisé vers le WLC puis injecté sur le réseau filaire.

---

## 3️⃣ 🖥️ ZONE COMPUTE

| Nœud | Rôle | Connecté à | Relations RUNS | Impact |
|------|------|-----------|----------------|--------|
| `HV Core 01` | Hyperviseur ESXi 1 | Core switch, SAN | `web-gw`, `db-main`, `ldap-idm` | Perte de 50% des VMs |
| `HV Core 02` | Hyperviseur ESXi 2 | Core switch, SAN | `cache-main`, `grafana-obs`, `prom-core` | Perte de l'autre moitié |
| `vCenter 01` | vCenter | HV 1, HV 2, OOB | Gère les 2 hyperviseurs | Plus possible de migrer/manager |
| `vCenter 02` | vCenter backup | HV 1, HV 2, OOB | Redondance vCenter | Aucun si vCenter 01 OK |

> **📌 Relations RUNS** : Les apps (web, db, cache, monitoring) **tournent sur** les hyperviseurs.
> - Si HV Core 01 tombe → perte de `web-gw-01`, `db-main-01`, `ldap-idm-01`
> - Si HV Core 02 tombe → perte de `cache-main-01`, `grafana-obs-01`, `prom-core-01`
> - Si les 2 tombent → **tout le datacenter est hors service**

---

## 4️⃣ 💾 ZONE STORAGE

| Nœud | Rôle | Connecté à | Impact |
|------|------|-----------|--------|
| `SAN 01` | Baie SAN principale | HV 1, HV 2 (FC), Backup | Stockage bloc des VMs |
| `SAN 02` | Baie SAN secondaire | HV 1, HV 2 (FC) | Réplication synchrone |
| `NAS 01` | NAS NFS | HV 1, HV 2 (Ethernet), Backup | Stockage fichiers partagés |
| `Backup 01` | Serveur de backup | SAN, NAS | Sauvegardes quotidiennes |
| `dc-par-srv-fs-01/02` | Serveurs de fichiers | Access switches, NAS | Données utilisateurs |

> **📌 Flux storage :**
> ```
> Hyperviseur → FC → SAN (stockage bloc pour VMs)
> Hyperviseur → NFS → NAS (stockage fichiers)
> Backup → SAN + NAS → Sauvegarde
> ```

---

## 5️⃣ 🟢 ZONE APPLICATION

| Nœud | Rôle | Connecté à | Relations RUNS | Impact |
|------|------|-----------|----------------|--------|
| `dc-par-srv-db-*` (x4) | PostgreSQL | Web servers, App servers | `HV Core 01` | Perte des bases de données |
| `dc-par-srv-web-*` (x4) | Web servers (Nginx) | LB, DB, Cache | `HV Core 01` | Sites web hors ligne |
| `dc-par-srv-monitoring` | Prometheus/Grafana | Tous les équipements (SNMP) | `HV Core 02` | Perte de la supervision |
| `search-obs-01` | Elasticsearch | Web, Logs | `HV Core 02` | Logs centralisés indisponibles |

> **📌 Dépendances applicatives :**
> ```
> Client → LB → Web Server → DB (PostgreSQL)
>                        ↘ Cache (Redis)
>                        
> Monitoring ← SNMP ← Tous les devices
> ```

---

## 6️⃣ 🔧 ZONE MANAGEMENT

| Nœud | Rôle | Connecté à | Impact |
|------|------|-----------|--------|
| `dc-par-srv-dns-*` (x4) | DNS | Tous les équipements | Résolution DNS impossible |
| `dc-par-srv-ntp-*` (x4) | NTP | Tous les équipements | Dérive des horloges (logs incohérents) |
| `dc-par-srv-aaa-*` (x2) | AAA (TACACS+/RADIUS) | Firewalls, switches, routeurs | Plus d'authentification admin |
| `dc-par-srv-syslog-*` (x2) | Syslog | Tous les équipements | Logs centralisés indisponibles |
| `Bastion 01` | Jump host SSH | OOB Switch | Accès SSH aux équipements bloqué |
| `OOB Switch 01` | Switch management | Core, HVs, Bastion | Perte du management à distance |

> **📌 Le réseau OOB (Out-Of-Band)** est un réseau dédié au management :
> ```
> Admin → Bastion → OOB Switch → Équipements (ports MGMT)
> ```
> Même si le réseau principal est down, les admins peuvent accéder aux équipements via OOB.

---

## 🔗 Relations clés (types de liens)

| Type | Couleur | Signification | Exemple |
|------|---------|---------------|---------|
| `CONNECTED_TO` | 🔵 Cyan | Connexion physique/réseau | Switch → Serveur |
| `PROTECTS` | 🔴 Rouge | Règle firewall protège | FW → Web Server |
| `RUNS` | 🟢 Vert | Application tourne sur | Web → Hyperviseur |
| `HAS_INTERFACE` | - | Interface appartient à | Switch → Interface |
| `HAS_VLAN` | - | VLAN configuré sur | Switch → VLAN |
| `HAS_IP` | - | Adresse IP attribuée | Interface → IP |
| `HAS_ROUTE` | - | Route statique/dynamique | Routeur → Route |
| `HAS_BGP_PEER` | - | Session BGP établie | Routeur WAN → ISP |

---

## 💥 Analyse d'impact (blast radius)

| Élément qui tombe | 🔴 Direct | 🟡 Indirect |
|-------------------|-----------|-------------|
| **Core Switch 1** | Distributions A | Tous les services en aval |
| **Firewall 1** | Tout le DMZ | Applications web |
| **Hyperviseur 1** | Web, DB, LDAP | Toute la stack applicative |
| **SAN 1** | VMs sur HV 1 et 2 | Toutes les applications |
| **DNS** | Résolution DNS | Tous les services (noms non résolus) |
| **ISP Orange** | Liaison WAN 1 | Dégradation (basculé sur SFR) |
| **Bastion** | Accès SSH admin | Impossible de gérer à distance |

---

## 📊 Statistiques

| Métrique | Valeur |
|----------|--------|
| Devices | 88 |
| Interfaces | 348 |
| VLANs | 128 |
| Routes | 118 |
| Règles firewall | 29 |
| Services | 23 |
| Connexions CONNECTED_TO | 4580 |
