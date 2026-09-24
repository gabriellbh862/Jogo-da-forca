# 🎮 Jogo da Forca Distribuído

Projeto de jogo da forca multiplayer utilizando **Python, sockets TCP, threads e interface gráfica com Tkinter**.

O objetivo do projeto é permitir partidas entre dois jogadores, com o servidor controlando toda a lógica do jogo e, na versão final, utilizando **duas VMs com redundância e failover**.

## Funcionalidades

A versão atual possui:

- Interface gráfica com Tkinter
- Dois jogadores por partida
- Criação automática de salas
- Turnos controlados pelo servidor
- Palavra compartilhada entre os jogadores
- Uma forca individual para cada jogador
- Chute de letras
- Chute da palavra inteira
- Errou o chute da palavra inteira → perde imediatamente
- Palavra secreta armazenada somente no servidor
- Validação das jogadas no servidor
- Controle de concorrência com `threading.Lock`
- Reconexão de jogador
- 40 segundos para reconectar
- Vitória por W.O. se o jogador não retornar
- Token de sessão
- Estrutura preparada para replicação entre VM1 e VM2

---

# 📁 Estrutura do projeto

```text
Jogo-da-forca/
│
├── client.py
├── server.py
├── game.py
├── protocol.py
├── discovery.py
├── tests/
├── docs/adr/
├── CONTEXT.md
├── README.md
└── .gitignore
```

### `client.py`

Responsável por:

- interface gráfica;
- descoberta e seleção do servidor na rede (sem digitar IP);
- hospedar uma partida embutida ("Anfitrião");
- conexão com o servidor;
- envio das jogadas;
- exibição da palavra;
- exibição das forcas;
- reconexão do jogador (buscando o servidor salvo na rede).

### `server.py`

Responsável por:

- aceitar conexões;
- criar salas;
- controlar sessões;
- validar jogadas;
- controlar turnos;
- detectar desconexões;
- aplicar W.O.;
- enviar o estado atualizado aos jogadores;
- anunciar sua presença na rede local (via `discovery.py`).

### `game.py`

Contém as regras do jogo da forca.

### `protocol.py`

Implementa o protocolo de comunicação TCP usando JSON.

### `discovery.py`

Descoberta automática de Servidores na rede local via broadcast UDP: `ServerAnnouncer` (lado do Servidor) e `ServerBrowser` (lado do Cliente). Veja [`CONTEXT.md`](CONTEXT.md) e [`docs/adr/0001-descoberta-via-socket-em-vez-de-api-http.md`](docs/adr/0001-descoberta-via-socket-em-vez-de-api-http.md).

---

# ✅ Requisitos

É necessário ter:

```text
Python 3.10+
```

O projeto utiliza apenas bibliotecas padrão do Python.

Não é necessário instalar bibliotecas externas para rodar o jogo localmente.

Para verificar sua versão:

```powershell
python --version
```

ou:

```bash
python3 --version
```

---

# 🚀 Como rodar localmente

## 1. Clonar o projeto

```bash
git clone https://github.com/gabriellbh862/Jogo-da-forca.git
```

Entre na pasta:

```bash
cd Jogo-da-forca
```

---

# 🧪 Verificar os arquivos

Antes de executar, é possível verificar a sintaxe:

```bash
python -m py_compile protocol.py game.py discovery.py server.py client.py
```

No Linux/macOS, dependendo da instalação:

```bash
python3 -m py_compile protocol.py game.py discovery.py server.py client.py
```

Se nenhum erro aparecer, os arquivos passaram na verificação de sintaxe.

---

# 🖥️ Iniciar o servidor local

Abra um terminal dentro da pasta do projeto:

```powershell
python server.py --name VM1
```

O esperado é algo semelhante a:

```text
[20:30:00] [VM1] [SERVER] Servidor iniciado em 0.0.0.0:5000
[20:30:00] [VM1] [SERVER] Aguardando jogadores...
```

Não feche esse terminal.

O servidor utiliza por padrão:

```text
Host: 0.0.0.0
Porta: 5000
```

---

# 🎮 Abrir o primeiro jogador

Abra outro terminal na mesma pasta.

No teste normal:

```powershell
python client.py
```

A interface gráfica será aberta e, em instantes, o Servidor iniciado no passo anterior aparece sozinho na lista **"Servidores encontrados na rede"** — não é preciso digitar IP.

