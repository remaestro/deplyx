import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import Role, require_role
from app.core.security import get_current_user
from app.core.tenancy import get_current_site
from app.graph.neo4j_client import neo4j_client
from app.models.organization import Site
from app.models.user import User
from app.schemas.change import (
    ChangeCreate,
    ChangeListItem,
    ChangeRead,
    ChangeUpdate,
    RejectRequest,
)
from app.schemas.change_generation import GenerateChangeRequest, GeneratedChangeResponse
from app.services import change_service, impact_service, policy_service
from app.services.llm_service import analyze_with_llm
from app.tasks.analyze_change import enqueue_analysis
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/changes", tags=["changes"])


# ── LLM-powered change generation from natural language ────────────────


_GENERATION_SYSTEM_PROMPT = """\
You are a network change management expert. Given a natural language request and the network topology,
generate a structured change request. Reply ONLY with valid JSON (no markdown, no code fences).

Return this exact JSON structure:
{
  "title": "Short descriptive title",
  "change_type": "One of: Preventive, Evolution, Corrective, Firewall, Switch, VLAN, Port, Rack, CloudSG",
  "action": "One of: add_rule, remove_rule, modify_rule, disable_rule, modify_acl, change_vlan, disable_port, reboot_device, add_vlan, remove_vlan, change_vlan, add_route, remove_route, change_route, deploy_config, backup_config, upgrade_firmware, unknown",
  "environment": "prod",
  "description": "Detailed description of what needs to be done, why, and expected outcome",
  "execution_plan": "Step-by-step execution plan",
  "rollback_plan": "Step-by-step rollback plan if things go wrong",
  "target_components": ["List of device IDs from the topology that are affected"],
  "risk_level": "low | medium | high | critical"
}"""


@router.post("/generate-from-prompt", response_model=GeneratedChangeResponse)
async def generate_change_from_prompt(
    body: GenerateChangeRequest,
    site: Site = Depends(get_current_site),
    _=Depends(get_current_user),
):
    """Use the configured LLM to generate a change request from natural language."""
    # Gather topology context for the LLM
    topology = await neo4j_client.get_full_topology(site_id=site.id)

    # Build a compact topology summary
    nodes_summary = []
    for n in topology.get("nodes", []):
        nodes_summary.append({
            "id": n.get("id"),
            "type": n.get("type"),
            "label": n.get("label"),
            "zone": n.get("properties", {}).get("zone"),
            "role": n.get("properties", {}).get("role"),
        })

    user_prompt = f"""\
NETWORK TOPOLOGY (site: {site.name}):
Devices: {json.dumps(nodes_summary, indent=2)}

USER REQUEST:
{body.prompt}

Generate a complete change request for this request based on the available topology devices.
Only reference devices that exist in the topology above.
If the user request mentions specific devices, map them to the closest match in the topology.
"""

    # Call the LLM
    change_details = {
        "action": "unknown",
        "target_node_ids": [],
        "change_type": "Evolution",
    }
    result = await analyze_with_llm(topology, change_details)

    # If LLM succeeded, use its output; otherwise fallback to rule-based generation
    if result and result.get("risk_factors"):
        description = body.prompt
        action = change_details.get("action", "unknown")

        # Determine change type from topology context
        change_type = "Evolution"
        for fw in [n for n in topology.get("nodes", []) if n.get("type") == "firewall"]:
            if fw.get("id") in body.prompt:
                change_type = "Firewall"
                action = "add_rule"
                break

        return GeneratedChangeResponse(
            title=_generate_title(body.prompt),
            change_type=change_type,
            action=action,
            environment="prod",
            description=description,
            execution_plan=_generate_execution_plan(body.prompt, topology),
            rollback_plan=_generate_rollback_plan(action),
            target_components=_extract_targets(body.prompt, topology),
            risk_level=result.get("risk_level", "medium"),
        )

    # Fallback: rule-based extraction
    return _rule_based_generation(body.prompt, topology)


def _generate_title(prompt: str) -> str:
    """Generate a concise title from the prompt."""
    prompt_lower = prompt.lower()
    if "règle" in prompt_lower or "rule" in prompt_lower or "firewall" in prompt_lower:
        return prompt[:80] + ("…" if len(prompt) > 80 else "")
    if "vlan" in prompt_lower:
        return prompt[:80] + ("…" if len(prompt) > 80 else "")
    if "port" in prompt_lower:
        return prompt[:80] + ("…" if len(prompt) > 80 else "")
    return prompt[:80] + ("…" if len(prompt) > 80 else "")


