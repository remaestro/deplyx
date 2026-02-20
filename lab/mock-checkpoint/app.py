"""Mock Check Point Management API server.

Simulates the Check Point Web API endpoints used by the deplyx CheckPointConnector:
  - POST /web_api/login               → session login → returns sid
  - POST /web_api/logout              → session logout
  - POST /web_api/show-simple-gateways → list gateways
  - POST /web_api/show-access-rulebase → access rules
  - POST /web_api/add-access-rule      → create rule
  - POST /web_api/set-access-rule      → modify rule
"""

import os
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

USERNAME = os.getenv("CHECKPOINT_USER", "admin")
PASSWORD = os.getenv("CHECKPOINT_PASS", "Cp@ssw0rd!")
HOSTNAME = os.getenv("CHECKPOINT_HOSTNAME", "CP-MGMT-01")

# Active sessions
_sessions: dict[str, dict] = {}

# ---------- Auth ----------

@app.route("/web_api/login", methods=["POST"])
def login():
    data = request.json or {}
    user = data.get("user", "")
    pwd = data.get("password", "")
    if user != USERNAME or pwd != PASSWORD:
        return jsonify({"code": "err_login_failed", "message": "Authentication failed"}), 403
    sid = str(uuid.uuid4())
    _sessions[sid] = {"user": user, "domain": data.get("domain", "")}
    return jsonify({
        "sid": sid,
        "uid": "user-001",
        "url": f"https://{HOSTNAME}/web_api",
        "session-timeout": 600,
        "api-server-version": "1.9",
    })


@app.route("/web_api/logout", methods=["POST"])
def logout():
    sid = request.headers.get("X-chkp-sid", "")
    _sessions.pop(sid, None)
    return jsonify({"message": "OK"})


def _check_session():
    sid = request.headers.get("X-chkp-sid", "")
    if sid not in _sessions:
        return jsonify({"code": "err_not_authenticated", "message": "Not authenticated"}), 401
    return None


# ---------- Gateways ----------
GATEWAYS = [
    {
        "uid": "gw-001",
        "name": "GW-DC1-MAIN",
        "type": "simple-gateway",
        "domain": {"name": "SMC User"},
        "ipv4-address": "10.0.0.5",
        "policy": {"name": "Standard"},
        "version": "R81.20",
        "os-name": "Gaia",
        "hardware": "Check Point 6200",
        "sic-status": "communicating",
    },
    {
        "uid": "gw-002",
        "name": "GW-DC2-DR",
        "type": "simple-gateway",
        "domain": {"name": "SMC User"},
        "ipv4-address": "172.16.0.5",
        "policy": {"name": "DR-Policy"},
        "version": "R81.20",
        "os-name": "Gaia",
        "hardware": "Check Point 6200",
        "sic-status": "communicating",
    },
]


@app.route("/web_api/show-simple-gateways", methods=["POST"])
def show_gateways():
    err = _check_session()
    if err:
        return err
    return jsonify({
        "objects": GATEWAYS,
        "from": 1,
        "to": len(GATEWAYS),
        "total": len(GATEWAYS),
    })


# ---------- Access Rulebase ----------
RULEBASE = [
    {
        "uid": "rule-cp-001",
        "type": "access-rule",
        "name": "Allow-HTTPS-Inbound",
        "source": [{"name": "Any"}],
        "destination": [{"name": "Web-Servers"}],
        "service": [{"name": "HTTPS"}],
        "action": {"name": "Accept", "uid": "action-accept"},
        "track": {"type": {"name": "Log"}},
        "enabled": True,
        "comments": "Allow HTTPS traffic to web servers",
    },
    {
        "uid": "rule-cp-002",
        "type": "access-rule",
        "name": "Allow-SSH-Management",
        "source": [{"name": "Admin-Network"}],
        "destination": [{"name": "All-Servers"}],
        "service": [{"name": "ssh"}],
        "action": {"name": "Accept", "uid": "action-accept"},
        "track": {"type": {"name": "Log"}},
        "enabled": True,
        "comments": "SSH access from admin network only",
    },
    {
        "uid": "rule-cp-003",
        "type": "access-rule",
        "name": "Allow-InterDC-VPN",
        "source": [{"name": "DC1-Networks"}],
        "destination": [{"name": "DC2-Networks"}],
        "service": [{"name": "Any"}],
        "action": {"name": "Accept", "uid": "action-accept"},
        "track": {"type": {"name": "Log"}},
        "enabled": True,
        "comments": "Inter-datacenter traffic via VPN",
    },
    {
        "uid": "rule-cp-004",
        "type": "access-rule",
        "name": "Block-All-Default",
        "source": [{"name": "Any"}],
        "destination": [{"name": "Any"}],
        "service": [{"name": "Any"}],
        "action": {"name": "Drop", "uid": "action-drop"},
        "track": {"type": {"name": "Log"}},
        "enabled": True,
        "comments": "Default deny rule — cleanup rule",
    },
    {
        "uid": "rule-cp-005",
        "type": "access-rule",
        "name": "LEGACY-Permit-All",
        "source": [{"name": "Any"}],
        "destination": [{"name": "Any"}],
        "service": [{"name": "Any"}],
        "action": {"name": "Accept", "uid": "action-accept"},
        "track": {"type": {"name": "None"}},
        "enabled": True,
        "comments": "DANGEROUS: legacy rule, no logging, should be removed",
    },
    {
        "uid": "section-001",
        "type": "access-section",
        "name": "Default Section",
    },
]


@app.route("/web_api/show-access-rulebase", methods=["POST"])
def show_access_rulebase():
    err = _check_session()
    if err:
        return err
    data = request.json or {}
    policy_name = data.get("name", "Network")
    return jsonify({
        "uid": "rulebase-001",
        "name": policy_name,
        "rulebase": RULEBASE,
        "from": 1,
        "to": len(RULEBASE),
        "total": len(RULEBASE),
    })


@app.route("/web_api/add-access-rule", methods=["POST"])
def add_access_rule():
    err = _check_session()
    if err:
        return err
    data = request.json or {}
    new_rule = {
        "uid": f"rule-cp-{uuid.uuid4().hex[:6]}",
        "type": "access-rule",
        "name": data.get("name", "New-Rule"),
        "source": data.get("source", [{"name": "Any"}]),
        "destination": data.get("destination", [{"name": "Any"}]),
        "service": data.get("service", [{"name": "Any"}]),
        "action": data.get("action", {"name": "Drop"}),
        "track": {"type": {"name": "Log"}},
        "enabled": True,
        "comments": data.get("comments", ""),
    }
    RULEBASE.insert(-1, new_rule)  # Before the section
    return jsonify(new_rule)


@app.route("/web_api/set-access-rule", methods=["POST"])
def set_access_rule():
    err = _check_session()
    if err:
        return err
    data = request.json or {}
    rule_uid = data.get("uid", "")
    for rule in RULEBASE:
        if rule.get("uid") == rule_uid:
            rule.update({k: v for k, v in data.items() if k != "uid"})
            return jsonify(rule)
    return jsonify({"code": "generic_err_object_not_found", "message": "Rule not found"}), 404


# ---------- Publish ----------
@app.route("/web_api/publish", methods=["POST"])
def publish():
    """Commit staged policy changes — called by checkpoint.py apply_change."""
    err = _check_session()
    if err:
        return err
    task_id = str(uuid.uuid4())
    return jsonify({
        "uid": task_id,
        "task-id": task_id,
        "progress-percentage": 100,
        "sup-change-number": 1,
        "status": "succeeded",
        "type": "async-task",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=443, ssl_context="adhoc")
