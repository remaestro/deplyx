from app.connectors import display_name


def test_device_display_name_builder():
    assert display_name.device("Fortinet", "Firewall", "fw-dc1-01") == "Fortinet Firewall \u2014 fw-dc1-01"


def test_interface_display_name_builder():
    assert display_name.interface("port1", "Fortinet Firewall \u2014 fw-dc1-01") == "port1  (Fortinet Firewall \u2014 fw-dc1-01)"


def test_rule_display_name_builder():
    parent = display_name.device("Palo Alto", "Firewall", "pa-01")
    assert display_name.rule("allow-web", parent) == f"Rule allow-web  ({parent})"