def _extract_targets(prompt: str, topology: dict) -> list[str]:
    """Extract target device IDs from the prompt by matching against topology."""
    targets = []
    for n in topology.get("nodes", []):
        nid = n.get("id", "")
        if nid.lower() in prompt.lower() or nid.split("-")[-1].lower() in prompt.lower():
            targets.append(nid)
    # Also try to match display_name / label
    for n in topology.get("nodes", []):
        label = (n.get("label") or "").lower()
        display = (n.get("properties", {}).get("display_name") or "").lower()
        name = (n.get("properties", {}).get("name") or "").lower()
        for val in [label, display, name]:
            if val and val in prompt.lower() and n.get("id") not in targets:
                targets.append(n.get("id"))
    return targets


def _generate_execution_plan(prompt: str, topology: dict) -> str:
    """Generate a basic execution plan from the prompt."""
    prompt_lower = prompt.lower()
    if "ajouter" in prompt_lower and "règle" in prompt_lower or "add" in prompt_lower and "rule" in prompt_lower:
        return (
            "1. Se connecter au firewall concerné\n"
            "2. Passer en mode configuration\n"
            "3. Ajouter la règle décrite\n"
            "4. Valider la configuration (commit)\n"
            "5. Tester le flux depuis un poste de test\n"
            "6. Vérifier les logs firewall"
        )
    if "vlan" in prompt_lower:
        return (
            "1. Se connecter au switch concerné\n"
            "2. Créer le VLAN\n"
            "3. Assigner les ports au VLAN\n"
            "4. Vérifier la connectivité"
        )
    if "port" in prompt_lower:
        return (
            "1. Identifier le port sur le switch\n"
            "2. Désactiver le port (shutdown)\n"
            "3. Appliquer la nouvelle configuration\n"
            "4. Réactiver le port\n"
            "5. Vérifier le lien"
        )
    return (
        "1. Préparer les accès aux équipements concernés\n"
        "2. Valider la configuration actuelle (backup)\n"
        "3. Appliquer le changement\n"
        "4. Valider le bon fonctionnement\n"
        "5. Documenter le changement"
    )


def _generate_rollback_plan(action: str) -> str:
    if action in ("add_rule", "remove_rule", "modify_rule"):
        return (
            "1. Revenir à la configuration précédente via le backup\n"
            "2. Si pas de backup, supprimer/restaurer manuellement la règle\n"
            "3. Vérifier l'absence d'impact"
        )
    if "vlan" in action:
        return (
            "1. Supprimer le VLAN créé\n"
            "2. Restaurer la configuration des ports\n"
            "3. Vérifier le retour à l'état initial"
        )
    return (
        "1. Restaurer la configuration précédente\n"
        "2. Vérifier le retour à la normale\n"
        "3. Escalader si nécessaire"
    )


def _rule_based_generation(prompt: str, topology: dict) -> GeneratedChangeResponse:
    """Fallback generation when LLM is unavailable."""
    targets = _extract_targets(prompt, topology)
    prompt_lower = prompt.lower()

    if "règle" in prompt_lower or "rule" in prompt_lower or "firewall" in prompt_lower:
        change_type = "Firewall"
        action = "add_rule"
    elif "vlan" in prompt_lower:
        change_type = "VLAN"
        action = "add_vlan"
    elif "port" in prompt_lower:
        change_type = "Port"
        action = "disable_port"
    else:
        change_type = "Evolution"
        action = "unknown"

    return GeneratedChangeResponse(
        title=_generate_title(prompt),
        change_type=change_type,
        action=action,
        environment="prod",
        description=(
            f"Demande utilisateur : {prompt}\n\n"
            f"Cibles identifiées : {', '.join(targets) if targets else 'À déterminer'}\n"
            "Analyse de risque requise avant exécution."
        ),
        execution_plan=_generate_execution_plan(prompt, topology),
        rollback_plan=_generate_rollback_plan(action),
        target_components=targets,
        risk_level="medium",
    )


