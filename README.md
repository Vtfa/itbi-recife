# Workspace: ITBI Recife Analytics (2015 - 2026)

Workspace completo e avançado para consulta, análise e visualização das **151.848 transações imobiliárias** do ITBI da Prefeitura do Recife.

---

## 🚀 Como Iniciar o Painel Interativo

Basta dar um duplo clique em:
- **`iniciar_dashboard.bat`** (ou executar `python iniciar_dashboard.py`)

Isso abrirá automaticamente no seu navegador o **Explorador Interativo de Transações** (`http://localhost:8050`).

---

## 🌟 Recursos do Painel

1. **Mapa Interativo com Polígonos de Bairros (GeoJSON):**
   - Visualize os 93 bairros e os 16.484 edifícios do Recife.
   - Marcadores coloridos por faixa de preço de m² privativo.
2. **Busca Inteligente por Endereço ou Edifício:**
   - Digite qualquer rua, avenida ou condomínio (ex: *Le Parc, Boa Viagem, Agamenon, Conselheiro Aguiar*).
3. **Histórico Detalhado Transação por Transação:**
   - Ao selecionar qualquer prédio, o painel lista **cada apartamento/sala vendido**:
     - **Unidade / Complemento** (ex: *Apto 1402 Edf Maria Julia*)
     - **Data da Transação** (de 2015 a 2026)
     - **Valor Corrigido pelo IPCA** vs. **Valor Nominal** da época
     - **Metragem Privativa Estimada** ($m^2$) vs. **Área Total Cadastral**
     - **Preço por $m^2$ Privativo Real**
     - **Padrão de Acabamento** e **Conservação**
4. **Gráfico de Evolução Temporal:**
   - Gráfico de linha mostrando a trajetória do preço/m² das unidades vendidas naquele edifício ao longo dos anos.
5. **Exportação de Dados:**
   - Botão para exportar o histórico daquele edifício diretamente para CSV / Excel.

---

## 📁 Estrutura de Arquivos

```text
ITBI_Recife/
├── iniciar_dashboard.bat          # Atalho para iniciar com 2 cliques
├── iniciar_dashboard.py           # Script iniciador
├── dashboard_interativo.html      # Interface web do painel
├── data/
│   ├── raw/
│   │   ├── itbi_2015.csv ... 2026.csv   # 12 CSVs originais
│   │   └── bairros_recife.geojson       # Polígonos oficiais dos bairros
│   └── processed/
│       ├── itbi_recife.db               # Banco SQLite indexado
│       ├── itbi_consolidado_corrigido.csv # Base com 151.848 transações
│       ├── imoveis_por_endereco_detalhado.csv # Todas as transações com endereços
│       ├── resumo_por_edificio_logradouro.csv # Resumo por condomínio
│       └── preco_m2_privativo_por_bairro.csv  # Ranking por bairro
└── scripts/
    ├── app_servidor.py            # Servidor HTTP / API REST
    ├── criar_banco_sqlite.py      # Importador SQLite
    ├── corrigir_area_e_inflacao.py# Correção IPCA + Área Privativa
    └── process_itbi.py            # Downloader inicial
```
