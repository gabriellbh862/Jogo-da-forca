---
status: accepted
---

# Descoberta automática de Servidor via socket, não via API HTTP

O objetivo era simplificar como um Jogador encontra um Servidor na mesma rede, sem digitar IP manualmente. A alternativa óbvia hoje em dia seria expor o jogo como uma API HTTP/REST ou WebSocket. Optamos por manter toda a comunicação em **socket TCP puro** e resolver a descoberta com broadcast/multicast na própria rede local (biblioteca externa liberada, ex. `zeroconf`), porque o enunciado da atividade exige explicitamente "utilize socket para comunicação" — migrar para HTTP descumpriria esse requisito. O Anfitrião (quem hospeda) passa a poder subir o mesmo motor de servidor embutido no cliente gráfico, mas `server.py` standalone continua existindo para rodar headless numa VM, mantendo o requisito de servidor resiliente em VM.
