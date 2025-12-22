# **Bluetooth-based, secure ad-hoc network for IoT devices**
## Projeto Final Segurança Informática e nas Comunicações

### Módulos:
* Certs
* Common
* Node
* Support
* Sync

---
### 1. certs

> Ondem ficam os certificados gerados/obtidos.

---
### 2. **common**
> **nid.py**
> ---
> Define o identificador único de 128 bits (NID) para cada nó de rede. Permite criar NIDs aleatórios ou a partir de hex, essenciais para o endereçamento na rede mesh.
 
> **message.py**
> ---
>Implementa o formato de mensagens da rede: header(origem, destino, serviço, seq) + payload + MAC. Funções de serialização/deserialização para transmissão via Bluetooth.
 
> **bluetooth.py**
> ---
> Gestor principal Bluetooth RFCOMM. Suporta múltiplos adaptadores (hci0, hci1), permite scanning de dispositivos próximos, estabelecer conexões cliente/servidor, e enviar/receber dados em threads dedicadas.

> **routing.py**
> ---
> Tabela de encaminhamento que aprende rotas (NID → link_id + hop_count). Mantém sempre a rota com menor número de saltos e remove entradas quando links caem.

> **security.py**
> ---
>Gestão de segurança:
> * Validação de Certiificados X.509
> * Derivação de chaves simétricas via ECDH
> * MACs (HMAC-SHA256) para autenticação de mensagens por link
> * Assinatura/verificação de heartbeats (ECDSA)

> **dtls_channel.py**
> ---
> Chamada de segurança TLS-over-TCP (emula DTLS). Usado para handshakes seguros e troca inicial de certificados entre nó.

---
### 3. node

> **router.py**
> ---
> Núcleo do nó mesh. Gere:
> * **Uplink**: conexão ao nó mais próximo do Sink (menor hop_count)
> * **Roteamento**: aprende rotas via mensagens recebidas, encaminha para destino ou Sink.
> * **Heartbeats**: valida assinaturas do Sink, mantém uplink ativo, flooding para outros nós.
> * **Inbox**: recebe/envia mensagens, encaminha se não for destinatário.
> * **Timeouts**: deteta perda de uplink (sem heartbeats) e reconecta
> * **Scanning**: procura vizinhos e conecta ao que possui o melhor hop_count

> **ui.py**
> ---
> Interface para interação com o nó:
> * Visualizar status (NID, hop_count, uplink, estatísticas)
> * Scan de dispositivos Bluetooth próximos
> * Escolher dispositivo a conectar
> * Enviar mensagens de texto para o Sink
> * Ver inbox de mensagens recebidas

> **main_node.py**
>---
> Bootstrap do nó:
> * Carrega certificados (device, CA, Sink) baseados no NID
> * Inicializa Bluetooth Manager, SecurityContext e NodeRouter
> * Thread para heartbeat timeouts (verifica a cada 1s)
> * Lança UI interativa
> * Aceita NID via argumento CLI ou gera aleatório
---
### 4. support 

> **make_ca.sh**
> ---
> Cria a Autoridade Certificadora (CA) raiz com chave privada EC P-521 e certificado auto-assinado válido por 10 anos, guardado em certs/ca/

> **issue_device_cert.sh**
> ---
> Gera certificado individual para cada dispositivo (nó ou sink) identificado pelo NID hex. Cria chave privada EC P-521, CSR, e certificado assinado pela CA válido por 1 ano, guardado em /certs/<nid_hex>. Usado para autenticação mútua ECDH na rede mesh.
---
### 5. sync
> **router.py** (SinkRouter)
> ---
> Router central do Sink que aceita conexões Bluetooth dos nós, valida MACs de cada mensagem recebida, aprende rotas dinamicamente (NID→link_id), encaminha mensagens entre nós se necessário, e distribui heartbeats para toda a rede através de broadcast para todos os links ativos.

> **heartbeat.py** (HearbeatService)
> ---
> Serviço em thread separada que gera heartbeats assinados (ECDSA) a cada 5 segundos com contador incremental, permitindo aos nós validar autenticidade do Sink e manter sincronização da rede.

> **inbox.py** (InboxService)
> ---
> Serviço simples que recebe e armazena mensagens enviadas pelos nós para o Sink, decodifica payloads em texto e mantém lista com origem (NID), client_id e conteúdo.

> **main_sink.py**
> ---
> Bootstrap do Sink que carrega certificados (sink, CA), inicializa Bluetooth em modo servidor, cria router e serviços (inbox, heartbeat), e mantém execução contínua até interrupção manual.

---

## How to execute
1. Start in other pc or dongle sink:
```
 python3 -m sync.main_sink
```
2. Start the node:
```
python3 -m node.main_node
```
*Note: Gives an error, it generates the network id (nid)*

3. Issue node certificate:
```
bash issue_device_cert.sh
```
4. After getting the node id (nid). Do:
```
python3 -m node.main_node <nid>
```
5. After establish connections, the interface is intuitive.
