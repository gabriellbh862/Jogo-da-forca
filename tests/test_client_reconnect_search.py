import time
import unittest

from client import HangmanClient


class FakeBrowser:

    def __init__(self, servers=None):
        self._servers = servers or []

    def start(self):
        pass

    def stop(self):
        pass

    def list_servers(self):
        return list(self._servers)


def primary(name="VM1", host="192.168.0.10", port=5000):
    return {
        "id": name,
        "name": name,
        "host": host,
        "port": port,
        "role": "PRIMARY",
        "replication_port": port + 1000,
    }


def backup(name="VM2", host="192.168.0.11", port=5000):
    server = primary(name=name, host=host, port=port)
    server["role"] = "BACKUP"
    return server


def pump(root, timeout=3.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        time.sleep(interval)


class FindServerAndConnectTests(unittest.TestCase):

    def setUp(self):
        self.client = HangmanClient()
        self.addCleanup(self.client.close)

        # Substitui o ServerBrowser real (que já está
        # escutando a rede de verdade) por um fake controlável.
        self.client.browser.stop()

    def test_connects_to_the_primary_when_already_known(self):
        self.client.browser = FakeBrowser(
            servers=[primary()]
        )

        calls = []

        def fake_open_connection(payload, host, port, show_game_screen=True):
            calls.append((payload, host, port, show_game_screen))

        self.client.open_connection = fake_open_connection

        statuses = []

        self.client.find_server_and_connect(
            {"type": "RECONNECT", "session_id": "abc"},
            show_game_screen=False,
            on_status=lambda text, color: statuses.append((text, color)),
        )

        self.assertEqual(len(calls), 1)
        payload, host, port, show_game_screen = calls[0]
        self.assertEqual(payload["session_id"], "abc")
        self.assertEqual(host, "192.168.0.10")
        self.assertEqual(port, 5000)
        self.assertFalse(show_game_screen)

    def test_ignores_backups_and_reports_not_found_after_deadline(self):
        # Só há Reservas na rede: nenhum Principal para conectar.
        self.client.browser = FakeBrowser(servers=[backup()])

        calls = []
        self.client.open_connection = lambda *a, **k: calls.append((a, k))

        statuses = []
        not_found_calls = []

        self.client.find_server_and_connect(
            {"type": "RECONNECT", "session_id": "abc"},
            show_game_screen=False,
            on_status=lambda text, color: statuses.append((text, color)),
            on_not_found=lambda: not_found_calls.append(True),
            deadline=time.monotonic() + 0.3,
        )

        pump(self.client.root, timeout=2.0)

        self.assertEqual(calls, [])
        self.assertEqual(len(not_found_calls), 1)
        self.assertTrue(statuses)
        last_text, last_color = statuses[-1]
        self.assertIn("Nenhum servidor ativo", last_text)
        self.assertEqual(last_color, "red")

    def test_finds_new_primary_that_appears_before_deadline(self):
        # Simula um failover: no início não há Principal (o antigo
        # acabou de cair); pouco depois uma Reserva assume.
        browser = FakeBrowser(servers=[])
        self.client.browser = browser

        calls = []
        self.client.open_connection = lambda payload, host, port, show_game_screen=True: calls.append(
            (host, port)
        )

        self.client.find_server_and_connect(
            {"type": "RECONNECT", "session_id": "xyz"},
            show_game_screen=False,
            deadline=time.monotonic() + 3.0,
        )

        # A Reserva "assume" como Principal um pouco depois.
        browser._servers = [
            primary(name="VM2", host="10.0.0.5", port=5000)
        ]

        pump(self.client.root, timeout=2.0)

        self.assertEqual(calls, [("10.0.0.5", 5000)])


if __name__ == "__main__":
    unittest.main()
