"""LLM-powered impact analysis.

Supports multiple providers:
- Google Gemini (via google.generativeai)
- OpenAI-compatible APIs (DeepSeek, opencode, etc.) via httpx

Falls back to rule-based analysis if the LLM is unavailable or returns invalid JSON.
"""

import asyncio
import json
import time
from typing import Any

import httpx

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_model = None

# Models to try in order — 2.0-flash is much faster for structured JSON output;
# 2.5-flash has "thinking" overhead that adds 30-50s latency.
_MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-001",
    "gemini-flash-latest",
]


class _TruncatedResponseError(Exception):
    """Raised when Gemini truncates its output (finish_reason=MAX_TOKENS)."""
    pass


def _get_model():
    """Lazy-init Gemini model to avoid import errors when key is absent."""
    global _model
    if _model is not None:
        return _model

    api_key = settings.gemini_api_key
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — LLM analysis unavailable")
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel(_MODEL_CANDIDATES[0])
        logger.info("Gemini model initialized: %s", _MODEL_CANDIDATES[0])
        return _model
    except Exception as e:
        logger.error("Failed to initialize Gemini: %s", e)
        return None


def _get_fallback_model(model_name: str):
    """Get a specific model by name for fallback."""
    try:
        import google.generativeai as genai
        return genai.GenerativeModel(model_name)
    except Exception:
        return None


