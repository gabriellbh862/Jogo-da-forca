import json
import os
import threading
import time
import unittest

from discovery import ServerAnnouncer, ServerBrowser, get_local_ip
from server import HangmanServer
from client import HangmanClient, SESSION_FILE


GAME_PORT = 55061
TEST_DISCOVERY_PORT = 55062


def pump(root, predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class JoinAndReconnectEndToEndTests(unittest.TestCase):
    """
    Cobre, de ponta a ponta (Servidor real + Cliente real, só a rede
    é que é substituída por loopback): um Jogador entra numa partida
    descoberta na rede, a Sessão salva grava o nome do Servidor, e um
    Cliente "reaberto" reencontra esse Servidor via descoberta
    automática e reconecta com a mesma Sessão (Ticket 1 + Ticket 3).
    """

    def setUp(self):
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)

        self.addCleanup(self._remove_session_file)

        # Um único ServerBrowser, compartilhado pelo Servidor (para
        # ele enxergar outros Servidores na eleição) e por todos os
        # Clientes deste teste: no Windows, dois sockets ligados à
        # mesma porta UDP no mesmo processo "roubam" pacotes um do
        # outro (só um dos dois recebe), o que não reflete a rede
        # real (lá cada papel é um processo/máquina separado).
        self.shared_browser = ServerBrowser(
            discovery_port=TEST_DISCOVERY_PORT, timeout=6.0
        )
        self.shared_browser.start()
        self.addCleanup(self.shared_browser.stop)

        self.server = HangmanServer(
            host="0.0.0.0",
            port=GAME_PORT,
            server_name="VM-E2E",
            announcer_factory=lambda: ServerAnnouncer(
                server_name="VM-E2E",
                game_port=GAME_PORT,
                discovery_port=TEST_DISCOVERY_PORT,
                # ServerAnnouncer se prende à interface real para
                # enviar; "127.0.0.1" não é entregue localmente a
                # partir dela no Windows.
                target_host=get_local_ip(),
                interval=0.05,
                # Sem isso, o anúncio usaria um id aleatório e um
                # role fixo "PRIMARY" desligados do servidor real,
                # e ele se veria como um Principal rival na rede.
                server_id=self.server.server_id,
                role_provider=lambda: self.server.role,
                replication_port=self.server.replication_port,
            ),
            peer_browser_factory=lambda: self.shared_browser,
        )

        self.server_thread = threading.Thread(
            target=self.server.start, daemon=True
        )
        self.server_thread.start()
        self.addCleanup(self.server.stop)

    def _remove_session_file(self):
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)

    def make_client(self):
        client = HangmanClient()
        client.browser.stop()
        client.browser = self.shared_browser
        return client

    def test_join_saves_server_name_and_reconnect_finds_it_via_discovery(self):
        player = self.make_client()
        self.addCleanup(player.close)

        # Espera o Servidor terminar a eleição inicial (ver
        # STARTUP_GRACE_PERIOD) e se anunciar como Principal —
        # não basta aparecer na descoberta, ele começa "ELECTING".
        pump(
            player.root,
            lambda: player.get_primary_server() is not None,
            timeout=8.0,
        )

        player.nickname_entry.insert(0, "Jogador E2E")

        player.connect_new_player()

        pump(
            player.root,
            lambda: player.session_id is not None,
            timeout=4.0,
        )

        self.assertIsNotNone(player.session_id)
        self.assertTrue(os.path.exists(SESSION_FILE))

        with open(SESSION_FILE, "r", encoding="utf-8") as file:
            saved = json.load(file)

        self.assertEqual(saved["server_name"], "VM-E2E")

        original_session_id = saved["session_id"]

        # Simula a conexão caindo (ex.: fechar e reabrir o cliente).
        # O ServerBrowser é compartilhado neste teste (ver setUp) e
        # continua vivo para o Servidor e para o próximo Cliente —
        # um processo de verdade fechado levaria o seu junto, mas
        # aqui isso não muda nada do que este teste observa.
        player.close_socket_only()
        player.connected = False

        reconnector = self.make_client()
        self.addCleanup(reconnector.close)

        pump(
            reconnector.root,
            lambda: reconnector.get_primary_server() is not None,
            timeout=4.0,
        )

        self.assertIsNotNone(reconnector.saved_session)

        reconnector.reconnect_saved_session()

        pump(
            reconnector.root,
            lambda: (
                reconnector.connected
                and reconnector.session_id == original_session_id
            ),
            timeout=6.0,
        )

        self.assertTrue(reconnector.connected)
        self.assertEqual(
            reconnector.session_id, original_session_id
        )


if __name__ == "__main__":
    unittest.main()