Selecione o Servidor na lista, digite seu nome e clique em:

```text
ENTRAR EM NOVA PARTIDA
```

O primeiro jogador ficará aguardando o segundo jogador.

---

# 🖥️ Alternativa: hospedar pelo próprio cliente ("Anfitrião")

Em vez de rodar `server.py` num terminal separado, qualquer cliente pode hospedar uma partida diretamente pela interface gráfica:

```powershell
python client.py
```

Na tela inicial, clique em:

```text
HOSPEDAR PARTIDA
```

Essa janela vira o Servidor daquela partida (mesma lógica de `server.py`) e fica visível para os outros clientes na lista de descoberta — mas **não joga**: quem hospeda só administra a partida. Para jogar, abra outro cliente na rede e clique em "Entrar" normalmente.

---

# 👥 Testar dois jogadores no mesmo computador

Como os clientes utilizam um arquivo local para guardar a sessão, é recomendado usar perfis diferentes durante os testes no mesmo PC.

No PowerShell, abra um terminal para o Jogador 1:

```powershell
$env:FORCA_PROFILE="jogador1"
python client.py
```

Abra outro terminal para o Jogador 2:

```powershell
$env:FORCA_PROFILE="jogador2"
python client.py
```

> Caso a versão atual do `client.py` ainda não utilize `FORCA_PROFILE`, os dois clientes ainda conseguem jogar normalmente, porém o teste de reconexão pode compartilhar o mesmo arquivo de sessão. Para testes completos no mesmo computador, utilize arquivos de sessão separados por perfil.

Os dois jogadores entrarão automaticamente na mesma sala:

```text
SALA-001
```

Depois disso a partida começa.

---

# 🎯 Regras do jogo

Cada partida possui uma palavra secreta escolhida pelo servidor.

Exemplo:

```text
_ _ _ _ _ _ _ _
```

Um jogador escolhe uma letra:

```text
E
```

Se a letra existir:

```text
_ E _ _ _ _ E _
```

A letra aparece para os dois jogadores.

Se estiver errada, somente a forca do jogador que errou recebe uma nova parte.

---

# 🔄 Turnos

O servidor controla os turnos.

Exemplo:

```text
Jogador 1
   ↓
Jogador 2
   ↓
Jogador 1
   ↓
Jogador 2
```

Mesmo que um cliente seja modificado para tentar jogar fora da vez, o servidor rejeita a jogada.

---

# 💀 Erros

Cada jogador possui sua própria forca.

O limite atual é:

```text
6 erros
```

A sequência é:

```text
1 - Cabeça
2 - Corpo
3 - Braço esquerdo
4 - Braço direito
5 - Perna esquerda
6 - Perna direita
```

Ao chegar ao sexto erro, o adversário vence.

---

# 📝 Chutar a palavra inteira

Além de escolher letras, o jogador pode tentar descobrir a palavra completa.

Exemplo:

```text
COMPUTADOR
```

Se acertar:

```text
VITÓRIA
```

Se errar:

```text
DERROTA IMEDIATA
```

Essa ação só pode ser feita durante o turno do jogador.

---

# 🔌 Testar desconexão

Durante uma partida, feche a janela de um dos jogadores.

O outro jogador deverá receber algo semelhante a:

```text
ADVERSÁRIO DESCONECTADO
```

A partida fica pausada.

O jogador possui:

```text
40 segundos
```

para retornar.

---

# 🔁 Testar reconexão

Se estiver utilizando perfis diferentes no mesmo computador, abra novamente o jogador com o mesmo perfil.

Exemplo:

```powershell
$env:FORCA_PROFILE="jogador1"
python client.py
```

A tela deverá encontrar a sessão anterior.

Clique em:

```text
RECONECTAR À PARTIDA
```

A partida deve continuar mantendo:

- mesma sala;
- mesma palavra;
- mesmas letras;
- mesmos erros;
- mesmo estado da partida.

---

# 🏳️ Vitória por W.O.

Feche um dos jogadores durante uma partida e não reconecte.

Após aproximadamente:

```text
40 segundos
```

o jogador conectado deverá receber:

```text
VITÓRIA POR W.O.
```

---

# 🧪 Teste básico recomendado

Antes de trabalhar com as VMs, teste:

```text
[ ] Servidor inicia
[ ] Jogador 1 conecta
[ ] Jogador 2 conecta
[ ] Os dois entram na mesma sala
[ ] Letras corretas aparecem para os dois
[ ] Erros são individuais
[ ] Turnos alternam
[ ] Chute correto da palavra vence
[ ] Chute incorreto da palavra perde
[ ] Desconectar pausa a partida
[ ] Reconectar em menos de 40s funciona
[ ] Não reconectar gera W.O.
```

---

# 🌐 Jogar entre computadores na mesma rede

Não é mais preciso descobrir ou digitar o IP do Servidor: basta que os computadores estejam na mesma rede local (mesmo Wi-Fi/LAN).

Um computador roda o Servidor (`python server.py --name VM1`, ou o botão "HOSPEDAR PARTIDA" pelo cliente). Nos demais computadores, ao abrir `python client.py`, esse Servidor aparece sozinho na lista **"Servidores encontrados na rede"** dentro de alguns segundos — é só selecioná-lo e entrar.

Isso funciona por uma descoberta automática via broadcast UDP na rede local (veja [`docs/adr/0001-descoberta-via-socket-em-vez-de-api-http.md`](docs/adr/0001-descoberta-via-socket-em-vez-de-api-http.md)).

O firewall do computador que hospeda o Servidor precisa permitir:

```text
TCP na porta 5000   (comunicação do jogo)
UDP na porta 55201  (descoberta automática na rede)
```

---

# 🖧 Arquitetura planejada com duas VMs

A versão final utilizará:

```text
                  CLIENTES
                     |
                     |
              +------+------+
              |             |
             VM1 <--------> VM2
           PRINCIPAL       BACKUP
```

A VM1 será inicialmente o servidor ativo.

A VM2 manterá uma cópia do estado.

Se a VM1 cair:

```text
VM1 ❌
 |
 +----> VM2 assume
```

Os clientes deverão reconectar automaticamente à VM2 e continuar a partida.

---

# 🔐 Segurança do jogo

O cliente nunca recebe a palavra secreta durante a partida.

O cliente envia apenas ações:

```json
{
  "type": "GUESS",
  "letter": "A"
}
```

ou:

```json
{
  "type": "GUESS_WORD",
  "word": "COMPUTADOR"
}
```

O servidor decide:

- se a jogada é válida;
- se é a vez do jogador;
- se a letra está correta;
- se a palavra está correta;
- quem venceu;
- quantos erros cada jogador possui.

Isso evita que um cliente modificado simplesmente declare que venceu.

---

# 🧹 Arquivos que não devem ir para o Git

O `.gitignore` deve conter:

```gitignore
.forca_session*.json
__pycache__/
*.pyc
```

Os arquivos `.forca_session*.json` são gerados durante a execução e armazenam tokens temporários de sessão.

Eles não são necessários para instalar ou executar o projeto em outro computador.

---

# 🛠️ Comandos rápidos

Servidor:

```powershell
python server.py --name VM1
```

Cliente:

```powershell
python client.py
```

Dois clientes no mesmo PC para testes:

```powershell
$env:FORCA_PROFILE="jogador1"
python client.py
```

```powershell
$env:FORCA_PROFILE="jogador2"
python client.py
```

Verificar sintaxe:

```powershell
python -m py_compile protocol.py game.py discovery.py server.py client.py
```

Rodar os testes automatizados (descoberta, hospedagem embutida e reconexão):

```powershell
python -m unittest discover -s tests
```

---

# 📌 Estado do projeto

## Implementado

- [x] Jogo da forca
- [x] Interface gráfica
- [x] Cliente/servidor TCP
- [x] Multiplayer
- [x] Salas
- [x] Turnos
- [x] Concorrência
- [x] Chute de letras
- [x] Chute da palavra
- [x] Reconexão de jogador
- [x] W.O.
- [x] Descoberta automática de servidores na rede (sem IP fixo)
- [x] Hospedar partida embutido no cliente (Anfitrião)
- [x] Reconexão buscando o servidor salvo pela rede

## Próximas etapas

- [ ] Replicação VM1 → VM2
- [ ] Heartbeat
- [ ] Failover automático
- [ ] Reconexão automática ao servidor backup
- [ ] Configuração em duas VMs
- [ ] Geração do executável Windows
- [ ] Testes finais de apresentação