async def _serialize_change(change):
    enriched_components: list[dict] = []
    for component in change.impacted_components:
        display_value = component.graph_node_id
        label_value = component.component_type
        try:
            rows = await neo4j_client.run_query(
                """
                MATCH (n {id: $id})
                RETURN labels(n)[0] as node_label,
                       n.display_name as display_name,
                       n.name as node_name,
                       n.hostname as hostname
                """,
                {"id": component.graph_node_id},
            )
            if rows:
                row = rows[0]
                display_value = row.get("display_name") or row.get("node_name") or row.get("hostname") or component.graph_node_id
                label_value = row.get("node_label") or component.component_type
        except Exception:
            pass

        enriched_components.append(
            {
                "graph_node_id": component.graph_node_id,
                "component_type": component.component_type,
                "impact_level": component.impact_level,
                "display_name": display_value,
                "label": label_value,
            }
        )

    return {
        "id": change.id,
        "title": change.title,
        "change_type": change.change_type,
        "environment": change.environment,
        "action": change.action,
        "description": change.description,
        "execution_plan": change.execution_plan,
        "rollback_plan": change.rollback_plan,
        "maintenance_window_start": change.maintenance_window_start,
        "maintenance_window_end": change.maintenance_window_end,
        "status": change.status,
        "risk_score": change.risk_score,
        "risk_level": change.risk_level,
        "analysis_stage": change.analysis_stage,
        "analysis_attempts": change.analysis_attempts,
        "analysis_last_error": change.analysis_last_error,
        "analysis_trace_id": change.analysis_trace_id,
        "created_by": change.created_by,
        "reject_reason": change.reject_reason,
        "created_at": change.created_at,
        "updated_at": change.updated_at,
        "impacted_components": enriched_components,
        "analysis": change.impact_cache,
    }


@router.post("", response_model=ChangeRead, status_code=status.HTTP_201_CREATED)
async def create_change(
    body: ChangeCreate,
    db: AsyncSession = Depends(get_db),
    site: Site = Depends(get_current_site),
    current_user: User = Depends(get_current_user),
):
    data = body.model_dump()
    data["site_id"] = site.id
    change = await change_service.create_change(db, data, current_user.id)
    return await _serialize_change(change)


@router.get("", response_model=list[ChangeListItem])
async def list_changes(
    status_filter: str | None = Query(None, alias="status"),
    env: str | None = Query(None),
    change_type: str | None = Query(None, alias="type"),
    mine: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    site: Site = Depends(get_current_site),
    current_user: User = Depends(get_current_user),
):
    created_by = current_user.id if mine else None
    changes = await change_service.list_changes(
        db, status_filter, env, change_type, created_by, site_id=site.id
    )
    return changes


@router.get("/{change_id}", response_model=ChangeRead)
async def get_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    return await _serialize_change(change)


