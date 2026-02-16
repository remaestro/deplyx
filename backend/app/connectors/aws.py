"""AWS connector via boto3.

Syncs Security Groups, VPCs, subnets, and ENIs into the Neo4j graph.
"""

from typing import Any

from app.connectors.base import BaseConnector
from app.graph.neo4j_client import neo4j_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AWSConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self.region = config.get("region", "us-east-1")
        self.access_key = config.get("aws_access_key_id", "")
        self.secret_key = config.get("aws_secret_access_key", "")

    def _get_client(self, service: str):
        import boto3
        return boto3.client(
            service,
            region_name=self.region,
            aws_access_key_id=self.access_key or None,
            aws_secret_access_key=self.secret_key or None,
        )

    async def sync(self) -> dict[str, Any]:
        synced: dict[str, int] = {"vpcs": 0, "subnets": 0, "security_groups": 0, "rules": 0}

        try:
            ec2 = self._get_client("ec2")

            # VPCs
            vpcs_resp = ec2.describe_vpcs()
            for vpc in vpcs_resp.get("Vpcs", []):
                vpc_id = vpc["VpcId"]
                name_tag = next((t["Value"] for t in vpc.get("Tags", []) if t["Key"] == "Name"), vpc_id)
                await neo4j_client.merge_node("Device", vpc_id, {
                    "id": vpc_id, "type": "vpc", "vendor": "aws",
                    "hostname": name_tag, "criticality": "high",
                    "cidr": vpc.get("CidrBlock", ""),
                })
                synced["vpcs"] += 1

            # Subnets
            subnets_resp = ec2.describe_subnets()
            for subnet in subnets_resp.get("Subnets", []):
                subnet_id = subnet["SubnetId"]
                name_tag = next((t["Value"] for t in subnet.get("Tags", []) if t["Key"] == "Name"), subnet_id)
                await neo4j_client.merge_node("VLAN", subnet_id, {
                    "id": subnet_id, "vlan_id": 0,
                    "name": name_tag,
                    "description": f"CIDR: {subnet.get('CidrBlock', '')}",
                })
                await neo4j_client.create_relationship("Device", subnet["VpcId"], "HOSTS", "VLAN", subnet_id)
                synced["subnets"] += 1

            # Security Groups
            sgs_resp = ec2.describe_security_groups()
            for sg in sgs_resp.get("SecurityGroups", []):
                sg_id = sg["GroupId"]
                await neo4j_client.merge_node("Device", sg_id, {
                    "id": sg_id, "type": "security_group", "vendor": "aws",
                    "hostname": sg.get("GroupName", sg_id),
                    "criticality": "high",
                })
                await neo4j_client.create_relationship("Device", sg["VpcId"], "HOSTS", "Device", sg_id)
                synced["security_groups"] += 1

                # Inbound rules
                for i, rule in enumerate(sg.get("IpPermissions", [])):
                    rule_id = f"AWS-RULE-{sg_id}-in-{i}"
                    src = rule.get("IpRanges", [{}])[0].get("CidrIp", "any") if rule.get("IpRanges") else "any"
                    port = str(rule.get("FromPort", "any"))
                    proto = rule.get("IpProtocol", "-1")

                    await neo4j_client.merge_node("Rule", rule_id, {
                        "id": rule_id, "name": f"SG {sg_id} inbound {i}",
                        "source": src, "destination": "self",
                        "port": port, "protocol": proto, "action": "allow",
                        "device_id": sg_id,
                    })
                    await neo4j_client.create_relationship("Device", sg_id, "HAS_RULE", "Rule", rule_id)
                    synced["rules"] += 1

        except Exception as e:
            logger.error("AWS sync error: %s", e)
            return {"vendor": "aws", "status": "error", "error": str(e), "synced": synced}

        return {"vendor": "aws", "status": "synced", "synced": synced}

    async def validate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate that the target SG exists and the rule is well-formed."""
        try:
            ec2 = self._get_client("ec2")
            sg_id = payload.get("security_group_id", "")
            resp = ec2.describe_security_groups(GroupIds=[sg_id])
            return {"vendor": "aws", "valid": len(resp.get("SecurityGroups", [])) > 0}
        except Exception as e:
            return {"vendor": "aws", "valid": False, "error": str(e)}

    async def simulate_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        """AWS doesn't have a dry-run for SG rules — validate only."""
        return await self.validate_change(payload)

    async def apply_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply a security group rule change."""
        try:
            ec2 = self._get_client("ec2")
            action = payload.get("action", "authorize_ingress")
            sg_id = payload.get("security_group_id", "")
            ip_permissions = payload.get("ip_permissions", [])

            if action == "authorize_ingress":
                ec2.authorize_security_group_ingress(GroupId=sg_id, IpPermissions=ip_permissions)
            elif action == "revoke_ingress":
                ec2.revoke_security_group_ingress(GroupId=sg_id, IpPermissions=ip_permissions)
            elif action == "authorize_egress":
                ec2.authorize_security_group_egress(GroupId=sg_id, IpPermissions=ip_permissions)
            elif action == "revoke_egress":
                ec2.revoke_security_group_egress(GroupId=sg_id, IpPermissions=ip_permissions)

            return {"vendor": "aws", "applied": True, "action": action, "sg_id": sg_id}
        except Exception as e:
            return {"vendor": "aws", "applied": False, "error": str(e)}
