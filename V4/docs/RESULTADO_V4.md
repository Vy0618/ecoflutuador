# Resultado da consolidação controlada V4

## Entrega e limites

Auditoria integral realizada antes de mudanças de código; baseline preservado; consolidação incremental sobre os caminhos existentes. **Nenhum arquivo movido/excluído, nenhum modelo trocado, nenhum motor acionado, nenhum serviço instalado ou processo do Raspberry desativado.** Legados continuam no lugar, claramente identificados no README da raiz. Fontes originais preservadas também em [original-sources.tar.gz](audit/original-sources.tar.gz), sem credenciais de rede, modelos ou build; snapshot integral temporário em /tmp/eco-v4-original.tar.gz. Modelos/binários originais intactos, hashes no manifesto.

Esta entrega não é uma liberação para navegação física: compilação alvo ESP32, câmera/UART/sensores e comportamento elétrico dos ESCs ainda precisam ser validados. Servidor/dashboard **local** funciona; transporte remoto/cache persistente possuem plano objetivo, não implementação.

## Evidências e testes

| Verificação | Antes | Depois |
|---|---|---|
| Python do sistema sem deps | 2 erros de coleta por cv2 ausente | Ambiente isolado em /tmp; sistema não alterado |
| Suíte completa | 58 passados,0 falhas,0 skips | **88 passados,0 falhas,0 skips**; 58 originais preservados |
| C++ nativo | Header de sensores passou com g++ | Sensores + lease/wrap/heartbeat/framing longo passaram no mesmo teste nativo |
| Mock determinístico | a/w/d/s observados na decisão, sem envio real ao mock | a/w/d/s transmitidos ao MockSerial e STOP no shutdown |
| Mock CLI | 3 s,29 frames, shutdown correto | 45 s,449 frames,9,9 FPS incluindo cleanup; WAITING/CONFIRMING/TRACKING/retorno; sem hardware |
| Importação | 9 módulos V4 importáveis com dependências | Módulos novos/imports/sintaxe verificados; decisão/contratos importam até no Python sem OpenCV/PySerial |
| Modelo real | `Const input blob for weights not found` | Erro preservado, pesos intactos; nenhum fallback silencioso |
| Dry-run | Picamera2 ausente | USB configurada; câmera0 indisponível no host, falha explícita; sem UART |
| HTTP | Endpoints test_client; socket inicialmente bloqueado pelo sandbox | `/`,health,status,telemetry,history,diagnostics HTTP200 em127.0.0.1; shutdown/STOP verificados |
| systemd | Unidade legada aponta ao servidor de vídeo | Unidade V4 de referência passa `systemd-analyze verify`; não instalada |
| ESP32 compile | Arduino CLI ausente | Nova tentativa mesma falha de ambiente; **compilação alvo não validada** |

Evidências: [baseline](audit/baseline-tests.txt), [suíte final](audit/final-tests.txt), [mock](audit/final-mock.txt), [tentativa firmware](audit/final-firmware.txt), [dependências exatas](audit/environment.txt), [integração HTTP](audit/final-http.txt) e [exemplo completo de telemetria](audit/telemetry-example.json). Saídas ERROR nos testes de falha são estímulos esperados e não falhas da suíte. Não houve warnings de compilação C++ nativa; dry-run emite warnings OpenCV por câmera ausente. Os warnings do teste real DNN são a incompatibilidade existente, não foram ocultados.

Foram corrigidas também falhas intermediárias: CameraConfig ainda não recebia index durante primeira integração; um teste novo usava imagem40px e esperava zona de320px, corrigido para a geometria pretendida. Nenhum teste anterior foi apagado ou relaxado.

Limitações de ambiente: Ubuntu x86_64, sem Raspberry conectado. systemctl bus restrito; não foi possível inventariar serviços do Pi. Navegador de inspeção indisponível; endpoints/template verificados, renderização visual interativa pendente. Socket e lock de câmera inicialmente restritos pelo sandbox foram reexecutados com autorização. Não há Git utilizável nesta cópia.

