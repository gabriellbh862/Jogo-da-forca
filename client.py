import json
import os
import queue
import socket
import threading
import tkinter as tk
from tkinter import messagebox

from protocol import (
    send_message,
    recv_message,
    ConnectionClosed
)


SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000

SESSION_PROFILE = os.getenv(
    "FORCA_PROFILE",
    "default"
)

SESSION_FILE = os.path.join(
    os.path.dirname(
        os.path.abspath(__file__)
    ),
    f".forca_session_{SESSION_PROFILE}.json"
)


class HangmanClient:

    def __init__(self):

        self.root = tk.Tk()

        self.root.title(
            "Jogo da Forca"
        )

        self.root.geometry(
            "1050x850"
        )

        self.root.resizable(
            False,
            False
        )

        self.sock = None

        self.session_id = None

        self.connected = False

        self.awaiting_handshake = False

        self.game_state = None

        self.messages = (
            queue.Queue()
        )

        # Evita thread antiga derrubar
        # uma conexão nova.
        self.connection_generation = 0

        # Countdown do adversário.
        self.countdown_job = None

        self.countdown_remaining = 0

        self.saved_session = (
            self.load_saved_session()
        )

        self.create_login_screen()

        self.root.after(
            100,
            self.process_messages
        )

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close
        )

    # ========================================================
    # SESSÃO LOCAL
    # ========================================================

    def load_saved_session(self):

        if not os.path.exists(
            SESSION_FILE
        ):
            return None

        try:

            with open(
                SESSION_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(
                    file
                )

            if not isinstance(
                data,
                dict
            ):
                return None

            if not data.get(
                "session_id"
            ):
                return None

            return data

        except (
            OSError,
            json.JSONDecodeError
        ):
            return None

    def save_session(
        self,
        session_id,
        nickname,
        room_id
    ):

        data = {
            "session_id":
                session_id,

            "nickname":
                nickname,

            "room_id":
                room_id
        }

        try:

            with open(
                SESSION_FILE,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    data,
                    file,
                    ensure_ascii=False,
                    indent=2
                )

            self.saved_session = (
                data
            )

        except OSError:
            pass

    def clear_saved_session(
        self
    ):

        self.saved_session = None

        try:

            if os.path.exists(
                SESSION_FILE
            ):

                os.remove(
                    SESSION_FILE
                )

        except OSError:
            pass

    # ========================================================
    # COUNTDOWN
    # ========================================================

    def cancel_countdown(
        self
    ):

        if (
            self.countdown_job
            is not None
        ):

            try:

                self.root.after_cancel(
                    self.countdown_job
                )

            except Exception:
                pass

        self.countdown_job = None

    def start_countdown(
        self,
        seconds
    ):

        self.cancel_countdown()

        self.countdown_remaining = max(
            0,
            int(seconds)
        )

        self.render_countdown()

    def render_countdown(
        self
    ):

        if not hasattr(
            self,
            "status_label"
        ):
            return

        if (
            self.countdown_remaining
            <= 0
        ):

            self.status_label.config(
                text=(
                    "Tempo de reconexão esgotado. "
                    "Aguardando confirmação do servidor..."
                ),
                fg="red"
            )

            self.countdown_job = None

            return

        self.status_label.config(
            text=(
                "Adversário desconectado. "
                f"Tempo para retornar: "
                f"{self.countdown_remaining}s"
            ),
            fg="darkorange"
        )

        self.countdown_remaining -= 1

        self.countdown_job = (
            self.root.after(
                1000,
                self.render_countdown
            )
        )

    # ========================================================
    # LIMPAR TELA
    # ========================================================

    def clear(self):

        self.cancel_countdown()

        for widget in (
            self.root.winfo_children()
        ):

            widget.destroy()

    # ========================================================
    # LOGIN
    # ========================================================

    def create_login_screen(self):

        self.clear()

        self.saved_session = (
            self.load_saved_session()
        )

        container = tk.Frame(
            self.root,
            padx=50,
            pady=40
        )

        container.pack(
            expand=True
        )

        tk.Label(
            container,
            text="JOGO DA FORCA",
            font=(
                "Arial",
                34,
                "bold"
            )
        ).pack(
            pady=15
        )

        tk.Label(
            container,
            text=(
                "Jogo distribuído • "
                "Cliente / Servidor"
            ),
            font=(
                "Arial",
                13
            )
        ).pack(
            pady=5
        )

        # ====================================================
        # SESSÃO ANTIGA
        # ====================================================

        if self.saved_session:

            old_frame = tk.Frame(
                container,
                bd=1,
                relief="solid",
                padx=20,
                pady=15
            )

            old_frame.pack(
                pady=20,
                fill="x"
            )

            tk.Label(
                old_frame,
                text=(
                    "PARTIDA INTERROMPIDA ENCONTRADA"
                ),
                font=(
                    "Arial",
                    12,
                    "bold"
                )
            ).pack()

            tk.Label(
                old_frame,
                text=(
                    f"Jogador: "
                    f"{self.saved_session.get('nickname', '-')}\n"
                    f"Sala: "
                    f"{self.saved_session.get('room_id', '-')}"
                ),
                font=(
                    "Arial",
                    11
                )
            ).pack(
                pady=8
            )

            tk.Button(
                old_frame,
                text="RECONECTAR À PARTIDA",
                font=(
                    "Arial",
                    11,
                    "bold"
                ),
                command=
                    self.reconnect_saved_session
            ).pack(
                pady=5
            )

        # ====================================================
        # NOVA PARTIDA
        # ====================================================

        tk.Label(
            container,
            text="Nova partida",
            font=(
                "Arial",
                14,
                "bold"
            )
        ).pack(
            pady=(
                15,
                5
            )
        )

        tk.Label(
            container,
            text="Seu nome:",
            font=(
                "Arial",
                12
            )
        ).pack()

        self.nickname_entry = (
            tk.Entry(
                container,
                font=(
                    "Arial",
                    15
                ),
                width=25,
                justify="center"
            )
        )

        self.nickname_entry.pack(
            pady=10
        )

        self.nickname_entry.focus()

        self.nickname_entry.bind(
            "<Return>",
            lambda event:
                self.connect_new_player()
        )

        tk.Button(
            container,
            text="ENTRAR EM NOVA PARTIDA",
            font=(
                "Arial",
                12,
                "bold"
            ),
            command=
                self.connect_new_player
        ).pack(
            pady=10
        )

        self.login_status = (
            tk.Label(
                container,
                text=(
                    f"Servidor: "
                    f"{SERVER_HOST}:"
                    f"{SERVER_PORT}"
                ),
                font=(
                    "Arial",
                    10
                )
            )
        )

        self.login_status.pack(
            pady=10
        )

    # ========================================================
    # SOCKET
    # ========================================================

    def close_socket_only(
        self
    ):

        old_socket = (
            self.sock
        )

        self.sock = None

        if old_socket:

            try:

                old_socket.shutdown(
                    socket.SHUT_RDWR
                )

            except OSError:
                pass

            try:

                old_socket.close()

            except OSError:
                pass

    def open_connection(
        self,
        handshake_payload,
        show_game_screen=True
    ):

        # Nova geração.
        self.connection_generation += 1

        generation = (
            self.connection_generation
        )

        self.connected = False

        self.close_socket_only()

        new_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        new_socket.settimeout(
            5
        )

        new_socket.connect(
            (
                SERVER_HOST,
                SERVER_PORT
            )
        )

        new_socket.settimeout(
            None
        )

        send_message(
            new_socket,
            handshake_payload
        )

        self.sock = new_socket

        self.connected = True

        self.awaiting_handshake = True

        if show_game_screen:

            self.create_game_screen()

        thread = threading.Thread(
            target=self.listen_server,
            args=(
                new_socket,
                generation
            ),
            daemon=True
        )

        thread.start()

    # ========================================================
    # NOVO JOGADOR
    # ========================================================

    def connect_new_player(
        self
    ):

        nickname = (
            self.nickname_entry
            .get()
            .strip()
        )

        if not nickname:

            messagebox.showwarning(
                "Atenção",
                "Digite seu nome."
            )

            return

        # Nova partida significa abandonar
        # token antigo salvo localmente.
        self.clear_saved_session()

        try:

            self.login_status.config(
                text="Conectando..."
            )

            self.open_connection(
                {
                    "type":
                        "JOIN",

                    "nickname":
                        nickname
                }
            )

        except OSError as error:

            self.connected = False

            messagebox.showerror(
                "Erro de conexão",
                (
                    "Não foi possível conectar.\n\n"
                    f"{error}"
                )
            )

    # ========================================================
    # RECONECTAR PARTIDA SALVA
    # ========================================================

    def reconnect_saved_session(
        self
    ):

        session = (
            self.load_saved_session()
        )

        if not session:

            messagebox.showwarning(
                "Reconexão",
                "Nenhuma sessão salva."
            )

            return

        session_id = (
            session.get(
                "session_id"
            )
        )

        if not session_id:

            self.clear_saved_session()
            self.create_login_screen()
            return

        self.session_id = (
            session_id
        )

        try:

            if hasattr(
                self,
                "login_status"
            ):

                self.login_status.config(
                    text="Reconectando..."
                )

            self.open_connection(
                {
                    "type":
                        "RECONNECT",

                    "session_id":
                        session_id
                }
            )

        except OSError as error:

            self.connected = False

            messagebox.showerror(
                "Reconexão",
                (
                    "Não foi possível reconectar.\n\n"
                    f"{error}"
                )
            )

    # ========================================================
    # RECONECTAR SEM FECHAR A JANELA
    # ========================================================

    def retry_reconnect(
        self
    ):

        session_id = (
            self.session_id
        )

        if not session_id:

            saved = (
                self.load_saved_session()
            )

            if saved:

                session_id = (
                    saved.get(
                        "session_id"
                    )
                )

        if not session_id:

            self.status_label.config(
                text=(
                    "Não existe sessão para reconectar."
                ),
                fg="red"
            )

            return

        self.server_label.config(
            text="● RECONECTANDO...",
            fg="darkorange"
        )

        self.status_label.config(
            text=(
                "Tentando recuperar sua sessão..."
            ),
            fg="darkorange"
        )

        try:

            self.open_connection(
                {
                    "type":
                        "RECONNECT",

                    "session_id":
                        session_id
                },
                show_game_screen=False
            )

        except OSError as error:

            self.connected = False

            self.server_label.config(
                text="● DESCONECTADO",
                fg="red"
            )

            self.status_label.config(
                text=(
                    "Falha ao reconectar: "
                    f"{error}"
                ),
                fg="red"
            )

    # ========================================================
    # TELA DO JOGO
    # ========================================================

    def create_game_screen(self):

        self.clear()

        # ====================================================
        # TOPO
        # ====================================================

        top = tk.Frame(
            self.root,
            pady=8
        )

        top.pack(
            fill="x"
        )

        self.room_label = tk.Label(
            top,
            text="Sala: aguardando...",
            font=(
                "Arial",
                14,
                "bold"
            )
        )

        self.room_label.pack(
            side="left",
            padx=25
        )

        self.server_label = tk.Label(
            top,
            text="● CONECTADO",
            font=(
                "Arial",
                12,
                "bold"
            ),
            fg="green"
        )

        self.server_label.pack(
            side="right",
            padx=25
        )

        self.turn_label = tk.Label(
            self.root,
            text="AGUARDANDO JOGADOR...",
            font=(
                "Arial",
                20,
                "bold"
            )
        )

        self.turn_label.pack(
            pady=5
        )

        # ====================================================
        # PALAVRA
        # ====================================================

        tk.Label(
            self.root,
            text="PALAVRA",
            font=(
                "Arial",
                12,
                "bold"
            )
        ).pack()

        self.word_label = tk.Label(
            self.root,
            text="_ _ _ _ _",
            font=(
                "Courier",
                28,
                "bold"
            )
        )

        self.word_label.pack(
            pady=5
        )

        # ====================================================
        # FORCAS
        # ====================================================

        players_frame = tk.Frame(
            self.root
        )

        players_frame.pack(
            pady=4
        )

        # VOCÊ
        your_frame = tk.Frame(
            players_frame,
            padx=20
        )

        your_frame.pack(
            side="left",
            padx=20
        )

        self.your_name_label = tk.Label(
            your_frame,
            text="VOCÊ",
            font=(
                "Arial",
                15,
                "bold"
            )
        )

        self.your_name_label.pack()

        self.your_canvas = tk.Canvas(
            your_frame,
            width=300,
            height=270,
            bg="white",
            highlightthickness=1,
            highlightbackground="#cccccc"
        )

        self.your_canvas.pack(
            pady=4
        )

        self.your_errors_label = tk.Label(
            your_frame,
            text="Erros: 0/6",
            font=(
                "Arial",
                12
            )
        )

        self.your_errors_label.pack()

        # ADVERSÁRIO
        opponent_frame = tk.Frame(
            players_frame,
            padx=20
        )

        opponent_frame.pack(
            side="right",
            padx=20
        )

        self.opponent_name_label = tk.Label(
            opponent_frame,
            text="ADVERSÁRIO",
            font=(
                "Arial",
                15,
                "bold"
            )
        )

        self.opponent_name_label.pack()

        self.opponent_canvas = tk.Canvas(
            opponent_frame,
            width=300,
            height=270,
            bg="white",
            highlightthickness=1,
            highlightbackground="#cccccc"
        )

        self.opponent_canvas.pack(
            pady=4
        )

        self.opponent_errors_label = tk.Label(
            opponent_frame,
            text="Aguardando...",
            font=(
                "Arial",
                12
            )
        )

        self.opponent_errors_label.pack()

        # ====================================================
        # LETRAS
        # ====================================================

        self.used_letters_label = tk.Label(
            self.root,
            text="Letras usadas: -",
            font=(
                "Arial",
                11
            )
        )

        self.used_letters_label.pack(
            pady=3
        )

        keyboard_frame = tk.Frame(
            self.root
        )

        keyboard_frame.pack(
            pady=4
        )

        self.letter_buttons = {}

        letters = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        )

        for (
            index,
            letter
        ) in enumerate(letters):

            row = index // 13

            column = index % 13

            button = tk.Button(
                keyboard_frame,
                text=letter,
                width=4,
                height=2,
                font=(
                    "Arial",
                    10,
                    "bold"
                ),
                command=
                    lambda value=letter:
                        self.guess_letter(
                            value
                        )
            )

            button.grid(
                row=row,
                column=column,
                padx=2,
                pady=2
            )

            self.letter_buttons[
                letter
            ] = button

        # ====================================================
        # CHUTE DA PALAVRA
        # ====================================================

        word_guess_frame = tk.Frame(
            self.root,
            pady=4
        )

        word_guess_frame.pack()

        tk.Label(
            word_guess_frame,
            text="Chutar palavra:",
            font=(
                "Arial",
                11,
                "bold"
            )
        ).pack(
            side="left",
            padx=5
        )

        self.word_guess_entry = tk.Entry(
            word_guess_frame,
            width=24,
            font=(
                "Arial",
                13
            ),
            justify="center"
        )

        self.word_guess_entry.pack(
            side="left",
            padx=5
        )

        self.word_guess_entry.bind(
            "<Return>",
            lambda event:
                self.guess_word()
        )

        self.word_guess_button = tk.Button(
            word_guess_frame,
            text="CHUTAR PALAVRA",
            font=(
                "Arial",
                10,
                "bold"
            ),
            command=
                self.guess_word
        )

        self.word_guess_button.pack(
            side="left",
            padx=5
        )

        tk.Label(
            self.root,
            text=(
                "⚠ Se errar a palavra, "
                "você perde imediatamente."
            ),
            font=(
                "Arial",
                9
            ),
            fg="darkred"
        ).pack()

        # ====================================================
        # STATUS
        # ====================================================

        self.status_label = tk.Label(
            self.root,
            text="Conectado.",
            font=(
                "Arial",
                11,
                "bold"
            ),
            pady=5
        )

        self.status_label.pack()

        self.reconnect_button = tk.Button(
            self.root,
            text="TENTAR RECONECTAR",
            font=(
                "Arial",
                10,
                "bold"
            ),
            command=
                self.retry_reconnect
        )

        self.reconnect_button.pack(
            pady=3
        )

        self.reconnect_button.pack_forget()

        self.disable_actions()

        self.draw_hangman(
            self.your_canvas,
            0
        )

        self.draw_hangman(
            self.opponent_canvas,
            0
        )

    # ========================================================
    # RECEBER SERVIDOR
    # ========================================================

    def listen_server(
        self,
        sock,
        generation
    ):

        try:

            while (
                self.connected
                and
                generation
                ==
                self.connection_generation
            ):

                message = recv_message(
                    sock
                )

                self.messages.put(
                    message
                )

        except (
            ConnectionClosed,
            OSError
        ):

            if (
                generation
                ==
                self.connection_generation
                and
                self.connected
            ):

                self.messages.put(
                    {
                        "type":
                            "CONNECTION_LOST"
                    }
                )

    # ========================================================
    # FILA TKINTER
    # ========================================================

    def process_messages(self):

        try:

            while True:

                message = (
                    self.messages
                    .get_nowait()
                )

                self.handle_message(
                    message
                )

        except queue.Empty:
            pass

        self.root.after(
            100,
            self.process_messages
        )

    # ========================================================
    # MENSAGENS
    # ========================================================

    def handle_message(
        self,
        message
    ):

        message_type = (
            message.get(
                "type"
            )
        )

        # ====================================================
        # BEM-VINDO / RECONECTOU
        # ====================================================

        if (
            message_type
            == "WELCOME"
        ):

            self.awaiting_handshake = (
                False
            )

            self.connected = True

            self.session_id = (
                message.get(
                    "session_id"
                )
            )

            room = (
                message.get(
                    "room_id"
                )
            )

            nickname = (
                message.get(
                    "nickname"
                )
            )

            server = (
                message.get(
                    "server"
                )
            )

            self.save_session(
                self.session_id,
                nickname,
                room
            )

            self.room_label.config(
                text=f"Sala: {room}"
            )

            self.server_label.config(
                text=(
                    f"● {server} CONECTADO"
                ),
                fg="green"
            )

            self.reconnect_button.pack_forget()

        # ====================================================
        # ESTADO
        # ====================================================

        elif (
            message_type
            == "GAME_STATE"
        ):

            self.game_state = (
                message
            )

            self.update_game(
                message
            )

        # ====================================================
        # ERRO
        # ====================================================

        elif (
            message_type
            == "ERROR"
        ):

            text = (
                message.get(
                    "message",
                    "Erro."
                )
            )

            # Erro durante RECONNECT/JOIN.
            if self.awaiting_handshake:

                self.awaiting_handshake = (
                    False
                )

                self.connected = False

                self.close_socket_only()

                # Token provavelmente expirou
                # ou servidor reiniciou.
                if (
                    "Sessão não encontrada"
                    in text
                ):

                    self.clear_saved_session()

                messagebox.showerror(
                    "Conexão",
                    text
                )

                self.create_login_screen()

                return

            self.status_label.config(
                text=text,
                fg="red"
            )

            if self.game_state:

                self.update_action_controls(
                    self.game_state
                )

        # ====================================================
        # CONEXÃO CAIU
        # ====================================================

        elif (
            message_type
            == "CONNECTION_LOST"
        ):

            self.connected = False

            self.awaiting_handshake = (
                False
            )

            self.server_label.config(
                text="● DESCONECTADO",
                fg="red"
            )

            self.status_label.config(
                text=(
                    "Conexão perdida. "
                    "Você tem até 40 segundos "
                    "para retornar."
                ),
                fg="red"
            )

            self.disable_actions()

            self.reconnect_button.pack(
                pady=3
            )

    # ========================================================
    # ATUALIZAR JOGO
    # ========================================================

    def update_game(
        self,
        state
    ):

        word = state.get(
            "word",
            ""
        )

        you = state.get(
            "you",
            {}
        )

        opponent = state.get(
            "opponent"
        )

        used_letters = state.get(
            "used_letters",
            []
        )

        started = state.get(
            "started",
            False
        )

        finished = state.get(
            "finished",
            False
        )

        your_turn = state.get(
            "your_turn",
            False
        )

        opponent_connected = state.get(
            "opponent_connected",
            True
        )

        reconnect_seconds = state.get(
            "opponent_reconnect_seconds",
            0
        )

        # ====================================================
        # PALAVRA
        # ====================================================

        self.word_label.config(
            text=word
        )

        if used_letters:

            self.used_letters_label.config(
                text=(
                    "Letras usadas: "
                    +
                    " • ".join(
                        used_letters
                    )
                )
            )

        else:

            self.used_letters_label.config(
                text="Letras usadas: -"
            )

        # ====================================================
        # VOCÊ
        # ====================================================

        your_name = you.get(
            "nickname",
            "Você"
        )

        your_errors = you.get(
            "errors",
            0
        )

        your_max = you.get(
            "max_errors",
            6
        )

        self.your_name_label.config(
            text=(
                f"VOCÊ — {your_name}"
            )
        )

        self.your_errors_label.config(
            text=(
                f"Erros: "
                f"{your_errors}/"
                f"{your_max}"
            )
        )

        self.draw_hangman(
            self.your_canvas,
            your_errors
        )

        # ====================================================
        # ADVERSÁRIO
        # ====================================================

        if opponent:

            opponent_name = (
                opponent.get(
                    "nickname",
                    "Adversário"
                )
            )

            opponent_errors = (
                opponent.get(
                    "errors",
                    0
                )
            )

            opponent_max = (
                opponent.get(
                    "max_errors",
                    6
                )
            )

            self.opponent_name_label.config(
                text=(
                    "ADVERSÁRIO — "
                    f"{opponent_name}"
                )
            )

            self.opponent_errors_label.config(
                text=(
                    f"Erros: "
                    f"{opponent_errors}/"
                    f"{opponent_max}"
                )
            )

            self.draw_hangman(
                self.opponent_canvas,
                opponent_errors
            )

        else:

            self.opponent_name_label.config(
                text="ADVERSÁRIO"
            )

            self.opponent_errors_label.config(
                text="Aguardando..."
            )

            self.draw_hangman(
                self.opponent_canvas,
                0
            )

        # ====================================================
        # JOGO TERMINADO
        # ====================================================

        if finished:

            self.cancel_countdown()

            winner = state.get(
                "winner"
            )

            reason = state.get(
                "finish_reason"
            )

            answer = state.get(
                "answer"
            )

            if winner == "YOU":

                if reason == "WO":

                    self.turn_label.config(
                        text=(
                            "★ VITÓRIA POR W.O. ★"
                        ),
                        fg="green"
                    )

                    text = (
                        "O adversário não retornou "
                        "em 40 segundos."
                    )

                else:

                    self.turn_label.config(
                        text=(
                            "★ VOCÊ VENCEU! ★"
                        ),
                        fg="green"
                    )

                    text = (
                        "Parabéns! Você venceu."
                    )

            else:

                if reason == "WO":

                    self.turn_label.config(
                        text="DERROTA POR W.O.",
                        fg="red"
                    )

                    text = (
                        "O tempo de reconexão expirou."
                    )

                elif reason == "WRONG_WORD":

                    self.turn_label.config(
                        text="PALPITE INCORRETO",
                        fg="red"
                    )

                    text = (
                        "O chute da palavra estava errado."
                    )

                else:

                    self.turn_label.config(
                        text="VOCÊ PERDEU",
                        fg="red"
                    )

                    text = (
                        "Seu adversário venceu."
                    )

            if answer:

                self.word_label.config(
                    text=" ".join(
                        answer
                    )
                )

                text += (
                    f" Palavra: {answer}"
                )

            self.status_label.config(
                text=text,
                fg=(
                    "green"
                    if winner == "YOU"
                    else "red"
                )
            )

            self.disable_actions()

            self.reconnect_button.pack_forget()

            # Jogo acabou; não precisa mais
            # oferecer essa sessão no próximo boot.
            self.clear_saved_session()

            return

        # ====================================================
        # AINDA NÃO COMEÇOU
        # ====================================================

        if not started:

            self.cancel_countdown()

            self.turn_label.config(
                text="AGUARDANDO JOGADOR...",
                fg="orange"
            )

            self.status_label.config(
                text=(
                    "Esperando outro jogador entrar."
                ),
                fg="black"
            )

            self.disable_actions()

            return

        # ====================================================
        # ADVERSÁRIO CAIU
        # ====================================================

        if (
            opponent
            and
            not opponent_connected
        ):

            self.turn_label.config(
                text=(
                    "⚠ ADVERSÁRIO DESCONECTADO"
                ),
                fg="darkorange"
            )

            self.disable_actions()

            self.start_countdown(
                reconnect_seconds
            )

            return

        self.cancel_countdown()

        # ====================================================
        # TURNO
        # ====================================================

        if your_turn:

            self.turn_label.config(
                text="★ SUA VEZ ★",
                fg="green"
            )

            self.status_label.config(
                text=(
                    "Escolha uma letra "
                    "ou chute a palavra."
                ),
                fg="black"
            )

        else:

            self.turn_label.config(
                text="VEZ DO ADVERSÁRIO",
                fg="blue"
            )

            self.status_label.config(
                text=(
                    "Aguarde a jogada "
                    "do adversário."
                ),
                fg="black"
            )

        self.update_action_controls(
            state
        )

    # ========================================================
    # CONTROLES
    # ========================================================

    def update_action_controls(
        self,
        state
    ):

        if (
            not self.connected
            or
            not state.get(
                "started",
                False
            )
            or
            state.get(
                "finished",
                False
            )
            or
            not state.get(
                "your_turn",
                False
            )
            or
            not state.get(
                "opponent_connected",
                True
            )
        ):

            self.disable_actions()

            return

        used_letters = set(
            state.get(
                "used_letters",
                []
            )
        )

        for (
            letter,
            button
        ) in (
            self.letter_buttons.items()
        ):

            if letter in used_letters:

                button.config(
                    state="disabled"
                )

            else:

                button.config(
                    state="normal"
                )

        self.word_guess_entry.config(
            state="normal"
        )

        self.word_guess_button.config(
            state="normal"
        )

    def disable_actions(self):

        if hasattr(
            self,
            "letter_buttons"
        ):

            for button in (
                self.letter_buttons.values()
            ):

                button.config(
                    state="disabled"
                )

        if hasattr(
            self,
            "word_guess_entry"
        ):

            self.word_guess_entry.config(
                state="disabled"
            )

        if hasattr(
            self,
            "word_guess_button"
        ):

            self.word_guess_button.config(
                state="disabled"
            )

    # ========================================================
    # CHUTE DE LETRA
    # ========================================================

    def guess_letter(
        self,
        letter
    ):

        if not self.connected:
            return

        try:

            send_message(
                self.sock,
                {
                    "type":
                        "GUESS",

                    "letter":
                        letter
                }
            )

            self.disable_actions()

            self.status_label.config(
                text=(
                    f"Enviando letra "
                    f"{letter}..."
                ),
                fg="black"
            )

        except OSError:

            self.status_label.config(
                text=(
                    "Erro ao enviar jogada."
                ),
                fg="red"
            )

    # ========================================================
    # CHUTE DA PALAVRA
    # ========================================================

    def guess_word(self):

        if not self.connected:
            return

        word = (
            self.word_guess_entry
            .get()
            .strip()
        )

        if not word:

            self.status_label.config(
                text=(
                    "Digite uma palavra antes de chutar."
                ),
                fg="red"
            )

            return

        try:

            send_message(
                self.sock,
                {
                    "type":
                        "GUESS_WORD",

                    "word":
                        word
                }
            )

            self.disable_actions()

            self.status_label.config(
                text=(
                    "Enviando chute da palavra..."
                ),
                fg="black"
            )

        except OSError:

            self.status_label.config(
                text=(
                    "Erro ao enviar chute."
                ),
                fg="red"
            )

    # ========================================================
    # DESENHAR FORCA
    # ========================================================

    def draw_hangman(
        self,
        canvas,
        errors
    ):

        canvas.delete(
            "all"
        )

        # Chão
        canvas.create_line(
            35,
            255,
            265,
            255,
            width=4
        )

        # Poste
        canvas.create_line(
            70,
            255,
            70,
            25,
            width=4
        )

        # Topo
        canvas.create_line(
            70,
            25,
            205,
            25,
            width=4
        )

        # Suporte
        canvas.create_line(
            70,
            60,
            105,
            25,
            width=3
        )

        # Corda
        canvas.create_line(
            205,
            25,
            205,
            60,
            width=3
        )

        # Cabeça
        if errors >= 1:

            canvas.create_oval(
                180,
                60,
                230,
                110,
                width=3
            )

        # Corpo
        if errors >= 2:

            canvas.create_line(
                205,
                110,
                205,
                185,
                width=3
            )

        # Braço esquerdo
        if errors >= 3:

            canvas.create_line(
                205,
                130,
                170,
                160,
                width=3
            )

        # Braço direito
        if errors >= 4:

            canvas.create_line(
                205,
                130,
                240,
                160,
                width=3
            )

        # Perna esquerda
        if errors >= 5:

            canvas.create_line(
                205,
                185,
                172,
                230,
                width=3
            )

        # Perna direita
        if errors >= 6:

            canvas.create_line(
                205,
                185,
                238,
                230,
                width=3
            )

    # ========================================================
    # FECHAR
    # ========================================================

    def close(self):

        self.connected = False

        self.connection_generation += 1

        self.cancel_countdown()

        self.close_socket_only()

        self.root.destroy()

    def run(self):

        self.root.mainloop()


if __name__ == "__main__":

    client = HangmanClient()

    client.run()