SYSTEM_PROMPT = """\
You are a senior network infrastructure engineer and risk analyst for Deplyx, \
an enterprise network change management platform.

You will receive:
1. A JSON snapshot of the network topology (nodes and edges from a Neo4j graph)
2. Details of a proposed infrastructure change (action, type, target components)

Your job is to perform a **complete impact analysis** by reasoning about the \
topology graph. Think like you are tracing packets and dependencies through the \
network.

## CRITICAL: Classify the impact type

The `action` field tells you what kind of change is being made. **NOT all actions \
cause traffic disruption.** Classify the action into one of these categories:

### Category A — Policy-only changes (LOW risk of traffic disruption)
`add_rule`, `remove_rule`, `modify_rule`, `disable_rule`, `modify_acl`, `modify_sg`
- These modify firewall/security policy, they do NOT physically disrupt connectivity
- **Stateful firewall behaviour**: Modern firewalls (FTD, FortiGate, Palo Alto, etc.) \
  maintain stateful session tables. Removing or modifying a rule does NOT drop existing \
  established connections — only NEW connection attempts are affected. The impact is \
  gradual as sessions time out.
- Risk is about **loss of protection** (e.g. an app behind the firewall becomes exposed), \
  not about connectivity loss. Trace PROTECTS edges to find apps that lose protection.
- If the rule being removed/modified has NOT been hit recently (low hit count), the \
  real-world impact is minimal.
- For these actions, the blast radius is about SECURITY EXPOSURE, not downtime.

### Category B — Traffic-impacting changes (HIGH risk of disruption)
`reboot_device`, `decommission`, `firmware_upgrade`, `shutdown_interface`, \
`disable_port`, `config_change`
- These physically disrupt connectivity. The device/interface goes down.
- Trace ALL connected paths for full blast radius.
- Every device, application, and service that depends on this path is at risk of downtime.
- Consider whether the target has redundancy (HA pair, secondary path, VRRP/HSRP).

### Category C — L2/L3 topology changes (MEDIUM risk)
`change_vlan`, `delete_vlan`, `modify_vlan`, `enable_port`
- These affect layer-2 or layer-3 connectivity but may not cause complete disruption.
- VLAN changes affect all devices on that VLAN. Check if the VLAN is used for \
  management, user traffic, or both.
- Port enable is typically benign unless it creates a loop (check STP).

## Stateful firewall deep-dive

For ANY action on a firewall device:
- Stateful firewalls track connection state in a session table.
- **Removing a rule does NOT tear down existing sessions.** The sessions remain until \
  they naturally expire (typically 60-3600s depending on protocol).
- Risk of traffic loss from rule removal is limited to NEW flows that would have \
  matched that rule.
- However, if ALL rules permitting traffic to an application are removed, the \
  application will become unreachable for new connections once existing sessions expire.
- For `disable_rule`: the rule is just disabled (kept in config), easily reverted.
- For `remove_rule`: the rule is deleted, harder to revert but still just a policy change.
- Factor the FIREWALL MODEL into your reasoning if available from topology data \
  (FTD/FortiGate/PaloAlto all handle stateful sessions slightly differently).

## Redundancy & risk context

The change details may include a `redundancy_analysis` object with pre-computed data \
showing which affected applications still have alternate protection from other \
firewalls/rules or alternate network paths. You MUST use this data to:
- Set `blast_radius.redundancy_available` accurately (true if ANY app has alt protection)
- Write a detailed `blast_radius.redundancy_details` explaining which apps are still \
  protected by which other firewalls/rules, and which apps become fully exposed
- Factor redundancy into your `risk_assessment.severity` — an app with alternate \
  protection is less critical than one that becomes a single point of failure
- Mention redundancy in `risk_assessment.factors` and `mitigations`

Return a JSON object with EXACTLY this structure (no markdown, no extra keys):
{
  "critical_paths": [
    {
      "source_id": "<target node id>",
      "endpoint_id": "<impacted endpoint id>",
      "endpoint_label": "<node type: Device|Application|Service|VLAN|...>",
      "criticality": "critical|high|medium|low",
      "hops": <number of hops>,
      "path_description": "<one-line description of dependency chain>",
      "nodes": [{"id": "<id>", "label": "<type>"}],
      "edges": [{"type": "<rel type>", "source": "<from id>", "target": "<to id>"}],
      "reasoning": "<why this path matters for this specific action, factoring action category>"
    }
  ],
  "risk_assessment": {
    "severity": "critical|high|medium|low",
    "summary": "<2-3 sentence risk summary that accounts for action category>",
    "factors": ["<factor 1>", "<factor 2>", ...],
    "mitigations": ["<mitigation 1>", "<mitigation 2>", ...]
  },
  "blast_radius": {
    "total_impacted": <number>,
    "critical_services_at_risk": ["<service/app id>", ...],
    "redundancy_available": true|false,
    "redundancy_details": "<explanation of failover options>"
  },
  "action_analysis": {
    "action": "<the change action>",
    "traversal_strategy": "<what kind of traversal makes sense>",
    "explanation": "<why this traversal strategy is appropriate, including action category>"
  }
}

Rules:
- Order critical_paths by criticality (critical first, then high, medium, low)
- Only include paths that are ACTUALLY affected by the specific action
- For Category A (policy) actions: focus on PROTECTS edges and security exposure, \
  NOT connectivity loss. Mark criticality lower than you would for traffic-impacting changes.
- For Category B (traffic-impacting) actions: trace all CONNECTED_TO and DEPENDS_ON \
  edges. Be thorough — this is a real outage risk.
- For Category C (L2/L3) actions: trace VLAN membership and adjacency.
- **Criticality scaling**: A policy change that exposes an app should be "medium" at \
  worst unless there is zero redundancy AND the app is business-critical. A traffic-impacting \
  change on a core device without HA should be "critical".
- **Device role context**: Each node has a `role` field that indicates its function \
  (core-router, distribution-switch, access-switch, firewall, wlc, ap, router, switch). \
  Use this to calibrate your risk assessment:
  * `core-router` / `distribution-switch` — Higher risk: these devices carry aggregated \
    traffic from many downstream devices. An outage affects a large blast radius.
  * `access-switch` — Lower risk: only affects the end-users/devices directly connected.
  * `firewall` — Risk depends on action category (policy change vs device reboot).
  * `wlc` / `ap` — Medium risk: affects wireless clients but not wired infrastructure.
  * If no role is shown, infer it from the device's position in the graph topology \
    (how many edges, what kind of neighbors, upstream/downstream position).
- **Device-level redundancy**: Each node may have `has_redundancy` (true/false) and \
  `redundancy_protocol` (e.g. "hsrp_2_groups", "etherchannel_3_channels", "SSO") fields. \
  Use these to determine if a device is a single point of failure (SPOF):
  * `has_redundancy: true` with HSRP/VRRP groups means another router can take over \
    if this one fails — lower the criticality for traffic-impacting changes on this device.
  * `has_redundancy: true` with EtherChannel means the link aggregation has multiple \
    member links — a single link failure won't disrupt connectivity.
  * `has_redundancy: false` on a core-router or distribution-switch means it's a SPOF \
    — any traffic-impacting change on it is HIGH or CRITICAL risk.
- **ACLs on interfaces**: Interface nodes may have `acl_in` and `acl_out` properties \
  indicating which access-lists are applied inbound/outbound. Use this to determine \
  if a proposed ACL change would actually affect traffic on a given interface:
  * If a rule change targets an ACL that is NOT applied to any interface, the impact \
    is LOW (the ACL exists but is not actively filtering).
  * If an ACL is applied inbound on an interface facing a specific device, only that \
    device's traffic is affected.
  * ACLs applied to management interfaces (Vlan1, Mgmt) have limited blast radius.
- **Services/Listening ports**: Device nodes may have a `services` field (JSON array) \
  listing detected services (HTTP, HTTPS, SSH, etc.) with `name`, `protocol`, `port`, \
  and `enabled` status. Use this to determine if a proposed rule/ACL change would \
  actually affect a running service:
  * If a rule blocks port 80 but the device has `services: [{"name": "http", "enabled": false}]`, \
    the impact is LOW — HTTP is not running.
  * If the device has HTTP enabled, blocking port 80 would impact management access.
  * Services running on management interfaces (Vlan1, Mgmt) affect only administrative access.
- Be specific about WHY each path is critical for this particular action, referencing \
  the action category, device role, and redundancy status in your reasoning.
- Return ONLY valid JSON, no markdown fences, no comments
"""


