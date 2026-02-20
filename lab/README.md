# Deplyx Lab — Virtual Enterprise Network

Lab d'infrastructure réseau virtuelle pour tester les connecteurs deplyx.
**Une seule machine Contabo suffit** — tous les équipements réseau sont simulés dans des containers Docker séparés, chacun avec sa propre IP, exactement comme dans un vrai réseau d'entreprise.

## Architecture

```
Machine Contabo (1 seule) — Ubuntu + Docker
│
├── Réseau lab-net: 10.100.0.0/24
│
│   ── ÉQUIPEMENTS RÉSEAU (mock devices) ──
│   │
│   ├── 10.100.0.10  FW-DC1-01     Fortinet FortiGate 60F    HTTPS API (443)
│   ├── 10.100.0.11  PA-DC1-01     Palo Alto PA-850          HTTPS API (443)
│   ├── 10.100.0.12  CP-MGMT-01    Check Point R81.20        HTTPS API (443)
│   ├── 10.100.0.20  SW-DC1-CORE   Cisco Catalyst 9300       SSH (22)
│   └── 10.100.0.21  SW-DC2-CORE   Juniper EX4300            SSH (22)
│
│   ── DEPLYX (application principale, hors lab/) ──
│   │
│   ├── Backend       FastAPI                   HTTP (8000)
│   ├── Frontend      React/Vite                HTTP (5173)
│   ├── Neo4j         Graph DB                  Bolt (7687)
│   ├── PostgreSQL    Relational DB             TCP (5432)
│   └── Redis         Queue                     TCP (6379)
```

## Comment ça marche

Chaque équipement réseau est un container Docker séparé qui **répond exactement comme le vrai équipement** :

| Équipement | Protocole | Ce qui est simulé |
|---|---|---|
| **Fortinet** | REST API HTTPS | Status système, interfaces (port1-4, SSL-VPN), 5 policies firewall |
| **Palo Alto** | XML + REST API HTTPS | System info, 6 interfaces (eth, loopback, tunnel), 5 security rules |
| **Check Point** | Web API HTTPS (session) | Login/logout, 2 gateways, 5 access rules |
| **Cisco** | SSH (NAPALM ios) | show commands: version, interfaces, VLANs (7), running-config, ARP, CDP |
| **Juniper** | SSH (NAPALM junos) | show commands: version, interfaces, VLANs (5), config, ARP, LLDP |

Ton outil deplyx se connecte à chaque machine séparément (SSH ou API), récupère les configs, et construit le graphe d'impact dans Neo4j.

## Plan Contabo recommandé

| Plan | vCPU | RAM | SSD | Prix | VMs simulées |
|---|---|---|---|---|---|
| **VPS S** | 4 | 8 Go | 200 Go | ~5 €/mois | 3-5 devices |
| **VPS M** ⭐ | 6 | 16 Go | 400 Go | ~11 €/mois | 5-10 devices |
| **VPS L** | 8 | 24 Go | 800 Go | ~17 €/mois | 10-20 devices |

**Recommandé : VPS M (6 vCPU, 16 Go RAM) à ~11 €/mois**
> Le lab utilise environ 2 Go de RAM et 3 Go de disque.

## Installation sur Contabo

### 1. Commander un VPS

