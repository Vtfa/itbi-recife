import os
import sqlite3
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_CONSOLIDADO = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
RELATORIO_CSV = os.path.join(BASE_DIR, "data", "processed", "imoveis_recuperados_georreferenciados.csv")
RELATORIO_BAIRRO_CSV = os.path.join(BASE_DIR, "data", "processed", "resumo_imoveis_recuperados_por_bairro.csv")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "itbi_recife.db")

# Load raw files to check which ones had latitude == NULL originally
raw_dir = os.path.join(BASE_DIR, "data", "raw")
raw_files = [os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if f.startswith("itbi_") and f.endswith(".csv")]

raw_dfs = []
for f in raw_files:
    d = pd.read_csv(f, sep=';', encoding='utf-8', dtype=str, on_bad_lines='skip')
    raw_dfs.append(d[['logradouro', 'numero', 'complemento', 'bairro', 'latitude', 'longitude']])

df_raw_all = pd.concat(raw_dfs, ignore_index=True)
print(f"Total registros brutos: {len(df_raw_all):,}")
print(f"Total registros originalmente sem latitude no dado bruto: {df_raw_all['latitude'].isna().sum():,}")

# Identificar os endereços afetados no dataset consolidado atual
df_cons = pd.read_csv(CSV_CONSOLIDADO, sep=';', encoding='utf-8-sig', low_memory=False)

# Marcar se o registro era originalmente sem coordenadas
# Na base bruta, latitude vazia:
df_cons['era_sem_coordenada_original'] = df_raw_all['latitude'].isna().values

print(f"Total marcado como sem coordenada original: {df_cons['era_sem_coordenada_original'].sum():,}")

# Salvar relatório detalhado por edifício recuperado
df_recup = df_cons[df_cons['era_sem_coordenada_original']].copy()

relatorio_edificios = df_recup.groupby(['bairro_padronizado', 'endereco_edificio', 'logradouro_canonico']).agg(
    total_transacoes=('valor_avaliacao_corrigido', 'count'),
    total_revendas=('total_vendas_imovel', lambda s: (s > 1).sum()),
    m2_privativo_medio=('preco_m2_privativo_corrigido', 'mean'),
    valor_medio_corrigido=('valor_avaliacao_corrigido', 'mean'),
    area_privativa_media=('area_privativa_estimada', 'mean'),
    latitude=('latitude', 'first'),
    longitude=('longitude', 'first')
).reset_index()

for c in ['m2_privativo_medio', 'valor_medio_corrigido', 'area_privativa_media']:
    relatorio_edificios[c] = relatorio_edificios[c].round(2)
    
relatorio_edificios = relatorio_edificios.sort_values(by=['bairro_padronizado', 'total_transacoes'], ascending=[True, False]).reset_index(drop=True)
relatorio_edificios.to_csv(RELATORIO_CSV, index=False, sep=';', encoding='utf-8-sig')
print(f"Relatório detalhado de {len(relatorio_edificios):,} edifícios recuperados salvo em: {RELATORIO_CSV}")

# Resumo agregado por bairro
resumo_bairro = relatorio_edificios.groupby('bairro_padronizado').agg(
    edificios_recuperados=('endereco_edificio', 'count'),
    transacoes_recuperadas=('total_transacoes', 'sum'),
    m2_privativo_medio_bairro=('m2_privativo_medio', 'mean'),
    valor_medio_imovel=('valor_medio_corrigido', 'mean')
).reset_index().sort_values(by='transacoes_recuperadas', ascending=False).reset_index(drop=True)

resumo_bairro['ranking'] = range(1, len(resumo_bairro) + 1)
resumo_bairro['m2_privativo_medio_bairro'] = resumo_bairro['m2_privativo_medio_bairro'].round(2)
resumo_bairro['valor_medio_imovel'] = resumo_bairro['valor_medio_imovel'].round(2)

resumo_bairro = resumo_bairro[['ranking', 'bairro_padronizado', 'edificios_recuperados', 'transacoes_recuperadas', 'm2_privativo_medio_bairro', 'valor_medio_imovel']]
resumo_bairro.to_csv(RELATORIO_BAIRRO_CSV, index=False, sep=';', encoding='utf-8-sig')
print(f"Resumo por bairro salvo em: {RELATORIO_BAIRRO_CSV}")

print("\n" + "="*95)
print("TOP 25 BAIRROS COM MAIS IMÓVEIS/TRANSAÇÕES QUE ESTAVAM OCULTOS NO MAPA E FORAM RECUPERADOS:")
print("="*95)
print(resumo_bairro.head(25).to_string(index=False))
