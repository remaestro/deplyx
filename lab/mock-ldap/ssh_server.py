"""Mock OpenLDAP SSH server."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("LDAP_HOSTNAME", "ldap-dc-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "LDAP123!")

COMMANDS = {
    "ldapsearch -x": f"""# extended LDIF
# LDAPv3
# base <dc=corp,dc=local> with scope subtree
# filter: (objectclass=*)

# corp.local
dn: dc=corp,dc=local
dc: corp
o: Corp Laboratory
objectClass: top
objectClass: dcObject
objectClass: organization

# admin, corp.local
dn: cn=admin,dc=corp,dc=local
objectClass: simpleSecurityObject
objectClass: organizationalRole
cn: admin
description: LDAP administrator

# People, corp.local
dn: ou=People,dc=corp,dc=local
ou: People
objectClass: organizationalUnit

# john.doe, People, corp.local
dn: uid=john.doe,ou=People,dc=corp,dc=local
uid: john.doe
cn: John Doe
sn: Doe
mail: john.doe@corp.local
objectClass: inetOrgPerson
memberOf: cn=developers,ou=Groups,dc=corp,dc=local

# Groups, corp.local
dn: ou=Groups,dc=corp,dc=local
objectClass: organizationalUnit
ou: Groups

# search result
search: 2
result: 0 Success
numEntries: 847
{HOSTNAME}$ """,

    "slapcat": f"""dn: dc=corp,dc=local
objectClass: top
objectClass: dcObject
objectClass: organization
o: Corp Laboratory
dc: corp
structuralObjectClass: organization
entryUUID: 12345678-90ab-cdef-1234-567890abcdef
creatorsName: cn=admin,dc=corp,dc=local
createTimestamp: 20231001120000Z
entryCSN: 20241201120000.123456Z#000000#000#000000
modifiersName: cn=admin,dc=corp,dc=local
modifyTimestamp: 20241201120000Z

... (847 entries total)
{HOSTNAME}$ """,

    "show schema": f"""LDAP Schema Information:
  Loaded schemas: core, cosine, inetorgperson, nis, ppolicy, memberof
  Custom schemas: corp-extensions.schema

  Object Classes: 143
  Attribute Types: 847
  Syntaxes: 45
  Matching Rules: 62
{HOSTNAME}$ """,

    "show replication": f"""LDAP Replication Status:
  Mode: Master-Slave (syncrepl)
  Replica 1 (ldap-dc-02.corp.local:389):
    Status: ACTIVE
    Last sync: 2024-12-01 14:22:33 UTC  
    CSN Delta: 0s (in sync)
    Pending updates: 0
  Replica 2 (ldap-dc-03.corp.local:389):
    Status: ACTIVE
    Last sync: 2024-12-01 14:22:31 UTC
    CSN Delta: 2s
    Pending updates: 0
{HOSTNAME}$ """,

    "slapd status": f"""slapd (OpenLDAP 2.6.7) is running.
PID: 1234
  Connections: 48 active / 1200 total
  Operations: 
    Bind: 12,847  Add: 243  Delete: 12  Modify: 1,456  Search: 478,234
  Database: /var/lib/ldap
    Entries: 847
    Size: 12.4 MB
  Uptime: 83 days, 14 hours
{HOSTNAME}$ """,
}


class MockSSH(paramiko.ServerInterface):
    def check_channel_request(self, kind, chanid): return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
    def check_auth_password(self, username, password): return paramiko.AUTH_SUCCESSFUL if username == SSH_USER and password == SSH_PASS else paramiko.AUTH_FAILED
    def check_channel_shell_request(self, channel): return True
    def get_allowed_auths(self, username): return "password,publickey"
    def check_auth_publickey(self, username, key): return paramiko.AUTH_SUCCESSFUL


def handle_client(sock, addr):
    t = paramiko.Transport(sock)
    t.add_server_key(HOST_KEY)
    t.start_server(server=MockSSH())
    ch = t.accept(30)
    if not ch: t.close(); return
    try:
        ch.sendall(f"\r\n{HOSTNAME}$ ".encode())
        buf = b""
        while True:
            data = ch.recv(4096)
            if not data: break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                cmd = line.decode("utf-8", errors="ignore").strip().rstrip("\r")
                if not cmd: ch.sendall(f"\r\n{HOSTNAME}$ ".encode()); continue
                if cmd in ("exit", "quit"): return
                resp = next((v for k, v in COMMANDS.items() if cmd.lower().startswith(k.lower())), f"bash: {cmd}: command not found\r\n{HOSTNAME}$ ")
                ch.sendall(f"\r\n{resp}\r\n".encode())
    except Exception: pass
    finally:
        try: ch.close()
        except: pass
        t.close()


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", SSH_PORT)); s.listen(5)
    print(f"[Mock OpenLDAP {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