## Justificativa das alterações

| Arquivo/grupo | Mudança e razão |
|---|---|
| ControleESP32.ino | Lease1,5 s, HB só renova movimento válido, STOP imediato, HC inválido para, trabalho UART/GPS limitado, versão de protocolo/firmware; elimina execução indefinida do último comando enquanto loop responde |
| sensors_v4.h / sensors_v4_test.cpp | ControlLease/CommandFramer independentes de hardware e asserções de expiração, wrap, mismatch e descarte de sufixo; testa a lógica realmente usada no sketch |
| core/contracts.py | Resultado/interface sem dependência de OpenCV; conversão xywh→xyxy explícita |
| core/detector.py | Mantém SSD e erro original; devolve classes sem decidir navegação; Detection reexportada para compatibilidade |
| core/decision.py | Targets/fauna/threshold configuráveis, prioridade segura, validação de resultados e frame_id, preservando zonas e testes antigos |
| core/state.py | Janela máxima independente da presença de detecções |
| core/serial_link.py | Sessão de reconexão, HB, validação adicional de TEL ambiental/GPS/uptime; comandos originais preservados |
| main.py | Orquestra adapters/config; exclusão de mock em produção; mensagens com idade de recebimento; reconexão/firmware antigo/HC inválido em FAULT; erro/latência/câmera seguros; mock realmente envia; API opcional não controla navegação; logs por mudança |
| core/camera.py | Índice configurável sem procura em múltiplas câmeras; lock cooperativo; ID/idade; limita captura/retry/logs; reduz cópias |
| core/config.py / config.yaml | USB320×240/10FPS oficial; paths relativos ao YAML; validação/env; política/janela/lease explícitos; remove configurações inoperantes de performance |
| core/logging_config.py | JSON escapado e rotação limitada; sem imagens |
| core/telemetry.py | Schema local enxuto, histórico limitado/por mudança, CPU/RSS/temperatura sob demanda |
| api/status_server.py / templates/dashboard.html | Reaproveita Flask existente; somente dados, histórico, health/diagnóstico; sem servidor de navegação nem vídeo |
| core/diagnostics.py | camera-test/uart-test/sensor-test com duração limitada e sem comandos de movimento |
| core/__init__.py | Exportações lazy eliminam importação de OpenCV quando só decisão/contratos são necessários |
| mock/detector_mock.py | Adapter sintético explícito separado do Pipeline |
| mock/camera_mock.py | Movimento sintético correto na tela; elimina linhas de zona que cortavam detecções |
| mock/serial_mock.py / run_mock.py | Filas limitadas, polling menos intenso, transmissão de comandos validada, STOP e logging uniforme |
| tests/test_consolidation.py | 30 regressões novas de segurança/config/observabilidade; sem hardware |
| configs/ecoflutuador-v4.service | Serviço correto, reinício limitado, conflito com legado, sem dependência da rede; referência somente |
| poc_raspberry/requirements-dev.txt | Explicita OpenCV headless/NumPy já exigidos pelo mock, sem acrescentar runtime de GUI |
| tools/benchmark_mock.py / verify_api.py | Medições reproduzíveis sem hardware e integração HTTP com cleanup |
| README.md / poc_raspberry/README.md / SENSORES_V4.md | Orientação vigente e correção de documentação contraditória; originais arquivados |
| ESTRUTURA_V4.md / TESTE_V4_HCSR04.md | Aviso no topo de que são relatórios históricos |
| docs/* | Inventário antes/depois, alterações, baseline, operação, riscos, roadmap e evidências |

Lista exata gerada por comparação SHA256: [changes.json](audit/changes.json). Arquivos legacy de execução, pinagem, pesos, perfil de rede e binários antigos não alterados. Os artefatos build/firmware são anteriores; **não fazer upload como se fossem resultado desta consolidação**.

## CPU, RAM, câmera e logs

Benchmark controlado sem API, sem rede e sem hardware, mesma resolução320×240/10FPS, duração5 s, mesmo Python/dependências no mesmo host; original extraído do snapshot. Inclui startup NumPy/OpenCV, threads e shutdown. Uma amostra por cenário: não é estimativa estatística nem benchmark de modelo.

| Cenário | CPU antes (% de1 núcleo) | CPU depois (amostra inicial consolidada) | Pico RSS antes/depois KiB | Linhas log antes/depois |
|---|---:|---:|---:|---:|
| WAITING |36,83|31,45|73344 /73836|58 /12|
| START/reconhecimento/retorno |34,24|29,00|75272 /75588|58 /28|

WAITING bytes stdout+stderr caíram de10087 para2227 (~78%). Ativo de10861 para7369 (~32%), mesmo acrescentando eventos/commands antes ausentes. RAM próxima de72–74MiB, sem redução relevante; não alegar economia de RAM. Variações curtas de CPU podem ser startup/agendamento. Captura real, energia, latência de USB/CSI e CPU/temperatura do Raspberry não foram medidas. DNN incompatível impede benchmark de inferência real.

O Pi deve ser medido em WAITING e reconhecimento por pelo menos60 s em320×240 e640×480, com mesmo backend/modelo validado. Registrar processoCPU/RSS/temperatura, FPS de captura/consumo, p50/p95/p99 de inferência, idade de frame e latência START→STOP/comando. Comparar antes de ativar FPS adaptativo. Arquivos performance-*.json e ferramenta permitem repetir. Logs de produção não contêm frames; memória de histórico limitada100 registros; nenhuma inferência ocorre em WAITING.

## Melhorias avaliadas — benefício, custo, prioridade e momento

P0: segurança antes de operação física; P1: próxima consolidação; P2: após medições/bancada; P3: somente com necessidade demonstrada.

| # | Melhoria | Benefício | Custo/complexidade | Prioridade / decisão |
|---|---|---|---|---|
|1|Watchdog ESP32|Recupera travamento do firmware além do lease|Média: API depende do core, boot/PWM precisam ensaio|P0 antes de operação; lease agora, watchdog tarefa depois da compilação alvo |
|2|Watchdog processo Pi|Reinicia processo travado|Média: sd_notify/liveness real, não thread que mascara travamento|P1 depois; Restart=on-failure agora não detecta hang |
|3|Heartbeat Pi↔ESP|Expira controle sem duplicar movimento|Baixa/média: extensão UART testada|P0 implementado HB+lease |
|4|Buffer offline|Preserva eventos sem rede|Média: disco, retenção/replay/backoff|P1 plano remoto; histórico RAM agora não é spool |
|5|Health endpoint|Liveness observável|Baixa|P1 preservado; separar readiness física |
|6|CPU/RAM/temperatura|Mede consumo real|Baixa, amostra lenta|P1 implementado diagnóstico; validar Pi |
|7|Câmera desconectada|Impede continuar com imagem antiga|Baixa/média|P0 timeout/idade/STOP implementados; USB real pendente |
|8|Sensor inválido|Evita decisão sobre dado falso|Média|P0 HC implementado; P1 diagnóstico ADC/GPS físico |
|9|Versão firmware|Identifica compatibilidade/control lease|Baixa|P1 implementada TEL4.1.0 |
|10|Versão modelo|Rastreia resultados|Baixa|P1 campo configurável, null até modelo real |
|11|Versão UART|Impede uso silencioso de firmware sem proteção|Baixa|P0 protocolo1.1 aditivo e verificação em config oficial |
|12|Config ambiente|Portabilidade e instalação reproduzível|Baixa|P1 overrides/validação implementados |
|13|Rotação logs|Limita disco|Baixa|P1 opcional2MB×4; journal rate-limit |
|14|systemd V4|Entrypoint correto e um único processo|Baixa|P1 exemplo verificado; instalação física pendente |
|15|Restart controlado|Evita crash loop consumindo Pi|Baixa|P1 unidade10 s/3 tentativas em120 s |
|16|Graceful shutdown|STOP e libera recursos|Baixa|P0 implementado/testado; validar serial física |
|17|Testes latência|Valida orçamento de segurança|Média|P0 regressão slow inference; P1 percentis no Pi/modelo real |
|18|FPS adaptativo|Reduz calor/CPU quando carga alta|Média: estabilidade temporal|P2 depois de medir; FPS fixo configurável agora |
|19|Resolução menor|Reduz cópia/captura/inferência|Baixa; afeta recall|P1 USB320×240, input320 configuráveis; precisão real pendente |
|20|Debounce/filtro|Evita START espúrio|Média: experimento acústico|P0 lógica preservada/testada; threshold15/10 não validado fisicamente |
|21|Fauna prioritária|Evita perseguir animais|Baixa na política, alta na validação do modelo|P0 política configurável/STOP imediato implementada |
|22|Persistência mínima|Histórico após reboot|Média: limites de disco e schema|P1 depois no servidor/SQLite; RAM100 agora |
|23|Schema eventos|Facilita consumo/deduplicação|Baixa/média|P1 snapshot/log JSON agora; envelope remoto boot_id+seq depois |
|24|Idempotência comandos|Evita repetir atuação sem necessidade|Baixa|P0 comandos setpoint+supressão+HB implementados; reconexão força STOP |
|25|ACK/sequência|Detecta perda/reordenação|Média: coordenação nas duas pontas|P1 ACK existente parseado; sequência/retry depois de medir erros UART; não alegar entrega garantida |
|26|Telemetria stale|Não usa conexão/dados expirados como atuais|Baixa|P0 timeout, timestamp de recepção e descarte de fila velha implementados |
|27|Dashboard leve|Diagnóstico sem vídeo|Baixa|P1 local implementado, polling5 s, sem dependências JS externas |
|28|Diagnóstico endpoint|Ajuda bancada|Baixa|P1 implementado; restringir rede de acesso |
|29|Manutenção|Testa sensores/UART sem navegar|Baixa/média|P1 modos limitados implementados; documentação motores desconectados |
|30|Simulador completo|Regride pipeline sem hardware|Média|P1 câmera/detector/serial/START/decisão/API/STOP implementados; ambiente físico, GPS NMEA e dinâmica não simulados |

## Pendências concretas antes de navegar

1. Instalar toolchain Arduino ESP32/ESP32Servo/TinyGPSPlus em ambiente de build, executar helper **sem --enable-motors**, registrar core/versões/log/binário novo. Não usar os bins antigos. Implementar e testar watchdog alvo conforme core escolhido.
2. Na bancada sem motores, validar UART1.1, perda do Pi, queda UART, HB atrasado/diferente, restart, lixo serial/linhas longas e stopPWM no instrumento. Validar timeout real e STOP1000 µs nos ESCs usados.
3. Validar USB, desconexão, ownership único e FPS real no Pi. CSI não bloqueia a bancada USB.
4. Calibrar HC-SR04 experimentalmente sobre água; pH com soluções reais; ST100 com referências reais. Coeficientes antigos não são validação. Integrar DS18B20 só após definir pinagem/montagem. Testar NMEA e GPS ausente/fix vencido.
5. Receber modelo customizado e adapter, mapear labels/coords/thresholds, avaliar fauna e lixo em conflito. Preservar erro do MobileNet legado. Medir latência/precisão antes de qualquer controle físico.
6. Identificar unidades/processos reais no Pi e desativar somente legado confirmado. Instalar unidade V4 apenas após config/modelo/firmware validados. Esta tarefa não tinha acesso ao Pi e não desativou nada nele.
7. Implementar transporte remoto/cache conforme plano em OPERACAO_V4.md quando houver destino e requisitos de retenção. Configuração de URL sozinha não envia nada.

Entregáveis de árvore/arquitetura/legado/baseline estão na auditoria; protocolos/estado/decisão/interface/schema/modos/serviços/comandos no guia de operação; alterações/testes/desempenho/riscos/roadmap neste relatório. Esses três documentos são a referência atual e substituem instruções operacionais contraditórias dos textos históricos.
