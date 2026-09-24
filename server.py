import argparse
import math
import secrets
import socket
import threading
import time
from dataclasses import dataclass, field

from game import (
    HangmanGame,
    GameError
)

from protocol import (
    ConnectionClosed,
    ProtocolError,
    recv_message,
    send_message,
)


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000

MAX_NICKNAME_LENGTH = 20

MIN_ACTION_INTERVAL = 0.10

# Tempo permitido para o jogador voltar.
RECONNECT_TIMEOUT = 40


@dataclass
class ClientSession:
    session_id: str
    nickname: str
    room_id: str

    sock: socket.socket
    address: tuple

    connected: bool = True

    send_lock: threading.Lock = field(
        default_factory=threading.Lock
    )

    last_action_time: float = 0.0

    disconnect_timer: threading.Timer | None = None

    disconnect_deadline: float | None = None


class HangmanServer:

    def __init__(
        self,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        server_name="VM1"
    ):
        self.host = host
        self.port = port

        self.server_name = (
            server_name
        )

        self.rooms = {}

        self.room_locks = {}

        self.sessions = {}

        self.state_lock = (
            threading.RLock()
        )

        self.room_counter = 0

        self.server_socket = None

        self.running = (
            threading.Event()
        )

    # ========================================================
    # LOG
    # ========================================================

    def log(
        self,
        category,
        message
    ):
        timestamp = (
            time.strftime(
                "%H:%M:%S"
            )
        )

        print(
            f"[{timestamp}] "
            f"[{self.server_name}] "
            f"[{category}] "
            f"{message}"
        )

    # ========================================================
    # SALAS
    # ========================================================

    def _new_room_id(self):

        self.room_counter += 1

        return (
            f"SALA-"
            f"{self.room_counter:03d}"
        )

    def find_or_create_room(
        self,
        session_id,
        nickname
    ):
        with self.state_lock:

            for (
                room_id,
                game
            ) in self.rooms.items():

                if (
                    game.started
                    or
                    game.finished
                    or
                    len(game.players) >= 2
                ):
                    continue

                # Não coloca jogador novo numa sala
                # cujo primeiro jogador caiu.
                existing_players_connected = all(
                    (
                        player.session_id
                        in self.sessions
                        and
                        self.sessions[
                            player.session_id
                        ].connected
                    )

                    for player
                    in game.players
                )

                if not existing_players_connected:
                    continue

                try:

                    game.add_player(
                        session_id,
                        nickname
                    )

                    self.log(
                        "ROOM",
                        (
                            f"{nickname} entrou "
                            f"em {room_id}"
                        )
                    )

                    return room_id

                except GameError:
                    continue

            room_id = (
                self._new_room_id()
            )

            game = HangmanGame(
                room_id=room_id
            )

            game.add_player(
                session_id,
                nickname
            )

            self.rooms[
                room_id
            ] = game

            self.room_locks[
                room_id
            ] = threading.RLock()

            self.log(
                "ROOM",
                (
                    f"{room_id} criada "
                    f"para {nickname}"
                )
            )

            return room_id

    # ========================================================
    # CRIAR SESSÃO
    # ========================================================

    def create_session(
        self,
        sock,
        address,
        nickname
    ):
        nickname = (
            nickname.strip()
        )

        if not nickname:

            raise ValueError(
                "Nickname não pode ficar vazio."
            )

        if (
            len(nickname)
            > MAX_NICKNAME_LENGTH
        ):

            raise ValueError(
                (
                    "Nickname pode ter no máximo "
                    f"{MAX_NICKNAME_LENGTH} caracteres."
                )
            )

        session_id = (
            secrets.token_urlsafe(24)
        )

        room_id = (
            self.find_or_create_room(
                session_id,
                nickname
            )
        )

        session = ClientSession(
            session_id=session_id,
            nickname=nickname,
            room_id=room_id,
            sock=sock,
            address=address
        )

        with self.state_lock:

            self.sessions[
                session_id
            ] = session

        self.log(
            "SESSION",
            (
                "Sessão criada para "
                f"{nickname}"
            )
        )

        return session

    # ========================================================
    # RECONEXÃO
    # ========================================================

    def reconnect_session(
        self,
        session_id,
        sock,
        address
    ):
        with self.state_lock:

            session = (
                self.sessions.get(
                    session_id
                )
            )

            if session is None:

                raise ValueError(
                    "Sessão não encontrada."
                )

            old_socket = (
                session.sock
            )

            # Cancela W.O.
            if (
                session.disconnect_timer
                is not None
            ):

                session.disconnect_timer.cancel()

            session.disconnect_timer = None

            session.disconnect_deadline = None

            session.sock = sock

            session.address = (
                address
            )

            session.connected = True

        try:

            if (
                old_socket
                and
                old_socket is not sock
            ):

                old_socket.close()

        except OSError:
            pass

        self.log(
            "RECONNECT",
            (
                f"{session.nickname} "
                "reconectou à partida."
            )
        )

        return session

    # ========================================================
    # MARCAR DESCONEXÃO
    # ========================================================

    def mark_disconnected(
        self,
        session_id,
        sock
    ):
        if not session_id:
            return None

        timer = None
        room_id = None

        with self.state_lock:

            session = (
                self.sessions.get(
                    session_id
                )
            )

            if session is None:
                return None

            # Uma conexão antiga não pode derrubar
            # uma conexão nova.
            if session.sock is not sock:
                return session.room_id

            # Já estava desconectado.
            if not session.connected:
                return session.room_id

            session.connected = False

            room_id = (
                session.room_id
            )

            deadline = (
                time.time()
                +
                RECONNECT_TIMEOUT
            )

            session.disconnect_deadline = (
                deadline
            )

            if (
                session.disconnect_timer
                is not None
            ):
                session.disconnect_timer.cancel()

            timer = threading.Timer(
                RECONNECT_TIMEOUT,
                self.handle_walkover,
                args=(
                    session_id,
                    deadline
                )
            )

            timer.daemon = True

            session.disconnect_timer = (
                timer
            )

        if timer is not None:
            timer.start()

        self.log(
            "DISCONNECT",
            (
                f"{session.nickname} caiu. "
                f"Aguardando "
                f"{RECONNECT_TIMEOUT}s "
                "para reconexão."
            )
        )

        return room_id

    # ========================================================
    # W.O.
    # ========================================================

    def handle_walkover(
        self,
        session_id,
        expected_deadline
    ):
        with self.state_lock:

            session = (
                self.sessions.get(
                    session_id
                )
            )

            if session is None:
                return

            # Voltou.
            if session.connected:
                return

            # Timer antigo.
            if (
                session.disconnect_deadline
                != expected_deadline
            ):
                return

            room_id = (
                session.room_id
            )

            game = self.rooms.get(
                room_id
            )

            room_lock = (
                self.room_locks.get(
                    room_id
                )
            )

        if (
            game is None
            or
            room_lock is None
        ):
            return

        finished_by_wo = False

        with room_lock:

            # Verifica de novo porque pode ter
            # reconectado enquanto esperávamos o Lock.
            with self.state_lock:

                current_session = (
                    self.sessions.get(
                        session_id
                    )
                )

                if (
                    current_session is None
                    or
                    current_session.connected
                    or
                    current_session.disconnect_deadline
                    != expected_deadline
                ):
                    return

            finished_by_wo = (
                game.finish_by_walkover(
                    session_id
                )
            )

        with self.state_lock:

            current_session = (
                self.sessions.get(
                    session_id
                )
            )

            if current_session:

                current_session.disconnect_timer = (
                    None
                )

                current_session.disconnect_deadline = (
                    None
                )

        if not finished_by_wo:
            return

        try:

            opponent = game.get_opponent(
                session_id
            )

            winner_name = (
                opponent.nickname
                if opponent
                else "adversário"
            )

        except GameError:

            winner_name = (
                "adversário"
            )

        self.log(
            "WO",
            (
                f"{session.nickname} não voltou "
                f"em {RECONNECT_TIMEOUT}s. "
                f"{winner_name} venceu por W.O."
            )
        )

        self.broadcast_room_state(
            room_id
        )

    # ========================================================
    # ENVIO
    # ========================================================

    def send_to_session(
        self,
        session_id,
        payload
    ):
        with self.state_lock:

            session = (
                self.sessions.get(
                    session_id
                )
            )

            if (
                session is None
                or
                not session.connected
            ):
                return False

            sock = session.sock

        try:

            with session.send_lock:

                send_message(
                    sock,
                    payload
                )

            return True

        except (
            OSError,
            ConnectionClosed,
            ProtocolError
        ):

            self.mark_disconnected(
                session_id,
                sock
            )

            return False

    def send_error(
        self,
        session_id,
        message
    ):
        self.send_to_session(
            session_id,
            {
                "type":
                    "ERROR",

                "message":
                    message,

                "server":
                    self.server_name
            }
        )

    # ========================================================
    # ANTI-SPAM
    # ========================================================

    def check_rate_limit(
        self,
        session
    ):
        now = (
            time.monotonic()
        )

        elapsed = (
            now
            -
            session.last_action_time
        )

        if (
            elapsed
            < MIN_ACTION_INTERVAL
        ):
            return False

        session.last_action_time = (
            now
        )

        return True

    # ========================================================
    # TODOS OS JOGADORES CONECTADOS?
    # ========================================================

    def room_players_connected(
        self,
        room_id
    ):
        with self.state_lock:

            game = self.rooms.get(
                room_id
            )

            if game is None:
                return False

            if len(game.players) < 2:
                return False

            for player in game.players:

                session = (
                    self.sessions.get(
                        player.session_id
                    )
                )

                if (
                    session is None
                    or
                    not session.connected
                ):
                    return False

        return True

    # ========================================================
    # ESTADO DA SALA
    # ========================================================

    def broadcast_room_state(
        self,
        room_id
    ):
        with self.state_lock:

            game = self.rooms.get(
                room_id
            )

            room_lock = (
                self.room_locks.get(
                    room_id
                )
            )

            if game is None:
                return

            connection_info = {}

            for player in game.players:

                session = (
                    self.sessions.get(
                        player.session_id
                    )
                )

                connection_info[
                    player.session_id
                ] = {
                    "connected": (
                        bool(
                            session
                            and
                            session.connected
                        )
                    ),

                    "deadline": (
                        session.disconnect_deadline
                        if session
                        else None
                    )
                }

        if room_lock is None:
            return

        payloads = []

        with room_lock:

            paused = (
                game.started
                and
                not game.finished
                and
                any(
                    not connection_info.get(
                        player.session_id,
                        {}
                    ).get(
                        "connected",
                        False
                    )

                    for player
                    in game.players
                )
            )

            for player in game.players:

                try:

                    state = (
                        game.public_state(
                            player.session_id
                        )
                    )

                    opponent = (
                        game.get_opponent(
                            player.session_id
                        )
                    )

                    opponent_connected = True

                    reconnect_seconds = 0

                    if opponent:

                        info = (
                            connection_info.get(
                                opponent.session_id,
                                {}
                            )
                        )

                        opponent_connected = (
                            info.get(
                                "connected",
                                False
                            )
                        )

                        deadline = (
                            info.get(
                                "deadline"
                            )
                        )

                        if (
                            not opponent_connected
                            and
                            deadline is not None
                        ):

                            reconnect_seconds = max(
                                0,
                                math.ceil(
                                    deadline
                                    -
                                    time.time()
                                )
                            )

                    state[
                        "server"
                    ] = self.server_name

                    state[
                        "room_paused"
                    ] = paused

                    state[
                        "opponent_connected"
                    ] = opponent_connected

                    state[
                        "opponent_reconnect_seconds"
                    ] = reconnect_seconds

                    payloads.append(
                        (
                            player.session_id,
                            state
                        )
                    )

                except GameError:
                    continue

        for (
            session_id,
            payload
        ) in payloads:

            self.send_to_session(
                session_id,
                payload
            )

    # ========================================================
    # ESTADO DE UM JOGADOR
    # ========================================================

    def send_current_state(
        self,
        session_id
    ):
        with self.state_lock:

            session = (
                self.sessions.get(
                    session_id
                )
            )

            if session is None:
                return

            room_id = (
                session.room_id
            )

        # Broadcast é mais simples e mantém
        # os dois clientes sincronizados.
        self.broadcast_room_state(
            room_id
        )

    # ========================================================
    # CHUTE DE LETRA
    # ========================================================

    def handle_guess(
        self,
        session_id,
        message
    ):
        with self.state_lock:

            session = (
                self.sessions.get(
                    session_id
                )
            )

            if session is None:
                return

            room_id = (
                session.room_id
            )

            game = self.rooms.get(
                room_id
            )

            room_lock = (
                self.room_locks.get(
                    room_id
                )
            )

        if (
            game is None
            or
            room_lock is None
        ):

            self.send_error(
                session_id,
                "Sala não encontrada."
            )

            return

        # Não deixa jogar enquanto alguém caiu.
        if not self.room_players_connected(
            room_id
        ):

            self.send_error(
                session_id,
                (
                    "Partida pausada. "
                    "Aguardando reconexão do adversário."
                )
            )

            return

        if not self.check_rate_limit(
            session
        ):

            self.send_error(
                session_id,
                "Ações rápidas demais."
            )

            return

        letter = (
            message.get(
                "letter"
            )
        )

        try:

            with room_lock:

                result = (
                    game.guess(
                        session_id,
                        letter
                    )
                )

                version = (
                    game.version
                )

            self.log(
                "GAME",
                (
                    f"{session.nickname} "
                    f"tentou a letra "
                    f"'{result['letter']}' "
                    f"em {room_id} "
                    f"| acertou="
                    f"{result['correct']} "
                    f"| versão={version}"
                )
            )

            self.broadcast_room_state(
                room_id
            )

        except GameError as error:

            self.log(
                "INVALID",
                (
                    f"{session.nickname}: "
                    f"{error}"
                )
            )

            self.send_error(
                session_id,
                str(error)
            )

    # ========================================================
    # CHUTE DA PALAVRA
    # ========================================================

    def handle_word_guess(
        self,
        session_id,
        message
    ):
        with self.state_lock:

            session = (
                self.sessions.get(
                    session_id
                )
            )

            if session is None:
                return

            room_id = (
                session.room_id
            )

            game = self.rooms.get(
                room_id
            )

            room_lock = (
                self.room_locks.get(
                    room_id
                )
            )

        if (
            game is None
            or
            room_lock is None
        ):

            self.send_error(
                session_id,
                "Sala não encontrada."
            )

            return

        if not self.room_players_connected(
            room_id
        ):

            self.send_error(
                session_id,
                (
                    "Partida pausada. "
                    "Aguardando reconexão do adversário."
                )
            )

            return

        if not self.check_rate_limit(
            session
        ):

            self.send_error(
                session_id,
                "Ações rápidas demais."
            )

            return

        word = (
            message.get(
                "word"
            )
        )

        try:

            with room_lock:

                result = (
                    game.guess_word(
                        session_id,
                        word
                    )
                )

                version = (
                    game.version
                )

            self.log(
                "GAME",
                (
                    f"{session.nickname} "
                    "chutou a palavra inteira "
                    f"em {room_id} "
                    f"| acertou="
                    f"{result['correct']} "
                    f"| versão={version}"
                )
            )

            self.broadcast_room_state(
                room_id
            )

        except GameError as error:

            self.log(
                "INVALID",
                (
                    f"{session.nickname}: "
                    f"{error}"
                )
            )

            self.send_error(
                session_id,
                str(error)
            )

    # ========================================================
    # PROCESSAR MENSAGEM
    # ========================================================

    def process_message(
        self,
        session_id,
        message
    ):
        message_type = (
            message.get(
                "type"
            )
        )

        if not isinstance(
            message_type,
            str
        ):

            self.send_error(
                session_id,
                "Mensagem sem tipo."
            )

            return

        message_type = (
            message_type.upper()
        )

        if (
            message_type
            == "GUESS"
        ):

            self.handle_guess(
                session_id,
                message
            )

        elif (
            message_type
            == "GUESS_WORD"
        ):

            self.handle_word_guess(
                session_id,
                message
            )

        elif (
            message_type
            == "GET_STATE"
        ):

            self.send_current_state(
                session_id
            )

        elif (
            message_type
            == "PING"
        ):

            self.send_to_session(
                session_id,
                {
                    "type":
                        "PONG",

                    "server":
                        self.server_name,

                    "timestamp":
                        time.time()
                }
            )

        else:

            self.send_error(
                session_id,
                "Comando desconhecido."
            )

    # ========================================================
    # HANDSHAKE
    # ========================================================

    def handshake(
        self,
        sock,
        address
    ):
        message = recv_message(
            sock
        )

        message_type = (
            message.get(
                "type"
            )
        )

        if not isinstance(
            message_type,
            str
        ):

            raise ProtocolError(
                "Handshake inválido."
            )

        message_type = (
            message_type.upper()
        )

        # Novo jogador
        if (
            message_type
            == "JOIN"
        ):

            nickname = (
                message.get(
                    "nickname",
                    ""
                )
            )

            if not isinstance(
                nickname,
                str
            ):

                raise ProtocolError(
                    "Nickname inválido."
                )

            session = (
                self.create_session(
                    sock,
                    address,
                    nickname
                )
            )

            self.send_to_session(
                session.session_id,
                {
                    "type":
                        "WELCOME",

                    "session_id":
                        session.session_id,

                    "room_id":
                        session.room_id,

                    "nickname":
                        session.nickname,

                    "server":
                        self.server_name,

                    "reconnected":
                        False
                }
            )

            self.log(
                "CONNECT",
                (
                    f"{session.nickname} "
                    f"conectado de "
                    f"{address[0]}:"
                    f"{address[1]}"
                )
            )

            self.broadcast_room_state(
                session.room_id
            )

            return session

        # Reconexão
        elif (
            message_type
            == "RECONNECT"
        ):

            session_id = (
                message.get(
                    "session_id"
                )
            )

            if not isinstance(
                session_id,
                str
            ):

                raise ProtocolError(
                    "Token de sessão inválido."
                )

            session = (
                self.reconnect_session(
                    session_id,
                    sock,
                    address
                )
            )

            self.send_to_session(
                session.session_id,
                {
                    "type":
                        "WELCOME",

                    "session_id":
                        session.session_id,

                    "room_id":
                        session.room_id,

                    "nickname":
                        session.nickname,

                    "server":
                        self.server_name,

                    "reconnected":
                        True
                }
            )

            self.broadcast_room_state(
                session.room_id
            )

            return session

        raise ProtocolError(
            (
                "Primeira mensagem deve "
                "ser JOIN ou RECONNECT."
            )
        )

    # ========================================================
    # THREAD DO CLIENTE
    # ========================================================

    def handle_client(
        self,
        sock,
        address
    ):
        session = None

        try:

            session = self.handshake(
                sock,
                address
            )

            while (
                self.running.is_set()
            ):

                message = (
                    recv_message(
                        sock
                    )
                )

                self.process_message(
                    session.session_id,
                    message
                )

        except ConnectionClosed:
            pass

        except ProtocolError as error:

            self.log(
                "PROTOCOL",
                (
                    f"{address[0]}:"
                    f"{address[1]} "
                    f"- {error}"
                )
            )

        except ValueError as error:

            self.log(
                "ERROR",
                str(error)
            )

            try:

                send_message(
                    sock,
                    {
                        "type":
                            "ERROR",

                        "message":
                            str(error),

                        "server":
                            self.server_name
                    }
                )

            except Exception:
                pass

        except Exception as error:

            self.log(
                "ERROR",
                (
                    "Erro inesperado: "
                    f"{error}"
                )
            )

        finally:

            room_id = None

            if session:

                room_id = (
                    self.mark_disconnected(
                        session.session_id,
                        sock
                    )
                )

            try:

                sock.shutdown(
                    socket.SHUT_RDWR
                )

            except OSError:
                pass

            try:

                sock.close()

            except OSError:
                pass

            # Avisa o outro jogador imediatamente.
            if room_id:

                self.broadcast_room_state(
                    room_id
                )

    # ========================================================
    # START
    # ========================================================

    def start(self):

        self.server_socket = (
            socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM
            )
        )

        self.server_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

        self.server_socket.bind(
            (
                self.host,
                self.port
            )
        )

        self.server_socket.listen(
            50
        )

        self.running.set()

        self.log(
            "SERVER",
            (
                "Servidor iniciado em "
                f"{self.host}:{self.port}"
            )
        )

        self.log(
            "SERVER",
            "Aguardando jogadores..."
        )

        try:

            while (
                self.running.is_set()
            ):

                (
                    client_socket,
                    address
                ) = (
                    self.server_socket
                    .accept()
                )

                thread = (
                    threading.Thread(
                        target=
                            self.handle_client,

                        args=(
                            client_socket,
                            address
                        ),

                        daemon=True
                    )
                )

                thread.start()

        except KeyboardInterrupt:

            self.log(
                "SERVER",
                "Encerrando servidor..."
            )

        finally:

            self.stop()

    # ========================================================
    # STOP
    # ========================================================

    def stop(self):

        self.running.clear()

        if self.server_socket:

            try:
                self.server_socket.close()

            except OSError:
                pass

        with self.state_lock:

            for session in (
                self.sessions.values()
            ):

                if (
                    session.disconnect_timer
                    is not None
                ):

                    session.disconnect_timer.cancel()

                try:
                    session.sock.close()

                except OSError:
                    pass

        self.log(
            "SERVER",
            "Servidor encerrado."
        )


def main():

    parser = (
        argparse.ArgumentParser(
            description=
                "Servidor do Jogo da Forca"
        )
    )

    parser.add_argument(
        "--host",
        default=DEFAULT_HOST
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT
    )

    parser.add_argument(
        "--name",
        default="VM1"
    )

    args = parser.parse_args()

    server = HangmanServer(
        host=args.host,
        port=args.port,
        server_name=args.name
    )

    server.start()


if __name__ == "__main__":
    main()