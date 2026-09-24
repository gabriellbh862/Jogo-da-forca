import json
import struct


MAX_MESSAGE_SIZE = 8192
HEADER_SIZE = 4


class ConnectionClosed(Exception):
    pass


class ProtocolError(Exception):
    pass


def _recv_exact(sock, quantidade):
    dados = bytearray()

    while len(dados) < quantidade:
        parte = sock.recv(quantidade - len(dados))

        if not parte:
            raise ConnectionClosed("Conexão encerrada.")

        dados.extend(parte)

    return bytes(dados)


def send_message(sock, payload):
    if not isinstance(payload, dict):
        raise ProtocolError(
            "Payload precisa ser um dicionário."
        )

    corpo = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":")
    ).encode("utf-8")

    if len(corpo) > MAX_MESSAGE_SIZE:
        raise ProtocolError(
            "Mensagem grande demais."
        )

    cabecalho = struct.pack(
        "!I",
        len(corpo)
    )

    sock.sendall(
        cabecalho + corpo
    )


def recv_message(sock):
    cabecalho = _recv_exact(
        sock,
        HEADER_SIZE
    )

    tamanho = struct.unpack(
        "!I",
        cabecalho
    )[0]

    if tamanho <= 0:
        raise ProtocolError(
            "Tamanho de mensagem inválido."
        )

    if tamanho > MAX_MESSAGE_SIZE:
        raise ProtocolError(
            "Mensagem excedeu o limite permitido."
        )

    corpo = _recv_exact(
        sock,
        tamanho
    )

    try:
        payload = json.loads(
            corpo.decode("utf-8")
        )

    except (
        json.JSONDecodeError,
        UnicodeDecodeError
    ):
        raise ProtocolError(
            "JSON inválido."
        )

    if not isinstance(payload, dict):
        raise ProtocolError(
            "Mensagem precisa ser um objeto JSON."
        )

    return payload