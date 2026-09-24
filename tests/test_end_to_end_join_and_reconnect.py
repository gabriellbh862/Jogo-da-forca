import json
import os
import threading
import time
import unittest

from discovery import ServerAnnouncer, ServerBrowser
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

        self.server = HangmanServer(
            host="0.0.0.0",
            port=GAME_PORT,
            server_name="VM-E2E",
            announcer_factory=lambda: ServerAnnouncer(
                server_name="VM-E2E",
                game_port=GAME_PORT,
                discovery_port=TEST_DISCOVERY_PORT,
                target_host="127.0.0.1",
                interval=0.05,
            ),
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
        client.browser = ServerBrowser(
            discovery_port=TEST_DISCOVERY_PORT, timeout=6.0
        )
        client.browser.start()
        return client

    def test_join_saves_server_name_and_reconnect_finds_it_via_discovery(self):
        player = self.make_client()
        self.addCleanup(player.close)

        pump(
            player.root,
            lambda: len(player.discovered_servers) > 0,
            timeout=4.0,
        )

        player.nickname_entry.insert(0, "Jogador E2E")
        player.server_listbox.selection_clear(0, "end")
        player.server_listbox.selection_set(0)

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
        # O ServerBrowser do cliente antigo também para, como aconteceria
        # de verdade ao fechar o processo — dois listeners de teste no
        # mesmo processo disputando a mesma porta UDP não é um cenário real.
        player.close_socket_only()
        player.connected = False
        player.browser.stop()

        reconnector = self.make_client()
        self.addCleanup(reconnector.close)

        pump(
            reconnector.root,
            lambda: len(reconnector.browser.list_servers()) > 0,
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