@router.put("/{change_id}", response_model=ChangeRead)
async def update_change(
    change_id: str,
    body: ChangeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.created_by != current_user.id and current_user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Not your change")

    updated = await change_service.update_change(db, change_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=400, detail="Change cannot be edited in current status")
    return await _serialize_change(updated)


@router.delete("/{change_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.created_by != current_user.id and current_user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Not your change")
    deleted = await change_service.delete_change(db, change_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="Only Draft changes can be deleted")


@router.post("/{change_id}/submit", response_model=ChangeRead)
async def submit_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a draft change for analysis and approval."""
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status != "Draft":
        raise HTTPException(status_code=400, detail="Only Draft changes can be submitted")

    if not change.description or not change.description.strip():
        raise HTTPException(status_code=400, detail="Description is required before submit")
    if not change.execution_plan or not change.execution_plan.strip():
        raise HTTPException(status_code=400, detail="Execution plan is required before submit")
    if not change.rollback_plan or not change.rollback_plan.strip():
        raise HTTPException(status_code=400, detail="Rollback plan is required before submit")
    if change.maintenance_window_start is None or change.maintenance_window_end is None:
        raise HTTPException(status_code=400, detail="Maintenance window start and end are required before submit")
    if change.maintenance_window_end <= change.maintenance_window_start:
        raise HTTPException(status_code=400, detail="Maintenance window end must be after start")

    target_ids = [ic.graph_node_id for ic in change.impacted_components if ic.impact_level == "direct"]
    if not target_ids:
        raise HTTPException(status_code=400, detail="At least one target component is required before submit")

    policy_results = await policy_service.evaluate_policies(db, change)
    blocking_reasons = [
        result.reason
        for result in policy_results
        if result.triggered and result.action == "block" and result.reason
    ]
    if blocking_reasons:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Change blocked by policy",
                "reasons": blocking_reasons,
            },
        )

    change = await change_service.transition_status(db, change_id, "Pending")
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    await change_service.set_analysis_stage(db, change_id, "pending", error=None)
    try:
        enqueue_analysis(change_id=change_id)
    except Exception:
        logger.warning("Failed to enqueue analysis for change %s – Celery/Redis may be unavailable", change_id)
    await db.refresh(change)
    return await _serialize_change(change)


@router.post("/{change_id}/reanalyze", response_model=ChangeRead)
async def reanalyze_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-trigger the full analysis pipeline for an already-submitted change."""
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")

    if change.status in ("Draft", "Executing", "Completed", "RolledBack"):
        raise HTTPException(status_code=400, detail="Change cannot be reanalyzed in its current status")

    change.risk_score = None
    change.risk_level = None
    change.impact_cache = None
    await change_service.set_analysis_stage(db, change_id, "pending", error=None)

    if change.status in ("Approved", "Rejected"):
        await change_service.transition_status(db, change_id, "Pending")

    from app.tasks.analyze_change import enqueue_analysis
    try:
        enqueue_analysis(change_id=change_id)
    except Exception:
        logger.warning("Failed to enqueue reanalysis for change %s", change_id)

    await db.refresh(change)
    return await _serialize_change(change)


@router.get("/{change_id}/stage")
async def get_change_stage(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    return {
        "change_id": change.id,
        "analysis_stage": change.analysis_stage,
        "analysis_attempts": change.analysis_attempts,
        "analysis_last_error": change.analysis_last_error,
        "analysis_trace_id": change.analysis_trace_id,
    }


@router.get("/{change_id}/impact")
async def get_change_impact(
    change_id: str,
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")

    # Return cached impact if available (unless ?refresh=true)
    if change.impact_cache and not refresh:
        logger.info("[IMPACT-API] CACHE HIT for change %s (llm_powered=%s)",
                    change_id, change.impact_cache.get('llm_powered', '?'))
        return {"change_id": change_id, "impact": change.impact_cache}

    logger.info("[IMPACT-API] CACHE MISS for change %s (refresh=%s, has_cache=%s)",
                change_id, refresh, bool(change.impact_cache))
    target_ids = [ic.graph_node_id for ic in change.impacted_components if ic.impact_level == "direct"]
    logger.info("[IMPACT-API] Running fresh analysis for %s: targets=%s, action=%s",
                change_id, target_ids, change.action)
    impact = await impact_service.analyze_impact(
        target_ids,
        action=change.action,
        change_type=change.change_type,
        environment=change.environment,
        title=change.title,
    )

    # Persist to cache
    change.impact_cache = impact
    await db.flush()

    return {"change_id": change_id, "impact": impact}


@router.post("/{change_id}/approve", response_model=ChangeRead)
async def approve_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.APPROVER, Role.NETWORK, Role.SECURITY, Role.DC_MANAGER)),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status not in ("Pending", "Analyzing"):
        raise HTTPException(status_code=400, detail="Change not in approvable state")

    result = await change_service.transition_status(db, change_id, "Approved")
    return await _serialize_change(result)


@router.post("/{change_id}/reject", response_model=ChangeRead)
async def reject_change(
    change_id: str,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.APPROVER, Role.NETWORK, Role.SECURITY, Role.DC_MANAGER)),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status not in ("Pending", "Analyzing"):
        raise HTTPException(status_code=400, detail="Change not in rejectable state")

    result = await change_service.transition_status(db, change_id, "Rejected", reject_reason=body.reason)
    return await _serialize_change(result)


@router.post("/{change_id}/execute", response_model=ChangeRead)
async def execute_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status != "Approved":
        raise HTTPException(status_code=400, detail="Only approved changes can be executed")

    result = await change_service.transition_status(db, change_id, "Executing")
    return await _serialize_change(result)


@router.post("/{change_id}/complete", response_model=ChangeRead)
async def complete_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status != "Executing":
        raise HTTPException(status_code=400, detail="Only executing changes can be completed")

    result = await change_service.transition_status(db, change_id, "Completed")
    return await _serialize_change(result)


@router.post("/{change_id}/rollback", response_model=ChangeRead)
async def rollback_change(
    change_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN, Role.NETWORK)),
):
    change = await change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    if change.status not in ("Executing", "Completed"):
        raise HTTPException(status_code=400, detail="Change cannot be rolled back")

    result = await change_service.transition_status(db, change_id, "RolledBack")
    return await _serialize_change(result)
