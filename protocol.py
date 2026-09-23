import json
import struct


MAX_MESSAGE_SIZE = 8192
HEADER_SIZE = 4


class ConnectionClosed(Exception):
    """A conexão foi encerrada pelo outro lado."""
    pass


class ProtocolError(Exception):
    """Mensagem inválida recebida."""
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
    """
    Envia um dicionário Python como JSON.

    Formato:
    [4 bytes tamanho][JSON]
    """

    if not isinstance(payload, dict):
        raise ProtocolError("Payload precisa ser um dicionário.")

    corpo = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":")
    ).encode("utf-8")

    if len(corpo) > MAX_MESSAGE_SIZE:
        raise ProtocolError("Mensagem grande demais.")

    cabecalho = struct.pack("!I", len(corpo))

    sock.sendall(cabecalho + corpo)


def recv_message(sock):
    """
    Recebe exatamente uma mensagem JSON.
    """

    cabecalho = _recv_exact(sock, HEADER_SIZE)

    tamanho = struct.unpack("!I", cabecalho)[0]

    if tamanho <= 0:
        raise ProtocolError("Tamanho de mensagem inválido.")

    if tamanho > MAX_MESSAGE_SIZE:
        raise ProtocolError(
            f"Mensagem excedeu o limite de {MAX_MESSAGE_SIZE} bytes."
        )

    corpo = _recv_exact(sock, tamanho)

    try:
        payload = json.loads(corpo.decode("utf-8"))

    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ProtocolError("JSON inválido.")

    if not isinstance(payload, dict):
        raise ProtocolError("Mensagem precisa ser um objeto JSON.")

    return payload