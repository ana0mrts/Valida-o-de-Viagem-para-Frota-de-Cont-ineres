# Validação de Viagem para Frota de Contêineres

## 1. O Problema Principal Resolvido
No transporte rodoviário de contêineres, as empresas enfrentam multas pesadas e retenções de cargas devido a quatro falhas críticas que muitas vezes são verificadas de forma manual ou isolada:
* **Irregularidade Fiscal:** Circular com MDF-e (Manifesto Eletrônico de Documentos Fiscais) cancelado, vencido ou com erro na chave de acesso.
* **Estouro de Jornada / Falta de Descanso:** Violar a "Lei do Motorista" (descanso mínimo obrigatório e limite diário de condução).
* **Telemetria e Retenções:** Veículos parados por tempo excessivo em congestionamentos não previstos.
* **Restrições de Trânsito Urbano e Janelas:** Caminhões pesados a entrarem em zonas urbanas fora dos horários permitidos ou a chegarem à fábrica fora da janela de recebimento.

**A Solução:** Automatiza todo este cruzamento de dados num único comando executado diretamente no terminal, decidindo de forma automática se a viagem é **LIBERADA** ou **BLOQUEADA**.

---

## 2. O que Cada Parte do Código Faz (Bloco a Bloco)

* **Configuração e Variáveis Globais:** Carrega as bibliotecas necessárias (`requests`, `datetime`), deteta chaves de ambiente para a Google Routes API e define os parâmetros regulatórios essenciais (`desc_min = 11 * 60`, `jorn_max = 10 * 60`, e restrições urbanas).
* **Validação Fiscal (MDF-e):** Valida a chave de acesso do documento fiscal de 44 dígitos através do algoritmo oficial de Módulo 11 (`calc_dv`) e checa o retorno da SEFAZ (`100` para autorizado, `101` para cancelado).
* **Controlo de Descanso e Jornada:** Faz o cálculo do histórico do motorista, confrontando o intervalo de descanso anterior com o mínimo exigido por lei[cite: 9].
* **Telemetria do Veículo:** Lê o fluxo de posições (velocidade e ignição) para detetar se o caminhão está retido há muito tempo por causa de trânsito ou paragens inesperadas[cite: 9].
* **Roteirização, Pedágios e Janelas:** Comunica com a Google Routes API para calcular tempo real de percurso e pedágios (com suporte a 5 eixos), validando também o horário previsto de chegada com as restrições da fábrica[cite: 9].

---

## 3. Testes Práticos no Terminal (Comandos de Simulação)

Para testar o comportamento do script com diferentes cenários operacionais, basta usar os seguintes comandos no terminal:

* **1. Cenário de Viagem Regular (Tudo Conforme):**
  ```powershell
  python viagem.py liberada
Resultado esperado: O sistema valida todas as etapas com sucesso e retorna VIAGEM LIBERADA

* **2. Testar Motorista sem Descanso Suficiente:**
  ```powershell
  python viagem.py sem_descanso
Resultado esperado: O script bloqueia logo na Etapa 2 porque o descanso está abaixo do mínimo legal.

* **3.Testar com MDF-e Cancelado na SEFAZ:**
  ```powershell
  python viagem.py mdfe_cancelado
Resultado esperado: O sistema barra a viagem na Etapa 1 devido à falta de autorização fiscal válida.

* **4.Testar Jornada Estourada:**
  ```powershell
  python viagem.py jornada_estourada
Resultado esperado: O script faz a projeção de tempo e bloqueia na Etapa 4 por excesso de horas acumuladas.
