import socket
import time
import unittest

from discovery import (
    ServerAnnouncer,
    ServerBrowser,
    get_local_ip,
)

from tests._polling import wait_until


class ServerBrowserTests(unittest.TestCase):

    def setUp(self):
        self.browser = ServerBrowser(discovery_port=0, timeout=0.4)
        self.browser.start()
        self.addCleanup(self.browser.stop)

        self.announcer = None

    def tearDown(self):
        if self.announcer is not None:
            self.announcer.stop()

    def start_announcer(self, server_name="VM1", game_port=5000, interval=0.05):
        self.announcer = ServerAnnouncer(
            server_name=server_name,
            game_port=game_port,
            discovery_port=self.browser.port,
            target_host="127.0.0.1",
            interval=interval,
        )
        self.announcer.start()

    def test_discovers_announced_server(self):
        self.start_announcer(server_name="VM1", game_port=5000)

        found = wait_until(
            lambda: len(self.browser.list_servers()) == 1
        )
        self.assertTrue(found, "servidor anunciado não foi descoberto a tempo")

        servers = self.browser.list_servers()
        self.assertEqual(servers[0]["name"], "VM1")
        self.assertEqual(servers[0]["host"], get_local_ip())
        self.assertEqual(servers[0]["port"], 5000)

    def test_prunes_stale_servers_after_announcer_stops(self):
        self.start_announcer(interval=0.05)

        wait_until(lambda: len(self.browser.list_servers()) == 1)

        self.announcer.stop()

        gone = wait_until(
            lambda: len(self.browser.list_servers()) == 0,
            timeout=2.0,
        )
        self.assertTrue(gone, "servidor parado não foi removido da lista")

    def test_ignores_malformed_packets(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(b"not-json", ("127.0.0.1", self.browser.port))
            sock.sendto(b'{"type": "OTHER"}', ("127.0.0.1", self.browser.port))
        finally:
            sock.close()

        time.sleep(0.3)
        self.assertEqual(self.browser.list_servers(), [])


class LocalIpTests(unittest.TestCase):

    def test_returns_non_empty_string(self):
        ip = get_local_ip()
        self.assertIsInstance(ip, str)
        self.assertTrue(ip)


if __name__ == "__main__":
    unittest.main()
