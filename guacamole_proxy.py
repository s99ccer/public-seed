"""
Guacamole HTTPS Reverse Proxy
- 443(HTTPS) → 8081(Guacamole)
- WebSocket 지원 (guacamole)
- 자체 인증서 자동 생성
"""

import ssl, os, sys, threading, http.server, urllib.request, urllib.error, socket, select
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

GUACAMOLE_BACKEND = "http://127.0.0.1:8081"
CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
CERT_FILE = os.path.join(CERT_DIR, "server.pem")
KEY_FILE = os.path.join(CERT_DIR, "server.key")
PORT = 443

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class WebSocketProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _do_proxy(self):
        target_url = GUACAMOLE_BACKEND + self.path
        headers = dict(self.headers)
        headers["Host"] = "127.0.0.1:8081"
        headers["X-Forwarded-For"] = self.client_address[0]
        headers["X-Forwarded-Proto"] = "https"
        headers["X-Real-IP"] = self.client_address[0]

        if "Connection" in headers:
            del headers["Connection"]
        if "Upgrade" in headers:
            del headers["Upgrade"]

        body = None
        content_length = int(headers.get("Content-Length", 0))
        if content_length > 0:
            body = self.rfile.read(content_length)

        try:
            req = urllib.request.Request(
                target_url,
                data=body,
                headers=headers,
                method=self.command
            )
            resp = urllib.request.urlopen(req, timeout=30)
            resp_data = resp.read()

            self.send_response(resp.status)
            for key, val in resp.getheaders():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, val)
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(resp_data)

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, val in e.headers.items():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, val)
            self.end_headers()
            if e.readable():
                self.wfile.write(e.read())

        except Exception as e:
            self.send_error(502, f"Bad Gateway: {str(e)}")

    def _is_websocket_upgrade(self):
        return (
            self.headers.get("Upgrade", "").lower() == "websocket"
            and self.headers.get("Connection", "").lower().find("upgrade") >= 0
        )

    def _do_websocket_proxy(self):
        try:
            import http.client
            conn = http.client.HTTPConnection("127.0.0.1", 8081, timeout=30)
            ws_headers = {}
            for key in self.headers:
                if key.lower() not in ("host", "connection", "upgrade"):
                    ws_headers[key] = self.headers[key]
            ws_headers["Host"] = "127.0.0.1:8081"
            ws_headers["Connection"] = "Upgrade"
            ws_headers["Upgrade"] = "websocket"

            conn.request(self.command, self.path, headers=ws_headers)
            resp = conn.getresponse()

            self.send_response(resp.status)
            for key, val in resp.getheaders():
                if key.lower() not in ("transfer-encoding",):
                    self.send_header(key, val)
            self.end_headers()

            if resp.status == 101:
                self._tunnel_websocket(conn.sock)
            else:
                data = resp.read()
                self.wfile.write(data)

        except Exception as e:
            self.send_error(502, f"WebSocket Bad Gateway: {str(e)}")

    def _tunnel_websocket(self, backend_sock):
        client_sock = self.request
        client_sock.setblocking(False)
        backend_sock.setblocking(False)

        try:
            while True:
                readable, _, exceptional = select.select(
                    [client_sock, backend_sock], [], [client_sock, backend_sock], 30
                )
                if exceptional:
                    break
                for sock in readable:
                    try:
                        data = sock.recv(65536)
                        if not data:
                            return
                        if sock is client_sock:
                            backend_sock.sendall(data)
                        else:
                            client_sock.sendall(data)
                    except:
                        return
        except:
            pass
        finally:
            try:
                backend_sock.close()
            except:
                pass

    def do_GET(self):
        if self._is_websocket_upgrade():
            self._do_websocket_proxy()
        else:
            self._do_proxy()

    def do_POST(self):
        self._do_proxy()

    def do_PUT(self):
        self._do_proxy()

    def do_DELETE(self):
        self._do_proxy()

    def do_PATCH(self):
        self._do_proxy()

    def do_OPTIONS(self):
        self._do_proxy()

    def do_HEAD(self):
        self._do_proxy()

def generate_self_signed_cert():
    os.makedirs(CERT_DIR, exist_ok=True)
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return

    print("[*] 자체 SSL 인증서 생성 중...")
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import datetime

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "KR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Seoul"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Seoul"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Guacamole"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(KEY_FILE, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()
        ))
    with open(CERT_FILE, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print("[+] 인증서 생성 완료")

def create_ssl_context():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        ctx.load_cert_chain(CERT_FILE, KEY_FILE)
    except:
        generate_self_signed_cert()
        ctx.load_cert_chain(CERT_FILE, KEY_FILE)
    return ctx

def main():
    generate_self_signed_cert()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), WebSocketProxyHandler)
    ctx = create_ssl_context()
    server.socket = ctx.wrap_socket(server.socket, server_side=True)

    print("=" * 50)
    print("  Guacamole HTTPS Reverse Proxy")
    print(f"  https://localhost:{PORT}")
    print(f"  https://127.0.0.1:{PORT}")
    print(f"  Backend: {GUACAMOLE_BACKEND}")
    print("=" * 50)
    print("  종료: Ctrl+C")
    print("=" * 50)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  중지됨")
        server.shutdown()

if __name__ == "__main__":
    main()
