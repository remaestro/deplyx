#!/usr/bin/env python3
"""Quick script to test LLM impact analysis on all 3 changes."""
import json
import sys
import time
import urllib.request

BASE = "http://localhost:8000/api/v1"

def login():
    data = json.dumps({"email": "llmtest@deplyx.io", "password": "TestPass123!"}).encode()
    req = urllib.request.Request(f"{BASE}/auth/login", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)["access_token"]

def get_impact(token, cid, label):
    req = urllib.request.Request(
        f"{BASE}/changes/{cid}/impact",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)

    impact = data.get("impact", {})
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"  Change ID: {cid}")
    print(f"  LLM Powered: {impact.get('llm_powered')}")
    print(f"{'='*70}")

    if not impact.get("llm_powered"):
        print("  *** LLM did not run - graph-only fallback ***")
        print(f"  Graph found {impact.get('total_dependency_count', 0)} dependencies")
        print(f"  Max criticality: {impact.get('max_criticality', 'N/A')}")
        print(f"  Traversal: {impact.get('traversal_strategy', 'N/A')}")
        print(f"  Critical paths (graph): {len(impact.get('critical_paths', []))}")
        return impact

    # Action Analysis
    aa = impact.get("action_analysis", {})
    if aa:
        print(f"\n  ACTION ANALYSIS:")
        for k, v in aa.items():
            print(f"    {k}: {v}")

    # Risk Assessment
    ra = impact.get("risk_assessment", {})
    if ra:
        print(f"\n  RISK ASSESSMENT:")
        for k, v in ra.items():
            if isinstance(v, list):
                print(f"    {k}:")
                for item in v:
                    if isinstance(item, dict):
                        desc = item.get("factor", item.get("name", item.get("description", item.get("action", str(item)))))
                        print(f"      - {desc}")
                    else:
                        print(f"      - {item}")
            else:
                print(f"    {k}: {v}")

    # Blast Radius
    br = impact.get("blast_radius", {})
    if br:
        print(f"\n  BLAST RADIUS:")
        for k, v in br.items():
            print(f"    {k}: {v}")

    # Critical Paths
    paths = impact.get("critical_paths", [])
    if paths:
        print(f"\n  CRITICAL PATHS ({len(paths)}):")
        for i, p in enumerate(paths, 1):
            nodes = p.get("nodes", p.get("path", []))
            if nodes and isinstance(nodes[0], dict):
                chain = " -> ".join(n.get("id", "?") for n in nodes)
            else:
                chain = " -> ".join(str(n) for n in nodes)
            crit = p.get("criticality", "?")
            reasoning = p.get("reasoning", "")
            print(f"    {i}. [{crit}] {chain}")
            if reasoning:
                print(f"       Reason: {reasoning}")

    return impact


def main():
    # If a specific change index is provided, only test that one
    test_idx = int(sys.argv[1]) if len(sys.argv) > 1 else None
    
    changes = [
        ("b70fe4e3-8eef-4611-b7e1-ed5326d78496", "CHANGE 1: Remove HTTP rule (RULE-DC1-01) on DC1 firewall"),
        ("fa674d15-43c6-427a-b252-9004440f4c5a", "CHANGE 2: Decommission core switch SW-DC1-CORE"),
        ("1b13557b-2d23-4c4d-9287-c7d4f827b676", "CHANGE 3: Delete VLAN-20 Production"),
    ]
    
    if test_idx is not None:
        changes = [changes[test_idx - 1]]

    token = login()
    print(f"Authenticated. Testing {len(changes)} change(s)...")

    results = []
    for i, (cid, label) in enumerate(changes):
        if i > 0:
            print(f"\n  ... waiting 5s ...")
            time.sleep(5)
        result = get_impact(token, cid, label)
        results.append((label, result))

    # Summary
    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    for label, r in results:
        llm = r.get("llm_powered", False)
        deps = r.get("total_dependency_count", 0)
        crit = r.get("max_criticality", "N/A")
        paths = len(r.get("critical_paths", []))
        sev = r.get("risk_assessment", {}).get("severity", "N/A") if llm else "N/A (graph-only)"
        print(f"  {label}")
        print(f"    LLM: {'Yes' if llm else 'No'} | Deps: {deps} | Criticality: {crit} | Paths: {paths} | Risk: {sev}")


if __name__ == "__main__":
    main()
