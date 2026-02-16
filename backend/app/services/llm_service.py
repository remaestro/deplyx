"""LLM-powered impact analysis using Google Gemini Flash.

Sends a pruned subgraph (multi-hop neighbourhood of targets) to Gemini and asks it to:
1. Identify all critical dependency paths from targets to impacted endpoints
2. Classify impacted nodes (direct / indirect / applications / services / VLANs)
3. Assess risk severity with reasoning
4. Suggest mitigations

Falls back to rule-based analysis if the LLM is unavailable or returns invalid JSON.
"""

import asyncio
import json
import time
from typing import Any

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_model = None

# Models to try in order — 2.0-flash is much faster for structured JSON output;
# 2.5-flash has "thinking" overhead that adds 30-50s latency.
_MODEL_CANDIDATES = [
    "gemini-2.0-flash",
    "gemini-2.5-flash",
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
      "reasoning": "<why this path matters for this specific action>"
    }
  ],
  "risk_assessment": {
    "severity": "critical|high|medium|low",
    "summary": "<2-3 sentence risk summary>",
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
    "explanation": "<why this traversal strategy is appropriate for this action>"
  }
}

Rules:
- Order critical_paths by criticality (critical first, then high, medium, low)
- Only include paths that are ACTUALLY affected by the specific action
- For 'remove_rule', trace PROTECTS edges to find apps that lose protection
- For 'reboot_device'/'decommission', trace ALL connected paths (full blast radius)
- For 'change_vlan'/'delete_vlan', find all devices and apps on that VLAN
- For 'disable_port', trace through the port's device to downstream dependencies
- Consider redundancy: if an alternate path exists, note it
- Be specific about WHY each path is critical for this particular action
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


async def analyze_with_llm(
    topology: dict[str, Any],
    change_details: dict[str, Any],
) -> dict[str, Any] | None:
    """Send topology + change context to Gemini and parse structured response.

    Tries multiple models and retries on rate limit (429).
    Returns None if all attempts fail — caller should fall back.
    """
    t_start = time.monotonic()
    model = _get_model()
    if model is None:
        logger.warning("[LLM-DIAG] No model available (API key missing?)")
        return None

    user_prompt = _build_prompt(topology, change_details)
    logger.info("[LLM-DIAG] ========== NEW ANALYSIS REQUEST ==========")
    logger.info("[LLM-DIAG] Change: action=%s, targets=%s, type=%s",
                change_details.get("action"), change_details.get("target_node_ids"), change_details.get("change_type"))
    logger.info("[LLM-DIAG] Topology: %d nodes, %d edges",
                len(topology.get("nodes", [])), len(topology.get("edges", [])))
    logger.info("[LLM-DIAG] Prompt size: %d chars", len(user_prompt))

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
        for key in ["type", "criticality", "vendor", "hostname", "name", "status", "vlan_id", "port", "protocol"]:
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
    return bool(settings.gemini_api_key)
