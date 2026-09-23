import random
import string
from dataclasses import dataclass, field


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
]


MAX_ERRORS = 6


class GameError(Exception):
    pass


@dataclass
class Player:
    session_id: str
    nickname: str

    guessed_letters: set = field(default_factory=set)

    errors: int = 0


class HangmanGame:

    def __init__(self, room_id, word=None):

        self.room_id = room_id

        self.word = (
            word.upper()
            if word
            else random.choice(WORDS)
        )

        self.players = []

        self.turn_index = 0

        self.started = False
        self.finished = False

        self.winner = None

        self.version = 0

    # -----------------------------------------------------
    # JOGADORES
    # -----------------------------------------------------

    def add_player(self, session_id, nickname):

        if self.started:
            raise GameError("A partida já começou.")

        if len(self.players) >= 2:
            raise GameError("A sala está cheia.")

        if any(
            player.session_id == session_id
            for player in self.players
        ):
            raise GameError("Jogador já está nesta sala.")

        nickname = nickname.strip()

        if not nickname:
            raise GameError("Nickname inválido.")

        if len(nickname) > 20:
            raise GameError("Nickname muito grande.")

        player = Player(
            session_id=session_id,
            nickname=nickname
        )

        self.players.append(player)

        self.version += 1

        if len(self.players) == 2:
            self.started = True
            self.turn_index = 0

        return player

    # -----------------------------------------------------
    # BUSCAS
    # -----------------------------------------------------

    def get_player(self, session_id):

        for player in self.players:

            if player.session_id == session_id:
                return player

        raise GameError("Jogador não encontrado.")

    def get_opponent(self, session_id):

        for player in self.players:

            if player.session_id != session_id:
                return player

        return None

    def current_player(self):

        if not self.players:
            return None

        return self.players[self.turn_index]

    # -----------------------------------------------------
    # PALAVRA MASCARADA
    # -----------------------------------------------------

    def masked_word(self, player):

        resultado = []

        for letra in self.word:

            if letra in player.guessed_letters:
                resultado.append(letra)

            elif letra == " ":
                resultado.append(" ")

            else:
                resultado.append("_")

        return " ".join(resultado)

    def player_completed_word(self, player):

        letras_da_palavra = {
            letra
            for letra in self.word
            if letra in string.ascii_uppercase
        }

        return letras_da_palavra.issubset(
            player.guessed_letters
        )

    # -----------------------------------------------------
    # JOGADA
    # -----------------------------------------------------

    def guess(self, session_id, letter):

        if not self.started:
            raise GameError(
                "Aguardando o segundo jogador."
            )

        if self.finished:
            raise GameError(
                "A partida já terminou."
            )

        player = self.get_player(session_id)

        current = self.current_player()

        if current.session_id != session_id:
            raise GameError(
                "Não é a sua vez."
            )

        if not isinstance(letter, str):
            raise GameError(
                "Letra inválida."
            )

        letter = letter.strip().upper()

        if len(letter) != 1:
            raise GameError(
                "Digite apenas uma letra."
            )

        if letter not in string.ascii_uppercase:
            raise GameError(
                "Use apenas letras de A a Z."
            )

        if letter in player.guessed_letters:
            raise GameError(
                "Você já tentou essa letra."
            )

        # registra tentativa
        player.guessed_letters.add(letter)

        acertou = letter in self.word

        if not acertou:
            player.errors += 1

        self.version += 1

        # -------------------------------------------------
        # VERIFICAR VITÓRIA
        # -------------------------------------------------

        if self.player_completed_word(player):

            self.finished = True
            self.winner = player.session_id

        elif player.errors >= MAX_ERRORS:

            opponent = self.get_opponent(
                session_id
            )

            self.finished = True

            if opponent:
                self.winner = opponent.session_id

        # -------------------------------------------------
        # TROCAR TURNO
        # -------------------------------------------------

        if not self.finished:

            self.turn_index = (
                self.turn_index + 1
            ) % len(self.players)

        return {
            "correct": acertou,
            "letter": letter
        }

    # -----------------------------------------------------
    # ESTADO PÚBLICO
    # -----------------------------------------------------

    def public_state(self, session_id):

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

            "your_turn": (
                current is not None
                and
                current.session_id == session_id
                and
                not self.finished
            ),

            "you": {
                "nickname": player.nickname,

                "word": self.masked_word(
                    player
                ),

                "errors": player.errors,

                "max_errors": MAX_ERRORS,

                "guessed_letters": sorted(
                    player.guessed_letters
                ),
            },

            "opponent": None,

            "winner": None,
        }

        if opponent:

            estado["opponent"] = {
                "nickname": opponent.nickname,

                "word": self.masked_word(
                    opponent
                ),

                "errors": opponent.errors,

                "max_errors": MAX_ERRORS,

                "guessed_letters": sorted(
                    opponent.guessed_letters
                ),
            }

        if self.finished:

            if self.winner == session_id:
                estado["winner"] = "YOU"

            else:
                estado["winner"] = "OPPONENT"

        return estado

    # -----------------------------------------------------
    # SNAPSHOT
    #
    # Isso será usado depois para VM1 -> VM2
    # -----------------------------------------------------

    def snapshot(self):

        return {

            "room_id": self.room_id,

            # Somente servidor recebe isto
            "word": self.word,

            "turn_index": self.turn_index,

            "started": self.started,

            "finished": self.finished,

            "winner": self.winner,

            "version": self.version,

            "players": [
                {
                    "session_id":
                        player.session_id,

                    "nickname":
                        player.nickname,

                    "guessed_letters":
                        sorted(
                            player.guessed_letters
                        ),

                    "errors":
                        player.errors,
                }

                for player
                in self.players
            ]
        }

    # -----------------------------------------------------
    # RESTAURAR SNAPSHOT
    #
    # VM2 poderá reconstruir uma partida da VM1
    # -----------------------------------------------------

    @classmethod
    def from_snapshot(cls, data):

        game = cls(
            room_id=data["room_id"],
            word=data["word"]
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

                guessed_letters=set(
                    player_data[
                        "guessed_letters"
                    ]
                ),

                errors=
                    player_data[
                        "errors"
                    ]
            )

            game.players.append(player)

        return game