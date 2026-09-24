import json
import socket
import threading
import time


DISCOVERY_PORT = 55201
BROADCAST_ADDRESS = "255.255.255.255"
ANNOUNCE_INTERVAL = 2.0
SERVER_TIMEOUT = 6.0

ANNOUNCE_TYPE = "FORCA_ANNOUNCE"


def get_local_ip():
    """IP do Anfitrião na rede local, para se anunciar aos Jogadores."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]

    except OSError:
        return "127.0.0.1"

    finally:
        sock.close()


class ServerAnnouncer:
    """Anuncia periodicamente a presença de um Servidor na rede local."""

    def __init__(
        self,
        server_name,
        game_port,
        discovery_port=DISCOVERY_PORT,
        target_host=BROADCAST_ADDRESS,
        interval=ANNOUNCE_INTERVAL,
    ):
        self.server_name = server_name
        self.game_port = game_port
        self.discovery_port = discovery_port
        self.target_host = target_host
        self.interval = interval

        self._stop_event = threading.Event()
        self._thread = None

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop_event.is_set():

            # Recalculado a cada anúncio: o IP local pode mudar
            # durante a vida do Servidor (DHCP renovado, troca de
            # rede Wi-Fi, etc.).
            payload = json.dumps(
                {
                    "type": ANNOUNCE_TYPE,
                    "name": self.server_name,
                    "host": get_local_ip(),
                    "port": self.game_port,
                }
            ).encode("utf-8")

            try:
                self._sock.sendto(
                    payload,
                    (self.target_host, self.discovery_port),
                )

            except OSError:
                pass

            self._stop_event.wait(self.interval)

    def stop(self):
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=1.0)

        try:
            self._sock.close()

        except OSError:
            pass


class ServerBrowser:
    """Escuta anúncios de Servidores e mantém uma lista viva de Anfitriões ativos na rede."""

    def __init__(
        self,
        discovery_port=DISCOVERY_PORT,
        timeout=SERVER_TIMEOUT,
    ):
        self.discovery_port = discovery_port
        self.timeout = timeout

        self._servers = {}
        self._lock = threading.Lock()

        self._stop_event = threading.Event()
        self._thread = None
        self._sock = None

        self.port = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(0.5)
        self._sock.bind(("", self.discovery_port))

        self.port = self._sock.getsockname()[1]

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop_event.is_set():

            try:
                data, _address = self._sock.recvfrom(4096)

            except socket.timeout:
                continue

            except OSError:
                break

            self._handle_packet(data)

    def _handle_packet(self, data):
        try:
            message = json.loads(data.decode("utf-8"))

        except (ValueError, UnicodeDecodeError):
            return

        if not isinstance(message, dict):
            return

        if message.get("type") != ANNOUNCE_TYPE:
            return

        name = message.get("name")
        host = message.get("host")
        port = message.get("port")

        if not name or not host or not isinstance(port, int):
            return

        # Chave por (host, port), não só por name: dois Servidores
        # físicos distintos podem anunciar o mesmo nome (hostnames
        # padrão, VMs clonadas) sem se sobrescrever na lista.
        key = (host, port)

        with self._lock:
            self._servers[key] = {
                "name": name,
                "host": host,
                "port": port,
                "last_seen": time.monotonic(),
            }

    def _prune(self):
        cutoff = time.monotonic() - self.timeout

        with self._lock:
            expired = [
                key
                for key, info in self._servers.items()
                if info["last_seen"] < cutoff
            ]

            for key in expired:
                del self._servers[key]

    def list_servers(self):
        self._prune()

        with self._lock:
            return sorted(
                self._servers.values(),
                key=lambda server: server["name"],
            )

    def stop(self):
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=1.0)

        if self._sock is not None:
            try:
                self._sock.close()

            except OSError:
                pass
