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
