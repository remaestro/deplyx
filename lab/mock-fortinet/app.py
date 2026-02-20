"""Mock Fortinet FortiOS REST API server.

Simulates the FortiOS REST API endpoints used by the deplyx FortinetConnector:
  - GET /api/v2/monitor/system/status   → system info
  - GET /api/v2/cmdb/system/interface   → interfaces
  - GET /api/v2/cmdb/firewall/policy    → firewall policies
  - PUT /api/v2/cmdb/firewall/policy/:id → update policy
"""

import os
from flask import Flask, jsonify, request

app = Flask(__name__)

API_TOKEN = os.getenv("FORTINET_API_TOKEN", "fg-lab-token-001")
HOSTNAME = os.getenv("FORTINET_HOSTNAME", "FG-DC1-01")
SERIAL = os.getenv("FORTINET_SERIAL", "FGT60F0000000001")


def _check_auth():
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401
    return None


# ---------- System status ----------
@app.route("/api/v2/monitor/system/status", methods=["GET"])
def system_status():
    err = _check_auth()
    if err:
        return err
    return jsonify({
        "http_method": "GET",
        "results": {
            "hostname": HOSTNAME,
            "serial": SERIAL,
            "version": "v7.4.3",
            "build": "2573",
            "model_name": "FortiGate-60F",
            "model_number": "FGT60F",
            "log_disk_usage": 12,
            "current_time": "2026-02-18 10:00:00",
        },
        "vdom": "root",
        "status": "success",
    })


# ---------- Interfaces ----------
INTERFACES = [
    {
        "name": "port1",
        "vdom": "root",
        "status": "up",
        "speed": "1000full",
        "ip": "10.0.1.1 255.255.255.0",
        "type": "physical",
        "alias": "WAN",
        "mtu": 1500,
    },
    {
        "name": "port2",
        "vdom": "root",
        "status": "up",
        "speed": "1000full",
        "ip": "10.0.10.1 255.255.255.0",
        "type": "physical",
        "alias": "LAN-SERVERS",
        "mtu": 1500,
    },
    {
        "name": "port3",
        "vdom": "root",
        "status": "up",
        "speed": "1000full",
        "ip": "10.0.20.1 255.255.255.0",
        "type": "physical",
        "alias": "DMZ",
        "mtu": 1500,
    },
    {
        "name": "port4",
        "vdom": "root",
        "status": "down",
        "speed": "auto",
        "ip": "0.0.0.0 0.0.0.0",
        "type": "physical",
        "alias": "SPARE",
        "mtu": 1500,
    },
    {
        "name": "ssl.root",
        "vdom": "root",
        "status": "up",
        "speed": "auto",
        "ip": "10.212.134.200 255.255.255.255",
        "type": "tunnel",
        "alias": "SSL-VPN",
        "mtu": 1500,
    },
]


@app.route("/api/v2/cmdb/system/interface", methods=["GET"])
def interfaces():
    err = _check_auth()
    if err:
        return err
    return jsonify({
        "http_method": "GET",
        "results": INTERFACES,
        "vdom": "root",
        "status": "success",
    })


# ---------- Firewall policies ----------
POLICIES = [
    {
        "policyid": 1,
        "name": "Allow-Web-Traffic",
        "srcintf": [{"name": "port1"}],
        "dstintf": [{"name": "port3"}],
        "srcaddr": [{"name": "all"}],
        "dstaddr": [{"name": "WebServer-DMZ"}],
        "service": [{"name": "HTTP"}, {"name": "HTTPS"}],
        "action": "accept",
        "status": "enable",
        "logtraffic": "all",
        "comments": "Allow inbound web traffic to DMZ",
    },
    {
        "policyid": 2,
        "name": "Allow-DB-Access",
        "srcintf": [{"name": "port3"}],
        "dstintf": [{"name": "port2"}],
        "srcaddr": [{"name": "WebServer-DMZ"}],
        "dstaddr": [{"name": "DB-Server"}],
        "service": [{"name": "PostgreSQL"}],
        "action": "accept",
        "status": "enable",
        "logtraffic": "all",
        "comments": "Allow DMZ web servers to reach database",
    },
    {
        "policyid": 3,
        "name": "Allow-DNS",
        "srcintf": [{"name": "port2"}, {"name": "port3"}],
        "dstintf": [{"name": "port1"}],
        "srcaddr": [{"name": "all"}],
        "dstaddr": [{"name": "DNS-Servers"}],
        "service": [{"name": "DNS"}],
        "action": "accept",
        "status": "enable",
        "logtraffic": "utm",
        "comments": "Allow DNS resolution for servers",
    },
    {
        "policyid": 4,
        "name": "Block-DMZ-to-LAN",
        "srcintf": [{"name": "port3"}],
        "dstintf": [{"name": "port2"}],
        "srcaddr": [{"name": "all"}],
        "dstaddr": [{"name": "all"}],
        "service": [{"name": "ALL"}],
        "action": "deny",
        "status": "enable",
        "logtraffic": "all",
        "comments": "Default deny DMZ to LAN (except DB rule above)",
    },
    {
        "policyid": 5,
        "name": "LEGACY-Any-Any",
        "srcintf": [{"name": "any"}],
        "dstintf": [{"name": "any"}],
        "srcaddr": [{"name": "all"}],
        "dstaddr": [{"name": "all"}],
        "service": [{"name": "ALL"}],
        "action": "accept",
        "status": "enable",
        "logtraffic": "disable",
        "comments": "DANGEROUS: legacy rule, should be removed",
    },
]


@app.route("/api/v2/cmdb/firewall/policy", methods=["GET"])
def firewall_policies():
    err = _check_auth()
    if err:
        return err
    return jsonify({
        "http_method": "GET",
        "results": POLICIES,
        "vdom": "root",
        "status": "success",
    })


@app.route("/api/v2/cmdb/firewall/policy/<int:policy_id>", methods=["GET"])
def firewall_policy_detail(policy_id):
    err = _check_auth()
    if err:
        return err
    pol = next((p for p in POLICIES if p["policyid"] == policy_id), None)
    if pol is None:
        return jsonify({"http_method": "GET", "status": "error", "error": "Policy not found"}), 404
    return jsonify({
        "http_method": "GET",
        "results": [pol],
        "vdom": "root",
        "status": "success",
    })


@app.route("/api/v2/cmdb/firewall/policy/<int:policy_id>", methods=["PUT"])
def update_firewall_policy(policy_id):
    err = _check_auth()
    if err:
        return err
    pol = next((p for p in POLICIES if p["policyid"] == policy_id), None)
    if pol is None:
        return jsonify({"status": "error", "error": "Policy not found"}), 404
    data = request.json or {}
    pol.update(data)
    return jsonify({
        "http_method": "PUT",
        "results": {"mkey": str(policy_id)},
        "vdom": "root",
        "status": "success",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=443, ssl_context="adhoc")
