# VideoLabeler Pro — Documentação de Arquitetura e Guia de Referência

Este documento centraliza todas as informações úteis sobre o repositório `Grafica` e, em especial, a arquitetura, estruturas de dados, algoritmos e fluxos de funcionamento do aplicativo **`video_labeler_pro`**.

---

## 1. Contexto Geral do Repositório (`Grafica`)

O repositório reúne ferramentas de análise gráfica/imagens e anotação temporal de vídeos:

- **Scripts iniciais de análise de imagens (pólen com DBSCAN/HSL):**
  - `run.py`, `run2.py`, `cores.py`, `teste.ipynb`: filtragem de cores (RGB/HSL) e clusterização espacial via DBSCAN para contagem de grãos de pólen em imagens `.tif`/`.jpg`.
- **Evolução das ferramentas de anotação de vídeo (Pygame + OpenCV):**
  - `VideoLabeler.py`: anotador single-video categorizado (exportação em CSV por timestamp).
  - `ViewVideoLabel.py`: visualizador sincronizado de múltiplos arquivos CSV de rótulos sobre um vídeo.
  - `VideoLabelerHierarchical.py`: ferramenta single-video (`VideoSplitter`) para divisão hierárquica de episódios em árvore binária, exportando a hierarquia em JSON (`number_steps`, `first_layer_starts`, `above_layers_groups`).
  - **`video_labeler_pro/`**: versão profissional multi-trilha (NLE + anotador Categorizado e Hierárquico), permitindo sincronizar múltiplos vídeos, dividir/arrastar clipes, anotar episódios hierarquicamente, exportar vídeos sincronizados e carregar/comparar até duas anotações hierárquicas simultâneas com clusterização incremental (`fcluster`).

---

## 2. Estrutura Modular do `video_labeler_pro`

O aplicativo é executado a partir de `video_labeler_pro/main.py` e está dividido nos seguintes módulos:

| Arquivo | Responsabilidade Principal |
| :--- | :--- |
| `main.py` | Ponto de entrada (`VideoLabelerApp().run()`). |
| `app.py` | Loop principal Pygame (`VideoLabelerApp`), gerenciamento de eventos (mouse, teclado, redimensionamento), barra de controles, caixa de entrada de número de episódios (`fcluster`) e sincronização com threads de diálogo/exportação. |
| `models.py` | Modelos de dados: `Node` (árvore binária de cortes), `HierarchicalLabelTrack` (estrutura de rótulo hierárquico carregado), função `fcluster` (agrupamento incremental por delta) e `AnnotationModel` (estado das anotações categorizadas e hierárquicas). |
| `video_engine.py` | `VideoClip` (decodificação OpenCV otimizada para seek sequencial/aleatório e corte de clipes) e `MultiVideoEngine` (gerenciamento de múltiplas trilhas de vídeo e visibilidade de até 2 trilhas simultâneas no viewport). |
| `timeline_widget.py` | `MultiTrackTimeline`: renderização da linha do tempo com zoom e rolagem horizontal, exibindo 1 ou 2 trilhas de anotação hierárquica no topo seguidas pelas trilhas de vídeo e agulha (playhead). |
| `viewport_manager.py` | `ViewportManager`: renderização de 1 vídeo centralizado ou 2 vídeos lado a lado (split-screen) conforme as trilhas ativas ("olho" ligado). |
| `ui_components.py` | `MenuBar` (barra superior com `"Abrir Vídeos"`, `"Abrir Labels"`, `"Salvar Projeto"`, `"Carregar Projeto"`, `"Exportar"` e seletor de modo `"Categorizado"` / `"Hierárquico"`) e `LabelPanel` (painel lateral para o modo categorizado). |
| `file_utils.py` | `FileDialogHelper`: abertura de diálogos nativos do sistema operacional (`zenity` no Linux, `PowerShell/WinForms` no Windows, `osascript` no macOS) em threads separadas para não travar a janela Pygame. |
| `export_utils.py` | `export_project_data`: exporta o JSON de anotações (`hierarchical_labels.json` ou `categorical_labels.json`) e renderiza os vídeos recortados/sincronizados (`*_syncronized.mp4`) alinhados frame a frame com a timeline global. |
| `modals.py` | `ConfirmationModal`: modal sobreposto para exibição de mensagens de confirmação ou erro. |

---

## 3. Formato de Dados Hierárquico (`hierarchical_labels.json`)

As anotações hierárquicas seguem um formato JSON padronizado de **aglutinação hierárquica reversa (bottom-up)** gerado a partir das divisões top-down:

```json
{
    "number_steps": 5756,
    "first_layer_starts": [0, 99, 169, 255, ...],
    "above_layers_groups": [
        [
            [60, 61],
            [56, 57],
            [63, 62],
            ...
        ]
    ]
}
```

### Como funciona a representação:
1. **`number_steps`**: total de frames da timeline anotada ($T$).
2. **`first_layer_starts`**: lista ordenada com o frame inicial de cada um dos $N$ episódios folha (camada mais granular).
   - O episódio folha de ID $i \in \{0, \dots, N-1\}$ compreende o intervalo $[s_i, s_{i+1})$, sendo $s_N = \text{number\_steps}$.
