import random
import string
from dataclasses import dataclass


WORDS = [
    "COMPUTADOR",
    "PROGRAMACAO",
    "SERVIDOR",
    "INTERNET",
    "SOFTWARE",
    "HARDWARE",
    "TECLADO",
    "MONITOR",
    "PROCESSADOR",
    "MEMORIA",
    "SISTEMA",
    "REDE",
    "PYTHON",
    "SOCKET",
    "ALGORITMO",
    "DATABASE",
    "SEGURANCA",
    "PROTOCOLO",
    "VIRTUALIZACAO",
    "TECNOLOGIA",
    "FIREWALL",
    "THREAD",
    "CLIENTE",
    "BACKUP",
    "CONEXAO",
]

MAX_ERRORS = 6


class GameError(Exception):
    pass


@dataclass
class Player:
    session_id: str
    nickname: str
    errors: int = 0


class HangmanGame:

    def __init__(
        self,
        room_id,
        word=None
    ):
        self.room_id = room_id

        self.word = (
            word.upper()
            if word
            else random.choice(WORDS)
        )

        self.players = []

        # Letras pertencem à partida inteira.
        self.guessed_letters = set()

        self.turn_index = 0

        self.started = False
        self.finished = False

        self.winner = None

        # WORD_COMPLETED
        # MAX_ERRORS
        # WORD_GUESS
        # WRONG_WORD
        # WO
        self.finish_reason = None

        self.version = 0

    # ========================================================
    # JOGADORES
    # ========================================================

    def add_player(
        self,
        session_id,
        nickname
    ):
        if self.started:
            raise GameError(
                "A partida já começou."
            )

        if len(self.players) >= 2:
            raise GameError(
                "A sala está cheia."
            )

        if any(
            player.session_id == session_id
            for player in self.players
        ):
            raise GameError(
                "Jogador já está nesta sala."
            )

        nickname = nickname.strip()

        if not nickname:
            raise GameError(
                "Nickname inválido."
            )

        if len(nickname) > 20:
            raise GameError(
                "Nickname muito grande."
            )

        player = Player(
            session_id=session_id,
            nickname=nickname
        )

        self.players.append(
            player
        )

        self.version += 1

        if len(self.players) == 2:
            self.started = True
            self.turn_index = 0

        return player

    # ========================================================
    # BUSCAS
    # ========================================================

    def get_player(
        self,
        session_id
    ):
        for player in self.players:

            if player.session_id == session_id:
                return player

        raise GameError(
            "Jogador não encontrado."
        )

    def get_opponent(
        self,
        session_id
    ):
        for player in self.players:

            if player.session_id != session_id:
                return player

        return None

    def current_player(self):
        if not self.players:
            return None

        return self.players[
            self.turn_index
        ]

    # ========================================================
    # PALAVRA
    # ========================================================

    def masked_word(self):
        resultado = []

        for letra in self.word:

            if letra in self.guessed_letters:
                resultado.append(
                    letra
                )

            elif letra == " ":
                resultado.append(
                    " "
                )

            else:
                resultado.append(
                    "_"
                )

        return " ".join(
            resultado
        )

    def word_completed(self):
        letras_da_palavra = {
            letra
            for letra in self.word
            if letra in string.ascii_uppercase
        }

        return letras_da_palavra.issubset(
            self.guessed_letters
        )

    # ========================================================
    # VALIDAR TURNO
    # ========================================================

    def _validate_turn(
        self,
        session_id
    ):
        if not self.started:
            raise GameError(
                "Aguardando o segundo jogador."
            )

        if self.finished:
            raise GameError(
                "A partida já terminou."
            )

        player = self.get_player(
            session_id
        )

        current = self.current_player()

        if (
            current is None
            or
            current.session_id != session_id
        ):
            raise GameError(
                "Não é a sua vez."
            )

        return player

    # ========================================================
    # CHUTE DE LETRA
    # ========================================================

    def guess(
        self,
        session_id,
        letter
    ):
        player = self._validate_turn(
            session_id
        )

        if not isinstance(
            letter,
            str
        ):
            raise GameError(
                "Letra inválida."
            )

        letter = (
            letter
            .strip()
            .upper()
        )

        if len(letter) != 1:
            raise GameError(
                "Digite apenas uma letra."
            )

        if letter not in string.ascii_uppercase:
            raise GameError(
                "Use apenas letras de A a Z."
            )

        if letter in self.guessed_letters:
            raise GameError(
                "Essa letra já foi utilizada."
            )

        self.guessed_letters.add(
            letter
        )

        acertou = (
            letter in self.word
        )

        if not acertou:
            player.errors += 1

        self.version += 1

        # Descobriu a palavra.
        if self.word_completed():

            self.finished = True
            self.winner = (
                player.session_id
            )

            self.finish_reason = (
                "WORD_COMPLETED"
            )

        # Completou a forca.
        elif player.errors >= MAX_ERRORS:

            opponent = self.get_opponent(
                session_id
            )

            self.finished = True

            if opponent:
                self.winner = (
                    opponent.session_id
                )

            self.finish_reason = (
                "MAX_ERRORS"
            )

        # Toda jogada troca o turno.
        if not self.finished:

            self.turn_index = (
                self.turn_index + 1
            ) % len(self.players)

        return {
            "correct": acertou,
            "letter": letter
        }

    # ========================================================
    # CHUTE DA PALAVRA INTEIRA
    # ========================================================

    def guess_word(
        self,
        session_id,
        word
    ):
        player = self._validate_turn(
            session_id
        )

        if not isinstance(
            word,
            str
        ):
            raise GameError(
                "Palavra inválida."
            )

        word = (
            word
            .strip()
            .upper()
        )

        if not word:
            raise GameError(
                "Digite uma palavra."
            )

        if len(word) > 50:
            raise GameError(
                "Palavra grande demais."
            )

        if not all(
            char in string.ascii_uppercase
            for char in word
        ):
            raise GameError(
                "Use apenas letras de A a Z."
            )

        self.version += 1

        # ACERTOU A PALAVRA
        if word == self.word:

            self.finished = True

            self.winner = (
                player.session_id
            )

            self.finish_reason = (
                "WORD_GUESS"
            )

            self.guessed_letters.update(
                {
                    letra
                    for letra in self.word
                    if letra in string.ascii_uppercase
                }
            )

            return {
                "correct": True
            }

        # ERROU = PERDE IMEDIATAMENTE
        opponent = self.get_opponent(
            session_id
        )

        self.finished = True

        if opponent:
            self.winner = (
                opponent.session_id
            )

        self.finish_reason = (
            "WRONG_WORD"
        )

        return {
            "correct": False
        }

    # ========================================================
    # VITÓRIA POR W.O.
    # ========================================================

    def finish_by_walkover(
        self,
        disconnected_session_id
    ):
        if not self.started:
            return False

        if self.finished:
            return False

        opponent = self.get_opponent(
            disconnected_session_id
        )

        if opponent is None:
            return False

        self.finished = True

        self.winner = (
            opponent.session_id
        )

        self.finish_reason = "WO"

        self.version += 1

        return True

    # ========================================================
    # ESTADO PÚBLICO
    # ========================================================

    def public_state(
        self,
        session_id
    ):
        player = self.get_player(
            session_id
        )

        opponent = self.get_opponent(
            session_id
        )

        current = self.current_player()

        estado = {
            "type": "GAME_STATE",

            "room_id": self.room_id,

            "started": self.started,
            "finished": self.finished,

            "version": self.version,

            "word": self.masked_word(),

            "used_letters": sorted(
                self.guessed_letters
            ),

            "your_turn": (
                self.started
                and
                current is not None
                and
                current.session_id == session_id
                and
                not self.finished
            ),

            "you": {
                "nickname":
                    player.nickname,

                "errors":
                    player.errors,

                "max_errors":
                    MAX_ERRORS,
            },

            "opponent": None,

            "winner": None,

            "finish_reason":
                self.finish_reason,

            # Palavra real só aparece no fim.
            "answer": (
                self.word
                if self.finished
                else None
            )
        }

        if opponent:

            estado["opponent"] = {
                "nickname":
                    opponent.nickname,

                "errors":
                    opponent.errors,

                "max_errors":
                    MAX_ERRORS,
            }

        if self.finished:

            if self.winner == session_id:
                estado["winner"] = "YOU"

            else:
                estado["winner"] = "OPPONENT"

        return estado

    # ========================================================
    # SNAPSHOT PARA OUTRO SERVIDOR
    # ========================================================

    def snapshot(self):
        return {
            "room_id":
                self.room_id,

            "word":
                self.word,

            "guessed_letters":
                sorted(
                    self.guessed_letters
                ),

            "turn_index":
                self.turn_index,

            "started":
                self.started,

            "finished":
                self.finished,

            "winner":
                self.winner,

            "finish_reason":
                self.finish_reason,

            "version":
                self.version,

            "players": [
                {
                    "session_id":
                        player.session_id,

                    "nickname":
                        player.nickname,

                    "errors":
                        player.errors,
                }

                for player
                in self.players
            ]
        }

    # ========================================================
    # RESTAURAR SNAPSHOT
    # ========================================================

    @classmethod
    def from_snapshot(
        cls,
        data
    ):
        game = cls(
            room_id=data[
                "room_id"
            ],

            word=data[
                "word"
            ]
        )

        game.guessed_letters = set(
            data.get(
                "guessed_letters",
                []
            )
        )

        game.turn_index = data[
            "turn_index"
        ]

        game.started = data[
            "started"
        ]

        game.finished = data[
            "finished"
        ]

        game.winner = data[
            "winner"
        ]

        game.finish_reason = (
            data.get(
                "finish_reason"
            )
        )

        game.version = data[
            "version"
        ]

        game.players = []

        for player_data in data[
            "players"
        ]:

            player = Player(
                session_id=
                    player_data[
                        "session_id"
                    ],

                nickname=
                    player_data[
                        "nickname"
                    ],

                errors=
                    player_data[
                        "errors"
                    ]
            )

            game.players.append(
                player
            )

        return game