- Aller sur [contabo.com](https://contabo.com)
- Choisir **VPS M** (ou plus grand)
- OS : **Ubuntu 24.04**
- Région : Europe (au plus proche)

### 2. Se connecter au VPS

```bash
ssh root@<IP-DU-VPS>
```

### 3. Installer le lab

```bash
# Copier ton code sur le serveur
git clone <ton-repo> /opt/deplyx
# Ou avec scp :
scp -r ./deplyx root@<IP-DU-VPS>:/opt/deplyx

# Lancer le script d'installation
cd /opt/deplyx/lab
chmod +x setup-contabo.sh
sudo ./setup-contabo.sh
```

### 4. Démarrer le lab (mock devices uniquement)

```bash
cd /opt/deplyx/lab
docker compose up -d --build
```

### 5. Enregistrer les devices dans deplyx (stack principale)

```bash
# Depuis le repo, avec le backend principal sur :8000
python3 register-devices.py
```

## Utilisation

### Accès aux interfaces

| Service | URL |
|---|---|
| Frontend principal | `http://<IP-VPS>:5173` |
| Backend API principal | `http://<IP-VPS>:8000/docs` |
| Neo4j Browser principal | `http://<IP-VPS>:7474` |

### Tester un connecteur manuellement

```bash
# API Fortinet (comme en prod)
curl -k -H "Authorization: Bearer fg-lab-token-001" \
  https://10.100.0.10/api/v2/monitor/system/status | jq
```

### Syncer un connecteur via l'API

```bash
# Lister les connecteurs
curl -s http://localhost:8000/api/v1/connectors \
  -H "Authorization: Bearer <TOKEN>" | jq

# Sync un connecteur (id=1)
curl -X POST http://localhost:8000/api/v1/connectors/1/sync \
  -H "Authorization: Bearer <TOKEN>"
```

## Configs embarquées dans les mock devices

Chaque mock device contient des configs réalistes avec des éléments que deplyx peut analyser :

### Firewall Rules (risques intentionnels)
- `LEGACY-Any-Any` — Règle dangereuse any→any (Fortinet policy #5)
- `LEGACY-Permit-All` — Même chose côté PaloAlto (rule #5)
- `LEGACY-Permit-All` — Même chose côté CheckPoint (rule #5)

### VLANs
- VLAN 10/110 : SERVERS
- VLAN 20/120 : DMZ
- VLAN 30/130 : MANAGEMENT
- VLAN 100/140 : DATABASE
- VLAN 200/150 : BACKUP

### Interfaces
- Cisco : 4 GbE + 1 Vlan interface
- Juniper : 4 ge + irb + loopback
- Fortinet : 4 ports + SSL-VPN tunnel
- PaloAlto : 4 ethernet + loopback + tunnel

## Ajouter plus de devices

Pour ajouter un nouveau mock device (ex: un 2ème switch Cisco) :

1. Dupliquer le dossier `mock-cisco/`
2. Modifier les variables d'environnement dans `docker-compose.yml`
3. Attribuer une nouvelle IP (ex: `10.100.0.22`)

Exemple dans `docker-compose.yml` :
```yaml
  sw-dc1-acc01:
    build: ./mock-cisco
    container_name: sw-dc1-acc01
    hostname: SW-DC1-ACC01
    environment:
      CISCO_HOSTNAME: "SW-DC1-ACC01"
      SSH_USER: "admin"
      SSH_PASS: "Cisco123!"
    networks:
      lab-net:
        ipv4_address: 10.100.0.22
```

## Structure du lab

```
lab/
├── docker-compose.yml           # Orchestre tout le lab
├── setup-contabo.sh             # Script d'installation Contabo
├── register-devices.py          # Enregistre les devices dans deplyx
├── .env.devices                 # Credentials de tous les devices
│
├── mock-fortinet/               # Simule FortiGate (REST API Flask)
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
│
├── mock-paloalto/               # Simule PAN-OS (XML + REST API Flask)
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
│
├── mock-checkpoint/             # Simule Check Point (Web API Flask)
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
│
├── mock-cisco/                  # Simule IOS switch (SSH server)
│   ├── Dockerfile
│   ├── ssh_server.py
│   └── requirements.txt
│
└── mock-juniper/                # Simule JunOS switch (SSH server)
    ├── Dockerfile
    ├── ssh_server.py
    └── requirements.txt
```

## FAQ

**Q: Est-ce que j'ai besoin de Proxmox ?**
> Non. Docker suffit amplement. Proxmox serait utile si tu voulais faire tourner de vrais OS complets (Windows, etc.), mais pour simuler des équipements réseau les containers Docker sont plus légers et plus rapides.

**Q: Les connecteurs NAPALM fonctionnent avec les mock SSH ?**
> Les mock SSH répondent aux mêmes `show` commands que les vrais équipements. Pour une compatibilité complète avec NAPALM, tu peux aussi utiliser le driver `mock` de NAPALM en mode fichier, mais les mock SSH sont plus réalistes car ils simulent une vraie connexion réseau.

**Q: Combien de devices je peux simuler ?**
> Avec 16 Go RAM : 20-30 devices facilement. Chaque mock device utilise ~50 Mo de RAM.

**Q: Comment tester l'impact des changements ?**
> 1. Sync tous les connecteurs → le graphe Neo4j se remplit
> 2. Crée un change request dans deplyx (ex: "disable VLAN 10")
> 3. Le risk engine traverse le graphe et calcule l'impact
> 4. Tu vois les composants affectés et le score de risque
