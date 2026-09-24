# Jogo da Forca Distribuído

Jogo da forca multiplayer em que um servidor central controla o estado de todas as partidas, e clientes gráficos se conectam a ele via socket TCP na mesma rede local.

## Language

**Servidor**:
Processo que mantém o estado do jogo (palavra secreta, salas, turnos) e valida todas as jogadas. Não participa como jogador.
_Avoid_: Host (em português, usar Anfitrião para o papel humano; Servidor é o processo)

**Anfitrião**:
Papel assumido por quem inicia um Servidor a partir do cliente gráfico (botão "Hospedar"), tornando-o descobrível pelos outros clientes na rede. O Anfitrião não joga — apenas hospeda o Servidor.
_Avoid_: Host

**Jogador**:
Participante de uma Partida que se conecta a um Servidor já existente para jogar. Cada Partida tem no máximo 2 Jogadores.
_Avoid_: Cliente (Cliente é o processo/app; Jogador é a pessoa participando da partida)

**Sala**:
Agrupamento de até 2 Jogadores mantido pelo Servidor, com sua própria palavra secreta, turnos e forcas. Um Servidor pode manter várias Salas simultaneamente.

**Partida**:
Uma rodada completa do jogo da forca disputada dentro de uma Sala, do início até vitória, derrota ou W.O.

**Descoberta automática**:
Mecanismo pelo qual um cliente encontra os Servidores ativos na rede local, exibindo-os para escolha, sem que o IP precise ser digitado manualmente.
