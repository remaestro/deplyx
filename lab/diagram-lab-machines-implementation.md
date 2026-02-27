# Lab Machines — Implementation and Exposure Map

This document restores the per-machine implementation map from the session.

## 1) fortinet
```mermaid
flowchart LR
  A[Connector/API Client] --> B[HTTPS :443]
  B --> C[lab/mock-fortinet/app.py]
  C --> D[state.py in-memory]
  C --> E[/health /ready /lab-config]
  C --> F[FortiOS-like endpoints]
```

## 2) paloalto
```mermaid
flowchart LR
  A --> B[HTTPS :443]
  B --> C[lab/mock-paloalto/app.py]
  C --> D[state.py]
  C --> E[/health /ready /lab-config]
  C --> F[PAN-OS XML/REST-like endpoints]
```

## 3) checkpoint
```mermaid
flowchart LR
  A --> B[HTTPS :443]
  B --> C[lab/mock-checkpoint/app.py]
  C --> D[state.py + session store]
  C --> E[/health /ready /lab-config]
  C --> F[/web_api/login + rulebase endpoints]
```

## 4) cisco-ios
```mermaid
flowchart LR
  A[Connector SSH] --> B[SSH :22]
  B --> C[lab/mock-cisco/ssh_server.py]
  C --> D[state.py]
  C --> E[show version/interfaces/vlan]
  F[Health sidecar :8080] --> G[/health /ready /lab-config]
```

## 5) juniper
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-juniper/ssh_server.py]
  C --> D[state.py]
  C --> E[Junos-like show commands]
  F[:8080] --> G[/health /ready /lab-config]
```

## 6) cisco-nxos
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-cisco-nxos/ssh_server.py]
  C --> D[state.py]
  C --> E[show version/interface/vlan/bgp/vrf]
  F[:8080] --> G[/health /ready /lab-config]
```

## 7) aruba-switch
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-aruba-switch/ssh_server.py]
  C --> D[state.py]
  C --> E[show version/interfaces/vlans/stp/lldp]
  F[:8080] --> G[/health /ready /lab-config]
```

## 8) router
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-router/ssh_server.py]
  C --> D[state.py]
  C --> E[route/bgp/ospf/nat/acl commands]
  F[:8080] --> G[/health /ready /lab-config]
```

## 9) vyos
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-vyos/ssh_server.py]
  C --> D[state.py]
  C --> E[interfaces/route/bgp/firewall/nat/vpn]
  F[:8080] --> G[/health /ready /lab-config]
```

## 10) wlc
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-wlc/ssh_server.py]
  C --> D[state.py]
  C --> E[wlan/ap/client/rf-tag commands]
  F[:8080] --> G[/health /ready /lab-config]
```

## 11) aruba-ap
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-aruba-ap/ssh_server.py]
  C --> D[state.py]
  C --> E[bss-table/radio/clients/config commands]
  F[:8080] --> G[/health /ready /lab-config]
```

## 12) vpn
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-vpn/ssh_server.py]
  C --> D[state.py]
  C --> E[ipsec status/connection/tunnel commands]
  F[:8080] --> G[/health /ready /lab-config]
```

## 13) snort
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-snort/ssh_server.py]
  C --> D[state.py]
  C --> E[alerts/stats/interfaces commands]
  F[:8080] --> G[/health /ready /lab-config]
```

## 14) ldap
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-ldap/ssh_server.py]
  C --> D[state.py]
  C --> E[ldapsearch/schema/replication commands]
  F[:8080] --> G[/health /ready /lab-config]
```

## 15) nginx
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-nginx/ssh_server.py]
  C --> D[state.py]
  C --> E[nginx -t/-T, logs, ports commands]
  F[:8080] --> G[/health /ready /lab-config]
```

## 16) postgres
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-postgres/ssh_server.py]
  C --> D[state.py]
  C --> E[psql list/version/connections commands]
  F[:8080] --> G[/health /ready /lab-config]
```

## 17) redis-node
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-redis-node/ssh_server.py]
  C --> D[state.py]
  C --> E[redis-cli info/dbsize/config/client list]
  F[:8080] --> G[/health /ready /lab-config]
```

## 18) elasticsearch
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-elasticsearch/ssh_server.py]
  C --> D[state.py]
  C --> E[_cat/indices _cluster/health _nodes/stats]
  F[:8080] --> G[/health /ready /lab-config]
```

## 19) grafana
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-grafana/ssh_server.py]
  C --> D[state.py]
  C --> E[health/datasources/dashboards commands]
  F[:8080] --> G[/health /ready /lab-config]
```

## 20) prometheus
```mermaid
flowchart LR
  A --> B[SSH :22]
  B --> C[lab/mock-prometheus/ssh_server.py]
  C --> D[state.py]
  C --> E[targets/alertmanagers/rules commands]
  F[:8080] --> G[/health /ready /lab-config]
```