async def _try_model(model, user_prompt: str, model_name: str = "unknown", max_output_tokens: int = 16384) -> dict[str, Any] | None:
    """Attempt a single Gemini call and parse the JSON response."""
    t0 = time.monotonic()
    logger.info("[LLM-DIAG] >>> Sending request to %s (prompt: %d chars, max_tokens: %d)",
                model_name, len(user_prompt), max_output_tokens)

    response = await model.generate_content_async(
        [SYSTEM_PROMPT, user_prompt],
        generation_config={
            "temperature": 0.1,
            "max_output_tokens": max_output_tokens,
            "response_mime_type": "application/json",
        },
    )

    t_response = time.monotonic() - t0

    # Log response metadata
    finish_reason = "N/A"
    candidate_count = 0
    if hasattr(response, "candidates") and response.candidates:
        candidate_count = len(response.candidates)
        finish_reason = str(getattr(response.candidates[0], "finish_reason", "unknown"))
    logger.info("[LLM-DIAG] <<< Response from %s in %.1fs — candidates: %d, finish_reason: %s",
                model_name, t_response, candidate_count, finish_reason)

    # Get the raw text — handle candidates structure
    text = ""
    try:
        text = response.text.strip()
    except Exception as text_err:
        logger.warning("[LLM-DIAG] response.text failed (%s), trying candidates directly", text_err)
        # Fallback: try extracting from candidates directly
        if hasattr(response, "candidates") and response.candidates:
            parts = response.candidates[0].content.parts
            text = "".join(p.text for p in parts if hasattr(p, "text")).strip()

    logger.info("[LLM-DIAG] Raw text length: %d chars, starts_with: %.80s",
                len(text), repr(text[:80]) if text else "<empty>")

    if not text:
        logger.error("[LLM-DIAG] EMPTY response from %s after %.1fs", model_name, t_response)
        return None

    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3].strip()
    if text.startswith("json"):
        text = text[4:].strip()

    try:
        parsed = json.loads(text)
        t_total = time.monotonic() - t0
        logger.info("[LLM-DIAG] JSON parsed OK in %.1fs total — keys: %s",
                    t_total, list(parsed.keys()))
        return parsed
    except json.JSONDecodeError as e:
        t_total = time.monotonic() - t0
        # Check if truncation caused the parse failure (finish_reason 2 = MAX_TOKENS)
        is_truncated = finish_reason in ("2", "MAX_TOKENS", "FinishReason.MAX_TOKENS")
        logger.error("[LLM-DIAG] JSON PARSE FAILED after %.1fs: %s (truncated=%s)",
                     t_total, e, is_truncated)
        logger.error("[LLM-DIAG] Response length: %d chars, finish_reason: %s", len(text), finish_reason)
        logger.error("[LLM-DIAG] First 500 chars: %s", text[:500])
        logger.error("[LLM-DIAG] Last 500 chars : %s", text[-500:] if len(text) > 500 else "(same as above)")
        if is_truncated:
            raise _TruncatedResponseError(
                f"Response truncated at {len(text)} chars (finish_reason={finish_reason})"
            )
        raise


