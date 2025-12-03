# Projeto Final SIC (Segurança Informática e nas Comunicações)

---

# **Planeamento de Atividades — Projeto SIC (Bluetooth IoT Ad-Hoc Network)**

**Duração recomendada:** 6–8 semanas
**Equipa:** 4 elementos
**Estrutura:** Sprints modulares + milestones importantes

---

# **Visão Geral dos Módulos**

1. **Bluetooth base + descoberta + ligações**
2. **Controlo de rede + interface CLI**
3. **Certificados + CA + autenticação + sessão**
4. **Encaminhamento + forwarding table + MACs**
5. **Heartbeat + deteção de falhas**
6. **Service Inbox + DTLS**
7. **Integração final + documentação**

---

# **Sprint 1 — Bluetooth básico (sem segurança)**

### **Objetivo**

Criar uma base funcional para ligações BLE e controlo manual.

### **Tarefas**

* Configurar ambiente Linux + simpleBLE em todos os nós.
* Desativar blueman/NetworkManager BT.
* Implementar:

  * Scan de dispositivos BLE próximos
  * Conexão/desconexão BLE entre dois nós
  * Troca básica de mensagens (sem segurança)
* Criar interface básica (CLI/TUI) mostrando:

  * NID (placeholder temporário)
  * Estado do uplink
  * Lista de downlinks

### **Entregáveis**

* Códigos `node/` e `sync/` com ligação BLE funcional.
* Script simples para testar envio/receção.

### **Critério de Aceitação**

> Dois nós conseguem conectar-se por BLE e trocar mensagens raw.

---

#  **Sprint 2 — Controlo de rede + topologia em árvore**

### **Objetivo**

Gerir ligações de uplink/downlink e lógica de árvore (sem segurança ainda).

### **Tarefas**

* Gerar temporariamente hop count local (manual).
* Implementar:

  * Descoberta de vizinhos + leitura do hop count deles.
  * Seleção de uplink com menor hop count.
  * Armazenamento de downlinks.
  * Queda do uplink → remover toda a subárvore.
  * Reconexão automática.
* Atualizar interface CLI:

  * hop atual
  * uplink NID
  * downlinks com NID

### **Entregáveis**

* Topologia automática tipo árvore com reconexão quando um nó falha.

### **Critério de Aceitação**

> A rede forma uma árvore, e quando um nó perde o uplink, todo o sub-nó reconecta.

---

#  **Sprint 3 — CA + Certificados + Identidades (common/ support/)**

### **Objetivo**

Implementar infraestrutura de identificação e autenticação.

### **Tarefas**

* Criar uma pequena CA local:

  * geração de chaves P-521
  * emissão de certificados X.509
  * certificado especial para o Sink
* Implementar:

  * Geração de NID = hash público (ou random 128-bit)
  * Armazenamento do certificado no device
  * Verificação mutua após conexão BLE

### **Entregáveis**

* `support/ca_tool.py` capaz de criar certificados.
* IoT nodes verificam certificados ao conectar.

### **Critério de Aceitação**

> Dois nós só estabelecem link BLE completo se ambos validarem os certificados da CA.

---

#  **Sprint 4 — Sessão segura + MAC + prevenção replay**

### **Objetivo**

Criar segurança ao nível da comunicação por saltos (hop-by-hop).

### **Tarefas**

* Implementar protocolo de autenticação:

  * Diffie-Hellman ECDH P-521
  * Derivação de chave simétrica (HKDF)
* Criar sessão com:

  * session key
  * contador TX local por ligação
* Criar MAC (HMAC-SHA256):

  * anexado a *todas* as mensagens hop-by-hop
  * cada ligação BLE tem sessão independente

### **Entregáveis**

* Mensagens têm MAC válido e rejeitam replay.
* Cada ligação tem uma sessão independente funcional.

### **Critério de Aceitação**

> Mensagens alteradas são rejeitadas e duplicados são detetados.

---

#  **Sprint 5 — Roteamento + forwarding tables**

### **Objetivo**

Criar full routing do tipo switch com armazenamento da origem.

### **Tarefas**

* Definir formato do header:

  ```
  [src NID | dst NID | service | client | counter | ... ]
  ```
* Encaminhamento uplink & downlink:

  * memorizar origem → tabela de forwarding
  * usar tabela para tráfego descendente
* Atualizar CLI:

  * forwarding table completa
  * contagem de mensagens encaminhadas

### **Entregáveis**

* Mensagens do Sink chegam ao IoT profundo e vice-versa.
* Atualização correta da forwarding table.

### **Critério de Aceitação**

> E envia msg → passa por B → chega ao Sink e devolve corretamente.

---

#  **Sprint 6 — Heartbeat + deteção automática de falhas**

### **Objetivo**

Adicionar liveness real e reorganização automática.

### **Tarefas**

* Sink envia heartbeat assinado com chave privada.
* Lógica de flooding downlink.
* IoT nodes:

  * validam assinatura
  * reenviam para downlinks
  * detetam perda após 3 heartbeats
  * quebram uplink
  * reconectam rede

### **Entregáveis**

* Rede reorganiza-se automaticamente quando uma ligação é cortada.
* CLI mostra:

  * número de heartbeats perdidos

### **Critério de Aceitação**

> Desligar um nó → subárvore perde 3 heartbeats → reconstrói rede sozinha.

---

#  **Sprint 7 — End-to-end DTLS + Inbox service**

### **Objetivo**

Implementar serviço final com segurança e ligação Sink ↔ IoT.

### **Tarefas**

* Adicionar endpoint DTLS:

  * certificação baseada nos mesmos certificados de link
  * criação de secure channel IoT ↔ Sink
* Criar serviço Inbox no Sink:

  * recebe msg + regista NID do autor
* Criar cliente Inbox no nó:

  * envio manual via CLI

### **Entregáveis**

* Comunicação segura da app no nó para o Sink.
* Sink imprime todas as mensagens recebidas.

### **Critério de Aceitação**

> Um nó envia msg → passa por multi-hop → DTLS protege ponta-a-ponta → Sink recebe.

---

#  **Sprint 8 — Integração final + testes + README**

### **Objetivo**

Unificar tudo, testar, corrigir e preparar entrega.

### **Tarefas**

* Criar testes:

  * rede em linha
  * rede em estrela
  * falha de nó intermediário
  * reconexão
  * repetição de mensagens (prevenção replay)
* Criar vídeo de demonstração (opcional)
* Criar `README.md` com:

  * arquitetura
  * decisões justificadas
  * partes incompletas
  * contribuição %
* Criar ZIP final com:

  * `/node`
  * `/sync`
  * `/common`
  * `/support`
---
