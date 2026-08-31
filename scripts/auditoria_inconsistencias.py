import sqlite3
import pandas as pd
import numpy as np

conn = sqlite3.connect(r'C:\Users\PC1\Documents\ITBI_Recife\data\processed\itbi_recife.db')
cursor = conn.cursor()

print("="*80)
print("AUDITORIA DE CONSISTÊNCIA DE DADOS - ITBI RECIFE (151.848 REGISTROS)")
print("="*80)

# 1. Edifícios com coordenadas nulas
query_coords_null = """
SELECT endereco_edificio, bairro_padronizado, cod_logradouro, total_transacoes, m2_privativo_medio, valor_medio_corrigido
FROM edifcios_resumo
WHERE latitude IS NULL OR longitude IS NULL
ORDER BY total_transacoes DESC
"""
df_null_coords = pd.read_sql_query(query_coords_null, conn)
print(f"\n1. EDIFÍCIOS SEM COORDENADAS GPS: {len(df_null_coords):,} edifícios sem coordenadas.")
print(f"   Total de transações afetadas: {df_null_coords['total_transacoes'].sum():,} ({df_null_coords['total_transacoes'].sum()/151848*100:.2f}%)")
print("\nTop 15 edifícios/endereços com mais transações sem coordenadas:")
print(df_null_coords.head(15).to_string())

# 2. Verificar se conseguimos recuperar coordenadas pelo cod_logradouro (mesma rua)
query_ruas_coords = """
SELECT DISTINCT cod_logradouro, AVG(latitude) as lat_media, AVG(longitude) as lng_media
FROM transacoes
WHERE latitude IS NOT NULL AND longitude IS NOT NULL
GROUP BY cod_logradouro
"""
df_ruas_coords = pd.read_sql_query(query_ruas_coords, conn)
cods_com_coord = set(df_ruas_coords['cod_logradouro'])
recuperaveis = df_null_coords[df_null_coords['cod_logradouro'].isin(cods_com_coord)]
print(f"\n   -> Desses {len(df_null_coords)} endereços sem coordenadas, {len(recuperaveis)} ({recuperaveis['total_transacoes'].sum():,} transações) têm coordenadas conhecidas na mesma rua (cod_logradouro) e podem ser georreferenciados com alta precisão!")

# 3. Inconsistências de Valores Extremos ou Zerados
query_valores = """
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN valor_num <= 0 THEN 1 ELSE 0 END) as valor_zero,
    SUM(CASE WHEN valor_num > 50000000 THEN 1 ELSE 0 END) as valor_hiper_alto,
    SUM(CASE WHEN area_total_cadastral <= 0 THEN 1 ELSE 0 END) as area_zero,
    SUM(CASE WHEN preco_m2_privativo_corrigido < 300 THEN 1 ELSE 0 END) as m2_suspeito_baixo,
    SUM(CASE WHEN preco_m2_privativo_corrigido > 50000 THEN 1 ELSE 0 END) as m2_suspeito_alto
FROM transacoes
"""
df_valores = pd.read_sql_query(query_valores, conn)
print("\n2. ANÁLISE DE VALORES VENAL E ÁREAS ANÔMALAS:")
print(df_valores.to_string())

# 4. Inconsistências de Bairros Desconhecidos ou Não Padronizados
query_bairros = """
SELECT bairro_padronizado, COUNT(*) as qtd
FROM transacoes
WHERE bairro_padronizado IS NULL OR bairro_padronizado = '' OR bairro_padronizado = 'Desconhecido'
"""
df_bairros = pd.read_sql_query(query_bairros, conn)
print("\n3. BAIRROS DESCONHECIDOS OU VAZIOS:")
print(df_bairros.to_string())

# 5. Inconsistências de Datas
query_datas = """
SELECT 
    MIN(data_transacao) as data_min,
    MAX(data_transacao) as data_max,
    SUM(CASE WHEN data_transacao IS NULL OR LENGTH(data_transacao) != 10 THEN 1 ELSE 0 END) as datas_invalidas
FROM transacoes
"""
df_datas = pd.read_sql_query(query_datas, conn)
print("\n4. INTEGRIDADE DAS DATAS DE TRANSAÇÃO:")
print(df_datas.to_string())
