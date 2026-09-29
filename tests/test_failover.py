import socket
import threading
import unittest

from discovery import ServerAnnouncer, ServerBrowser, get_local_ip
from server import HangmanServer, ROLE_BACKUP, ROLE_PRIMARY
from protocol import recv_message, send_message

from tests._polling import wait_until


GAME_PORT_A = 55091
GAME_PORT_B = 55092
DISCOVERY_PORT = 55093


class FailoverTests(unittest.TestCase):
    """
    Dois Servidores na mesma rede (aqui, loopback): um vira o
    Principal, o outro fica de Reserva replicando o estado das
    salas. Ao derrubar o Principal, a Reserva assume sozinha e um
    Jogador consegue reconectar à mesma sessão/sala nela.
    """

    def setUp(self):
        self.browser = ServerBrowser(
            discovery_port=DISCOVERY_PORT,
            timeout=0.6,
        )
        self.browser.start()
        self.addCleanup(self.browser.stop)

        self.server_a = self._make_server(
            "A-SERVIDOR", "A-ID", GAME_PORT_A
        )

        self.server_b = self._make_server(
            "B-SERVIDOR", "B-ID", GAME_PORT_B
        )

        self.sockets = []

        self.addCleanup(self._close_sockets)

        for server in (self.server_a, self.server_b):

            thread = threading.Thread(
                target=server.start, daemon=True
            )
            thread.start()
            self.addCleanup(server.stop)

    def _make_server(self, name, server_id, port):

        server = HangmanServer(
            # "0.0.0.0" (não "127.0.0.1"): a replicação entre os
            # dois Servidores conecta pelo IP real da interface
            # (get_local_ip(), usado no anúncio), não por loopback.
            host="0.0.0.0",
            port=port,
            server_name=name,
            server_id=server_id,
            peer_browser_factory=lambda: self.browser,
            startup_grace_period=0.3,
            election_interval=0.1,
            replication_interval=0.1,
        )

        server._announcer_factory = lambda: ServerAnnouncer(
            server_name=name,
            game_port=port,
            discovery_port=DISCOVERY_PORT,
            target_host=get_local_ip(),
            interval=0.05,
            server_id=server.server_id,
            role_provider=lambda: server.role,
            replication_port=server.replication_port,
        )

        return server

    def _close_sockets(self):

        for sock in self.sockets:

            try:
                sock.close()

            except OSError:
                pass

    def _connect(self, port):

        sock = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM
        )
        sock.settimeout(2.0)
        sock.connect(("127.0.0.1", port))

        self.sockets.append(sock)

        return sock

    def _join(self, port, nickname):

        sock = self._connect(port)

        send_message(
            sock,
            {"type": "JOIN", "nickname": nickname},
        )

        welcome = recv_message(sock)

        self.assertEqual(welcome["type"], "WELCOME")

        return sock, welcome

    def test_backup_takes_over_the_match_when_the_primary_dies(self):

        # 1) A eleição decide um único Principal; o outro vira
        # Reserva (o de menor id sempre vence, ver server.py).
        elected = wait_until(
            lambda: (
                self.server_a.role == ROLE_PRIMARY
                and self.server_b.role == ROLE_BACKUP
            ),
            timeout=3.0,
        )

        self.assertTrue(
            elected,
            (
                "eleição não convergiu: "
                f"A={self.server_a.role} "
                f"B={self.server_b.role}"
            ),
        )

        primary, backup = self.server_a, self.server_b

        # 2) Dois Jogadores entram na partida, direto no Principal.
        sock1, welcome1 = self._join(primary.port, "Jogador 1")
        sock2, welcome2 = self._join(primary.port, "Jogador 2")

        room_id = welcome1["room_id"]
        self.assertEqual(welcome2["room_id"], room_id)

        session_id_1 = welcome1["session_id"]

        # Consome o GAME_STATE inicial de cada um (o segundo JOIN
        # já inicia a partida e cada Jogador recebe seu estado).
        recv_message(sock1)
        recv_message(sock2)

        # 3) Espera a replicação levar a sala/sessões à Reserva.
        replicated = wait_until(
            lambda: (
                room_id in backup.rooms
                and backup.rooms[room_id].started
                and len(backup.sessions) == 2
            ),
            timeout=2.0,
        )

        self.assertTrue(
            replicated, "estado não chegou à reserva a tempo"
        )

        # 4) O Principal "cai" (processo morre de verdade).
        primary.stop()

        # 5) A Reserva sobrevivente assume sozinha.
        promoted = wait_until(
            lambda: backup.role == ROLE_PRIMARY,
            timeout=3.0,
        )

        self.assertTrue(
            promoted, "a reserva não assumiu após a queda"
        )

        # 6) O Jogador 1 reconecta à MESMA sessão, agora na Reserva
        # promovida — sala e progresso da partida preservados.
        reconnect_sock = self._connect(backup.port)

        send_message(
            reconnect_sock,
            {
                "type": "RECONNECT",
                "session_id": session_id_1,
            },
        )

        welcome_back = recv_message(reconnect_sock)

        self.assertEqual(welcome_back["type"], "WELCOME")
        self.assertTrue(welcome_back["reconnected"])
        self.assertEqual(welcome_back["room_id"], room_id)
        self.assertEqual(welcome_back["server"], "B-SERVIDOR")

        state = recv_message(reconnect_sock)

        self.assertEqual(state["type"], "GAME_STATE")
        self.assertEqual(state["room_id"], room_id)
        self.assertTrue(state["started"])


if __name__ == "__main__":
    unittest.main()
