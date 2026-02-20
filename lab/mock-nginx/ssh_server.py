"""Mock Nginx web server SSH."""
import os, threading, signal, sys, socket
import paramiko

HOST_KEY = paramiko.RSAKey.generate(2048)
HOSTNAME = os.getenv("NGINX_HOSTNAME", "nginx-web-01")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER", "admin")
SSH_PASS = os.getenv("SSH_PASS", "Nginx123!")

COMMANDS = {
    "nginx -t": f"""nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
{HOSTNAME}$ """,

    "nginx -T": f"""# configuration file /etc/nginx/nginx.conf:
worker_processes auto;
events {{ worker_connections 1024; }}

http {{
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent"';
    access_log /var/log/nginx/access.log main;

    upstream backend {{
        server 10.0.1.100:8080 weight=5;
        server 10.0.1.101:8080 weight=5;
        server 10.0.1.102:8080 backup;
    }}

    server {{
        listen 80;
        server_name corp.local;
        return 301 https://$host$request_uri;
    }}

    server {{
        listen 443 ssl;
        server_name corp.local;
        ssl_certificate /etc/ssl/corp.crt;
        ssl_certificate_key /etc/ssl/corp.key;
        location / {{ proxy_pass http://backend; }}
    }}
}}
{HOSTNAME}$ """,

    "cat /var/log/nginx/access.log": f"""10.0.1.50 - - [01/Dec/2024:14:22:33 +0000] "GET /api/health HTTP/1.1" 200 24 "-" "curl/7.88.1"
10.0.1.51 - - [01/Dec/2024:14:22:30 +0000] "POST /api/users/login HTTP/1.1" 200 512 "https://corp.local/" "Mozilla/5.0"
10.0.1.52 - - [01/Dec/2024:14:22:28 +0000] "GET /api/dashboard HTTP/1.1" 200 4096 "https://corp.local/" "Mozilla/5.0"
203.0.113.99 - - [01/Dec/2024:14:22:15 +0000] "GET /wp-login.php HTTP/1.1" 404 162 "-" "python-requests/2.28"
{HOSTNAME}$ """,

    "cat /var/log/nginx/error.log": f"""2024/12/01 14:10:22 [warn] 1234#0: *48823 upstream server temporarily disabled while connecting to upstream
2024/12/01 14:10:22 [error] 1234#0: *48823 connect() failed (111: Connection refused) while connecting to upstream, client: 10.0.1.50, server: corp.local, upstream: "10.0.1.102:8080"
2024/12/01 13:58:00 [notice] 1234#0: signal process started
{HOSTNAME}$ """,

    "netstat -tlnp": f"""Proto Recv-Q Send-Q Local Address    Foreign Address   State   PID/Program
tcp        0      0 0.0.0.0:80       0.0.0.0:*         LISTEN  1234/nginx
tcp        0      0 0.0.0.0:443      0.0.0.0:*         LISTEN  1234/nginx
tcp        0      0 127.0.0.1:8080   0.0.0.0:*         LISTEN  5678/php-fpm
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
    print(f"[Mock Nginx {HOSTNAME}] Listening on :{SSH_PORT}")
    signal.signal(signal.SIGTERM, lambda *_: (s.close(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (s.close(), sys.exit(0)))
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle_client, args=(c, a), daemon=True).start()
        except OSError: break

if __name__ == "__main__": main()
