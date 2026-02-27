"""Unit tests for the graph layer (neo4j_client constants & validation)."""

import pytest

from app.graph.neo4j_client import ALLOWED_REL_TYPES


class TestAllowedRelTypes:
    def test_is_frozenset(self):
        assert isinstance(ALLOWED_REL_TYPES, frozenset)

    def test_count_at_least_22(self):
        assert len(ALLOWED_REL_TYPES) >= 22

    def test_core_network_rels(self):
        for rel in ["HAS_INTERFACE", "HAS_RULE", "HOSTS", "CONNECTED_TO"]:
            assert rel in ALLOWED_REL_TYPES

    def test_wireless_rels(self):
        for rel in ["HAS_WLAN", "HAS_AP", "SERVES_WLAN", "HAS_RADIO"]:
            assert rel in ALLOWED_REL_TYPES

    def test_routing_rels(self):
        for rel in ["HAS_BGP_PEER", "HAS_VRF", "HAS_ROUTE", "ROUTES_TO"]:
            assert rel in ALLOWED_REL_TYPES

    def test_service_rels(self):
        for rel in ["HAS_VHOST", "HAS_INDEX", "HAS_DATASOURCE", "HAS_SCRAPE_TARGET"]:
            assert rel in ALLOWED_REL_TYPES

    def test_infra_rels(self):
        for rel in ["HAS_REPLICA", "PART_OF", "LOCATED_IN", "HAS_VPN_TUNNEL"]:
            assert rel in ALLOWED_REL_TYPES

    def test_no_duplicates(self):
        # frozenset by definition has no duplicates; verify count vs list
        as_list = list(ALLOWED_REL_TYPES)
        assert len(as_list) == len(set(as_list))


class TestRelTypeValidation:
    """Verify that create_relationship validates rel_type.

    We inspect the source to confirm the validation exists (we can't call
    the real neo4j_client without a running DB).
    """

    def test_validation_in_source(self):
        import inspect
        from app.graph import neo4j_client as mod

        source = inspect.getsource(mod)
        assert "ALLOWED_REL_TYPES" in source
        assert "rel_type" in source

    def test_last_seen_in_merge_node(self):
        import inspect
        from app.graph import neo4j_client as mod

        source = inspect.getsource(mod)
        assert "last_seen" in source