async def _call_openai_compatible(prompt: str, user_prompt: str) -> dict[str, Any] | None:
    """Call an OpenAI-compatible API (DeepSeek, opencode, etc.) via httpx."""
    api_key = settings.llm_api_key or ""
    base_url = settings.llm_base_url.rstrip("/")
    model = settings.llm_model

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }

    t0 = time.monotonic()
    logger.info("[LLM-DIAG] >>> Sending request to %s model=%s (prompt: %d chars)",
                base_url, model, len(prompt) + len(user_prompt))

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.error("[LLM-DIAG] OpenAI-compatible call FAILED: %s", str(e)[:300])
        return None

    t_response = time.monotonic() - t0
    logger.info("[LLM-DIAG] <<< Response in %.1fs", t_response)

    # Extract content from the standard OpenAI chat format
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        logger.error("[LLM-DIAG] Unexpected response format: %s — %s", e, str(data)[:300])
        return None

    if not text:
        logger.error("[LLM-DIAG] Empty response")
        return None

    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3].strip()
    if text.startswith("json"):
        text = text[4:].strip()

    try:
        parsed = json.loads(text)
        logger.info("[LLM-DIAG] JSON parsed OK in %.1fs total — keys: %s",
                    time.monotonic() - t0, list(parsed.keys()))
        return parsed
    except json.JSONDecodeError as e:
        logger.error("[LLM-DIAG] JSON parse FAILED: %s — text[:300]=%s", e, text[:300])
        return None


async def _is_provider_available() -> bool:
    """Check if the configured LLM provider is available."""
    provider = settings.llm_provider.strip().lower()
    if provider == "gemini":
        return settings.gemini_api_key != ""
    elif provider == "openai_compatible":
        return settings.llm_base_url != "" and settings.llm_model != ""
    return False


