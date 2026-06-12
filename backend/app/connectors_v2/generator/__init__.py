"""Générateur automatique de profils YAML Deplyx.

Permet de créer un profil YAML pour n'importe quel constructeur/OS
en combinant :
  - Scanner passif (bannière SSH, SNMP)
  - Documentation existante (Netmiko, ntc-templates, LibreNMS)
  - LLM pour la synthèse finale

Utilisation :
    from app.connectors_v2.generator import generate_profile

    profile_yaml = await generate_profile(host="192.168.1.1", username="admin")
"""

from .profile_generator import generate_profile

__all__ = ["generate_profile"]
