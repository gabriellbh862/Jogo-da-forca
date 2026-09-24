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

    def test_connects_when_server_is_already_known(self):
        self.client.browser = FakeBrowser(
            servers=[
                {"name": "VM1", "host": "192.168.0.10", "port": 5000}
            ]
        )

        calls = []

        def fake_open_connection(payload, host, port, show_game_screen=True):
            calls.append((payload, host, port, show_game_screen))

        self.client.open_connection = fake_open_connection

        statuses = []

        self.client.find_server_and_connect(
            "VM1",
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

    def test_reports_not_found_after_deadline_without_blocking(self):
        self.client.browser = FakeBrowser(servers=[])

        calls = []
        self.client.open_connection = lambda *a, **k: calls.append((a, k))

        statuses = []
        not_found_calls = []

        self.client.find_server_and_connect(
            "VM-QUE-NAO-EXISTE",
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
        self.assertIn("não encontrado", last_text)
        self.assertEqual(last_color, "red")

    def test_finds_server_that_appears_before_deadline(self):
        browser = FakeBrowser(servers=[])
        self.client.browser = browser

        calls = []
        self.client.open_connection = lambda payload, host, port, show_game_screen=True: calls.append(
            (host, port)
        )

        self.client.find_server_and_connect(
            "VM2",
            {"type": "RECONNECT", "session_id": "xyz"},
            show_game_screen=False,
            deadline=time.monotonic() + 3.0,
        )

        # Servidor "aparece" na rede um pouco depois.
        browser._servers = [
            {"name": "VM2", "host": "10.0.0.5", "port": 5000}
        ]

        pump(self.client.root, timeout=2.0)

        self.assertEqual(calls, [("10.0.0.5", 5000)])


if __name__ == "__main__":
    unittest.main()
