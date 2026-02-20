"""Mock Palo Alto PAN-OS API server.

Simulates the PAN-OS XML API and REST API endpoints used by the deplyx PaloAltoConnector:
  - GET /api/?type=op&cmd=<show><system><info>  → system info (XML)
  - GET /api/?type=op&cmd=<show><interface>all  → interfaces (XML)
  - GET /restapi/v10.1/Policies/SecurityRules   → security rules (JSON)
  - POST/PUT /restapi/v10.1/Policies/SecurityRules → create/update rules
  - GET /api/?type=op&cmd=<validate><full>      → commit validation
"""

import os
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

API_KEY = os.getenv("PALOALTO_API_KEY", "pa-lab-apikey-001")
HOSTNAME = os.getenv("PALOALTO_HOSTNAME", "PA-DC1-01")
SERIAL = os.getenv("PALOALTO_SERIAL", "007200001234")

# ---------- XML API ----------
SYSTEM_INFO_XML = f"""<response status="success">
  <result>
    <system>
      <hostname>{HOSTNAME}</hostname>
      <ip-address>10.0.0.1</ip-address>
      <netmask>255.255.255.0</netmask>
      <default-gateway>10.0.0.254</default-gateway>
      <mac-address>00:1B:17:00:01:01</mac-address>
      <serial>{SERIAL}</serial>
      <model>PA-850</model>
      <sw-version>10.1.9</sw-version>
      <family>800</family>
      <uptime>45 days, 12:33:21</uptime>
      <multi-vsys>off</multi-vsys>
      <operational-mode>normal</operational-mode>
    </system>
  </result>
</response>"""

INTERFACES_XML = """<response status="success">
  <result>
    <hw>
      <entry>
        <name>ethernet1/1</name>
        <id>16</id>
        <type>0</type>
        <mac>00:1b:17:00:01:10</mac>
        <speed>1000</speed>
        <duplex>full</duplex>
        <state>up</state>
        <st>10/100/1000</st>
      </entry>
      <entry>
        <name>ethernet1/2</name>
        <id>17</id>
        <type>0</type>
        <mac>00:1b:17:00:01:11</mac>
        <speed>1000</speed>
        <duplex>full</duplex>
        <state>up</state>
        <st>10/100/1000</st>
      </entry>
      <entry>
        <name>ethernet1/3</name>
        <id>18</id>
        <type>0</type>
        <mac>00:1b:17:00:01:12</mac>
        <speed>1000</speed>
        <duplex>full</duplex>
        <state>up</state>
        <st>10/100/1000</st>
      </entry>
      <entry>
        <name>ethernet1/4</name>
        <id>19</id>
        <type>0</type>
        <mac>00:1b:17:00:01:13</mac>
        <speed>0</speed>
        <duplex>auto</duplex>
        <state>down</state>
        <st>10/100/1000</st>
      </entry>
      <entry>
        <name>loopback.1</name>
        <id>100</id>
        <type>0</type>
        <mac>00:00:00:00:00:00</mac>
        <speed>0</speed>
        <duplex>auto</duplex>
        <state>up</state>
        <st>loopback</st>
      </entry>
      <entry>
        <name>tunnel.1</name>
        <id>200</id>
        <type>0</type>
        <mac>00:00:00:00:00:00</mac>
        <speed>0</speed>
        <duplex>auto</duplex>
        <state>up</state>
        <st>IPSec tunnel</st>
      </entry>
    </hw>
  </result>
</response>"""

VALIDATE_XML = """<response status="success">
  <result>
    <msg>
      <line>Configuration is valid</line>
    </msg>
  </result>
</response>"""


@app.route("/api/", methods=["GET"])
def xml_api():
    key = request.args.get("key", "")
    if key != API_KEY:
        return Response(
            '<response status="error"><msg>Invalid credentials</msg></response>',
            content_type="application/xml", status=401,
        )

    api_type = request.args.get("type", "")
    cmd = request.args.get("cmd", "")

    if api_type == "op":
        if "<show><system><info>" in cmd:
            return Response(SYSTEM_INFO_XML, content_type="application/xml")
        elif "<show><interface>" in cmd:
            return Response(INTERFACES_XML, content_type="application/xml")
        elif "<validate>" in cmd:
            return Response(VALIDATE_XML, content_type="application/xml")

    return Response(
        '<response status="error"><msg>Unknown command</msg></response>',
        content_type="application/xml", status=400,
    )


