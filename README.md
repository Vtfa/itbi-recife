# ITBI Recife (2015 – 2026)

Painel analítico e base de dados processada para consulta e análise das transações imobiliárias registradas no ITBI pela Prefeitura do Recife.

---

## Execução

Para iniciar o servidor local:

```bash
python scripts/app_servidor.py
```

Ou no Windows:
- Executar `iniciar_dashboard.bat` (ou `python iniciar_dashboard.py`).

O painel estará disponível em `http://localhost:8050`.

---

## Pipeline de Processamento de Dados

Para reprocessar a base completa a partir dos dados oficiais e reconstruir `itbi_recife.db` (e `itbi_recife.db.gz`):

```bash
python scripts/process_itbi.py               # 1. Baixa e consolida os CSVs anuais da Prefeitura
python scripts/corrigir_area_e_inflacao.py   # 2. Aplica correção IPCA (BCB) e estima área privativa
python scripts/padronizar_logradouros.py     # 3. Unifica logradouros por cod_logradouro e número
python scripts/processar_revendas.py         # 4. Identifica histórico de revendas por unidade
python scripts/recuperar_coordenadas_itbi.py # 5. Recupera coordenadas faltantes e gera o SQLite
```

Para apenas reconstruir o banco SQLite a partir de `data/processed/itbi_consolidado_corrigido.csv`:

```bash
python scripts/criar_banco_sqlite.py
```

---

## Funcionalidades

- **Visualização Geoespacial:** Mapa interativo com delimitação dos bairros (GeoJSON) e localização dos edifícios.
- **Busca por Endereço:** Autocomplete por logradouro, condomínio e bairro.
- **Histórico por Unidade:** Detalhamento de transações com valor nominal, valor corrigido pelo IPCA e preço por m² privativo estimado.
- **Identificação de Revendas:** Rastreamento de imóveis com mais de uma venda registrada ao longo do período analisado.
- **Séries Temporais:** Gráficos de evolução histórica de preços por edifício e bairro.
- **Exportação:** Exportação dos dados filtrados para CSV.

---

## Estrutura do Repositório

```text
├── dashboard_interativo.html        # Interface web (Leaflet, Tailwind, Chart.js)
├── iniciar_dashboard.py             # Script de inicialização local
├── data/
│   ├── raw/
│   │   ├── itbi_2015.csv ...        # Dados brutos anuais
│   │   └── bairros_recife.geojson   # Malha vetorial dos bairros
│   └── processed/
│       ├── itbi_recife.db           # Banco SQLite indexado
│       └── itbi_consolidado_corrigido.csv
└── scripts/
    ├── app_servidor.py              # Servidor HTTP e API REST
    ├── criar_banco_sqlite.py        # Importação e indexação SQLite
    ├── corrigir_area_e_inflacao.py  # Correção pelo IPCA e cálculo de m²
    ├── padronizar_logradouros.py    # Padronização de nomes de vias
    └── processar_revendas.py        # Identificação de revendas
```