3. **`above_layers_groups`**: lista de camadas contendo a sequência de fusões `[id_esq, id_dir]`.
   - Na criação manual de cortes (`cuts_history`), o usuário divide segmentos de cima para baixo (top-down), formando uma árvore binária (`build_tree()`).
   - Na exportação (`to_hierarchical_export_dict()`), as folhas recebem IDs $0 \dots N-1$ em ordem cronológica, e as divisões são percorridas **em ordem reversa** (`reversed(history_records)`): cada fusão na posição $m \in \{0, \dots, M-1\}$ une dois grupos ativos `[id_esq, id_dir]` e cria um novo grupo pai com ID $N + m$.

---

## 4. Carregamento de Labels Hierárquicas e `fcluster` Incremental (por Delta)

### 4.1. Botão `"Abrir Labels"` e Modo Não Editável
- O botão **`"Abrir Labels"`** na barra superior permite selecionar **1 ou 2 arquivos JSON** de rótulos hierárquicos:
  - O usuário pode selecionar 2 arquivos de uma só vez no diálogo de arquivos, ou abrir 1 arquivo e clicar novamente em `"Abrir Labels"` para adicionar a segunda label distinta.
- Quando há labels carregadas e o aplicativo está no modo **`Hierárquico`**:
  - Os rótulos carregados tornam-se **não editáveis (somente leitura)**: os botões `"Cortar (C)"` e `"Desfazer (Ctrl+Z)"` (bem como os respectivos atalhos de teclado) ficam bloqueados para edição de cortes.
  - A timeline exibe 1 ou 2 faixas de anotação (`Label 1` e `Label 2`) com paletas de cores distintas para comparação direta sobre os vídeos sincronizados.
  - O botão **`"Limpar Labels"`** na barra de controles permite descarregar as labels externas e retomar a edição manual a qualquer momento.

### 4.2. Seleção do Número de Episódios e Eficiência por Delta (`fcluster`)
Na barra de controles do modo hierárquico há a caixa de escrita **`Episódios:`** acompanhada do botão **`Aplicar`** (também acionável com `Enter` ou com as setas `↑` / `↓` quando a caixa está focada).

Ao informar um número alvo de episódios $K$, a função `fcluster(label_track, target_num_episodes)` em `models.py` é executada em cada `HierarchicalLabelTrack`:

1. **Estado Mantido (`HierarchicalLabelTrack`):**
   - `current_step`: índice da próxima fusão em `merges` (inicialmente $0$, correspondendo aos $N$ episódios de `first_layer_starts`).
   - `active_nodes`: dicionário `group_id -> (start, end)` contendo exatamente os episódios ativos no recorte atual.
   - `node_intervals`: cache de intervalos `(start, end)` de todos os nós folhas e nós pais já calculados.
   - `cached_segments`: lista ordenada de tuplas `(start, end)` mantida via `bisect` (`insort_left` / `bisect_left`).

2. **Atualização Exclusiva do Delta ($\Delta$):**
   - **Se $K == |\text{active\_nodes}|$ ($\Delta = 0$):** retorna imediatamente `cached_segments` em $O(1)$.
   - **Se $K < |\text{active\_nodes}|$ (menos episódios $\Rightarrow$ avançar fusões):**
     Continua a partir de `current_step`, juntando os pares em `merges[current_step]` um a um até que $|\text{active\_nodes}| == K$ **e para imediatamente**, sem processar o restante da árvore.
   - **Se $K > |\text{active\_nodes}|$ (mais episódios $\Rightarrow$ desfazer fusões):**
     Retrocede a partir de `current_step`, desfazendo apenas as $\Delta = K - |\text{active\_nodes}|$ fusões necessárias (removendo `parent_id` e restaurando seus filhos a partir de `node_intervals`) até atingir $K$ episódios **e para**.

Dessa forma, transitar de um recorte de $K_1$ episódios para $K_2$ episódios nunca recalcula a árvore desde o início, executando estritamente $|\Delta| = |K_1 - K_2|$ operações.

---

## 5. Controles e Atalhos Rápidos

- **Ferramentas de Timeline:**
  - **I-Beam (Agulha):** posiciona e arrasta o playhead pela linha do tempo.
  - **Seta (Mover):** seleciona e arrasta clipes de vídeo horizontalmente para sincronização.
  - **Tesoura (Corte de Vídeo):** divide um clipe de vídeo no frame clicado.
- **Atalhos de Teclado:**
  - `Espaço`: Play / Pause.
  - `Seta Esquerda` / `Seta Direita`: rolagem horizontal da timeline (quando a caixa de texto não está focada).
  - `Scroll do Mouse` (sobre a timeline): Zoom In / Zoom Out (`Shift + Scroll` rola horizontalmente).
  - `C`: adiciona corte de episódio no frame atual (apenas no modo Hierárquico editável, desabilitado quando há labels carregadas).
  - `Ctrl + Z`: desfaz última edição de clipe ou último corte hierárquico manual.
  - `Delete` / `Backspace`: remove o clipe de vídeo selecionado.
  - Na caixa **`Episódios`**: digite o número desejado e pressione `Enter` (ou clique em `Aplicar`), ou use as setas `↑` / `↓` para incrementar/decrementar em tempo real via delta.