# ---------- REST API ----------
SECURITY_RULES = [
    {
        "@name": "Allow-Outbound-Web",
        "@uuid": "rule-001",
        "from": {"member": ["trust"]},
        "to": {"member": ["untrust"]},
        "source": {"member": ["10.0.10.0/24"]},
        "destination": {"member": ["any"]},
        "service": {"member": ["service-http", "service-https"]},
        "application": {"member": ["web-browsing", "ssl"]},
        "action": "allow",
        "log-start": "yes",
        "log-end": "yes",
        "description": "Allow outbound web traffic from servers",
    },
    {
        "@name": "Allow-DNS",
        "@uuid": "rule-002",
        "from": {"member": ["trust", "dmz"]},
        "to": {"member": ["untrust"]},
        "source": {"member": ["any"]},
        "destination": {"member": ["DNS-Servers"]},
        "service": {"member": ["service-dns"]},
        "application": {"member": ["dns"]},
        "action": "allow",
        "log-start": "no",
        "log-end": "yes",
        "description": "Allow DNS resolution",
    },
    {
        "@name": "Allow-VPN-InterDC",
        "@uuid": "rule-003",
        "from": {"member": ["trust"]},
        "to": {"member": ["vpn-dc2"]},
        "source": {"member": ["10.0.0.0/16"]},
        "destination": {"member": ["172.16.0.0/16"]},
        "service": {"member": ["any"]},
        "application": {"member": ["any"]},
        "action": "allow",
        "log-start": "yes",
        "log-end": "yes",
        "description": "Inter-datacenter VPN traffic",
    },
    {
        "@name": "Block-Untrust-to-Trust",
        "@uuid": "rule-004",
        "from": {"member": ["untrust"]},
        "to": {"member": ["trust"]},
        "source": {"member": ["any"]},
        "destination": {"member": ["any"]},
        "service": {"member": ["any"]},
        "application": {"member": ["any"]},
        "action": "deny",
        "log-start": "yes",
        "log-end": "yes",
        "description": "Default deny untrust to trust",
    },
    {
        "@name": "LEGACY-Permit-All",
        "@uuid": "rule-005",
        "from": {"member": ["any"]},
        "to": {"member": ["any"]},
        "source": {"member": ["any"]},
        "destination": {"member": ["any"]},
        "service": {"member": ["any"]},
        "application": {"member": ["any"]},
        "action": "allow",
        "log-start": "no",
        "log-end": "no",
        "description": "DANGEROUS: legacy any-any rule, must be removed",
    },
]


@app.route("/restapi/v10.1/Policies/SecurityRules", methods=["GET"])
def security_rules():
    api_key = request.headers.get("X-PAN-KEY", "")
    if api_key != API_KEY:
        return jsonify({"@status": "error", "msg": "Invalid API key"}), 401
    return jsonify({
        "@status": "success",
        "@code": "19",
        "result": {
            "@total-count": str(len(SECURITY_RULES)),
            "entry": SECURITY_RULES,
        },
    })


@app.route("/restapi/v10.1/Policies/SecurityRules", methods=["POST"])
def create_security_rule():
    api_key = request.headers.get("X-PAN-KEY", "")
    if api_key != API_KEY:
        return jsonify({"@status": "error", "msg": "Invalid API key"}), 401
    rule_name = request.args.get("name", "")
    data = request.json or {}
    entry = data.get("entry", {})
    entry["@name"] = rule_name
    SECURITY_RULES.append(entry)
    return jsonify({"@status": "success", "@code": "20", "msg": "command succeeded"})


@app.route("/restapi/v10.1/Policies/SecurityRules", methods=["PUT"])
def update_security_rule():
    api_key = request.headers.get("X-PAN-KEY", "")
    if api_key != API_KEY:
        return jsonify({"@status": "error", "msg": "Invalid API key"}), 401
    rule_name = request.args.get("name", "")
    for i, rule in enumerate(SECURITY_RULES):
        if rule.get("@name") == rule_name:
            data = request.json or {}
            SECURITY_RULES[i].update(data.get("entry", {}))
            return jsonify({"@status": "success", "msg": "command succeeded"})
    return jsonify({"@status": "error", "msg": "Rule not found"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=443, ssl_context="adhoc")
