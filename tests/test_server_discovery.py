import threading
import unittest

from discovery import ServerAnnouncer, ServerBrowser, get_local_ip
from server import HangmanServer

from tests._polling import wait_until


class HangmanServerAnnouncesItselfTests(unittest.TestCase):

    def test_server_is_discoverable_while_running_and_gone_after_stop(self):
        browser = ServerBrowser(discovery_port=0, timeout=0.4)
        browser.start()
        self.addCleanup(browser.stop)

        server = HangmanServer(
            host="127.0.0.1",
            port=0,
            server_name="VM-TESTE",
            announcer_factory=lambda: ServerAnnouncer(
                server_name="VM-TESTE",
                game_port=0,
                discovery_port=browser.port,
                target_host="127.0.0.1",
                interval=0.05,
            ),
        )

        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()

        try:
            found = wait_until(
                lambda: any(
                    s["name"] == "VM-TESTE"
                    for s in browser.list_servers()
                )
            )
            self.assertTrue(found, "servidor não se anunciou na rede")

            servers = {s["name"]: s for s in browser.list_servers()}
            self.assertEqual(servers["VM-TESTE"]["host"], get_local_ip())

        finally:
            server.stop()

        gone = wait_until(
            lambda: not any(
                s["name"] == "VM-TESTE"
                for s in browser.list_servers()
            ),
            timeout=2.0,
        )
        self.assertTrue(gone, "servidor parado continuou anunciado")


if __name__ == "__main__":
    unittest.main()