async def analyze_with_llm(
    topology: dict[str, Any],
    change_details: dict[str, Any],
) -> dict[str, Any] | None:
    """Send topology + change context to configured LLM provider and parse structured response.

    Supports Gemini (native) and OpenAI-compatible providers (DeepSeek, opencode, etc.).
    Returns None if all attempts fail — caller should fall back.
    """
    t_start = time.monotonic()
    provider = settings.llm_provider.strip().lower()

    user_prompt = _build_prompt(topology, change_details)
    logger.info("[LLM-DIAG] ========== NEW ANALYSIS REQUEST ==========")
    logger.info("[LLM-DIAG] Provider: %s, Change: action=%s, targets=%s, type=%s",
                provider, change_details.get("action"), change_details.get("target_node_ids"), change_details.get("change_type"))
    logger.info("[LLM-DIAG] Topology: %d nodes, %d edges",
                len(topology.get("nodes", [])), len(topology.get("edges", [])))
    logger.info("[LLM-DIAG] Prompt size: %d chars", len(user_prompt))

    # ── OpenAI-compatible provider path (openai_compatible, opencode) ──
    if provider in ("openai_compatible", "opencode"):
        result = await _call_openai_compatible(SYSTEM_PROMPT, user_prompt)
        if result:
            t_total = time.monotonic() - t_start
            paths = len(result.get("critical_paths", [])) if result else 0
            logger.info("[LLM-DIAG] SUCCESS (OpenAI-compatible, %.1fs total): %d critical paths",
                        t_total, paths)
            return result
        logger.error("[LLM-DIAG] OpenAI-compatible provider returned no result")
        return None

    # ── Gemini provider path ─────────────────────────────────────
    model = _get_model()
    if model is None:
        logger.warning("[LLM-DIAG] No Gemini model available (API key missing?)")
        return None

    # Try primary model with retry
    max_tokens = 8192
    for attempt in range(3):
        try:
            result = await _try_model(model, user_prompt, model_name=_MODEL_CANDIDATES[0],
                                       max_output_tokens=max_tokens)
            t_total = time.monotonic() - t_start
            paths = len(result.get("critical_paths", [])) if result else 0
            logger.info("[LLM-DIAG] SUCCESS (%s, attempt %d, %.1fs total): %d critical paths",
                        _MODEL_CANDIDATES[0], attempt + 1, t_total, paths)
            return result
        except _TruncatedResponseError as e:
            # Response was cut off — retry with 2x tokens
            max_tokens = min(max_tokens * 2, 65536)
            logger.warning("[LLM-DIAG] TRUNCATED on %s (attempt %d), retrying with max_tokens=%d — %s",
                           _MODEL_CANDIDATES[0], attempt + 1, max_tokens, e)
            continue
        except json.JSONDecodeError:
            logger.error("[LLM-DIAG] ABORT — invalid JSON from %s (attempt %d)",
                         _MODEL_CANDIDATES[0], attempt + 1)
            return None
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "quota" in err_str.lower() or "resource exhausted" in err_str.lower()
            if is_rate_limit:
                wait = 5 * (attempt + 1)
                logger.warning("[LLM-DIAG] RATE LIMITED on %s (attempt %d/%d), waiting %ds — error: %s",
                               _MODEL_CANDIDATES[0], attempt + 1, 3, wait, err_str[:200])
                await asyncio.sleep(wait)
            else:
                logger.error("[LLM-DIAG] UNEXPECTED ERROR on %s (attempt %d): %s",
                             _MODEL_CANDIDATES[0], attempt + 1, err_str[:500])
                return None

    # Try fallback models
    logger.info("[LLM-DIAG] Primary model exhausted, trying fallbacks: %s", _MODEL_CANDIDATES[1:])
    for fallback_name in _MODEL_CANDIDATES[1:]:
        fallback = _get_fallback_model(fallback_name)
        if fallback is None:
            logger.warning("[LLM-DIAG] Could not initialize fallback model %s", fallback_name)
            continue
        try:
            result = await _try_model(fallback, user_prompt, model_name=fallback_name,
                                       max_output_tokens=max_tokens)
            t_total = time.monotonic() - t_start
            paths = len(result.get("critical_paths", [])) if result else 0
            logger.info("[LLM-DIAG] SUCCESS (fallback %s, %.1fs total): %d critical paths",
                        fallback_name, t_total, paths)
            return result
        except _TruncatedResponseError as e:
            logger.warning("[LLM-DIAG] Fallback %s truncated: %s", fallback_name, e)
            continue
        except json.JSONDecodeError:
            logger.error("[LLM-DIAG] ABORT — invalid JSON from fallback %s", fallback_name)
            return None
        except Exception as e:
            logger.warning("[LLM-DIAG] Fallback %s failed: %s", fallback_name, str(e)[:200])
            continue

    t_total = time.monotonic() - t_start
    logger.error("[LLM-DIAG] ALL MODELS EXHAUSTED after %.1fs", t_total)
    return None


def _build_prompt(topology: dict[str, Any], change_details: dict[str, Any]) -> str:
    """Build a concise but complete prompt with topology + change context."""

    # Trim large property bags to stay under token limits
    trimmed_nodes = []
    for node in topology.get("nodes", []):
        trimmed = {
            "id": node.get("id"),
            "label": node.get("label"),
        }
        props = node.get("properties", {})
        for key in ["type", "role", "criticality", "vendor", "hostname", "name",
                     "status", "vlan_id", "port", "protocol",
                     "has_redundancy", "redundancy_protocol",
                     "acl_in", "acl_out", "services"]:
            if key in props:
                trimmed[key] = props[key]
        trimmed_nodes.append(trimmed)

    trimmed_edges = []
    for edge in topology.get("edges", []):
        trimmed_edges.append({
            "source": edge.get("source"),
            "target": edge.get("target"),
            "type": edge.get("rel_type"),
        })

    prompt_data = {
        "topology": {
            "nodes": trimmed_nodes,
            "edges": trimmed_edges,
            "node_count": len(trimmed_nodes),
            "edge_count": len(trimmed_edges),
        },
        "change": change_details,
    }

    return (
        "Analyze the following infrastructure change against the network topology.\n\n"
        f"{json.dumps(prompt_data, indent=2, default=str)}"
    )


def is_available() -> bool:
    """Check if LLM service is configured and available."""
    provider = settings.llm_provider.strip().lower()
    if provider in ("openai_compatible", "opencode"):
        return bool(settings.llm_base_url and settings.llm_model)
    return bool(settings.gemini_api_key)
