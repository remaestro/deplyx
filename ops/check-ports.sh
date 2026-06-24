#!/usr/bin/env bash
set -euo pipefail

DEPLYX_PORTS=(8100 5180 8101 5452 7475 7688 6381)

echo "=== Projets en cours (via Podman) ==="
podman ps --format '{{.Names}}|{{.Ports}}|{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null | while IFS='|' read -r name ports project dir; do
  if [ -n "$project" ]; then
    echo "  $name"
    echo "    Projet : $project"
    echo "    Dossier: $dir"
    echo "    Ports   : $ports"
    echo ""
  fi
done

echo "=== Tous les ports en écoute ==="
lsof -iTCP -sTCP:LISTEN -P 2>/dev/null | awk 'NR>1 {print $1, $9}' | sort -u -k2

echo ""
echo "=== Ports par défaut de deplyx ==="
for port in "${DEPLYX_PORTS[@]}"; do
  proc=$(lsof -iTCP:"$port" -sTCP:LISTEN -P 2>/dev/null | awk 'NR>1 {print $1}' | sort -u | tr '\n' ' ')
  if [ -n "$proc" ]; then
    echo "  :$port  occupé par $proc"
  else
    echo "  :$port  libre"
  fi
done
