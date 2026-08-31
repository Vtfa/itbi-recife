import os
import unicodedata
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado.csv")
CSV_OUTPUT = os.path.join(BASE_DIR, "data", "processed", "preco_m2_por_bairro.csv")
CSV_ANUAL_OUTPUT = os.path.join(BASE_DIR, "data", "processed", "preco_m2_por_bairro_e_ano.csv")

def normalize_text(text):
    if pd.isna(text): return 'DESCONHECIDO'
    nfkd = unicodedata.normalize('NFKD', str(text))
    clean = ''.join([c for c in nfkd if not unicodedata.combining(c)]).strip().upper()
    return clean.title()

def clean_val(v):
    if pd.isna(v): return None
    s = str(v).strip()
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except:
        return None

def main():
    print("Carregando base consolidada...")
    df = pd.read_csv(CSV_INPUT, sep=';', encoding='utf-8-sig', low_memory=False)
    
    df['valor_num'] = df['valor_avaliacao'].apply(clean_val)
    df['area_num'] = df['area_construida'].apply(clean_val)
    df['bairro_padronizado'] = df['bairro'].apply(normalize_text)
    
    # Filtro de registros válidos para cálculo de m2
    valid = df[(df['area_num'] >= 10) & (df['valor_num'] >= 10000)].copy()
    valid['preco_m2'] = valid['valor_num'] / valid['area_num']
    
    # Remoção de outliers extremos (percentis 1% e 99%)
    p_low = valid['preco_m2'].quantile(0.01)
    p_high = valid['preco_m2'].quantile(0.99)
    valid_filtered = valid[(valid['preco_m2'] >= p_low) & (valid['preco_m2'] <= p_high)].copy()
    
    print(f"Total de registros válidos: {len(valid_filtered):,}")
    
    # Agrupamento consolidado por bairro
    bairro_stats = valid_filtered.groupby('bairro_padronizado').agg(
        total_transacoes=('preco_m2', 'count'),
        preco_m2_medio=('preco_m2', 'mean'),
        preco_m2_mediana=('preco_m2', 'median'),
        preco_m2_desvio_padrao=('preco_m2', 'std'),
        preco_m2_min=('preco_m2', 'min'),
        preco_m2_max=('preco_m2', 'max'),
        area_media_m2=('area_num', 'mean'),
        valor_medio=('valor_num', 'mean')
    ).reset_index()
    
    # Normalização Min-Max (escala 0 a 100)
    min_m2 = bairro_stats['preco_m2_medio'].min()
    max_m2 = bairro_stats['preco_m2_medio'].max()
    bairro_stats['indice_normalizado_0_100'] = ((bairro_stats['preco_m2_medio'] - min_m2) / (max_m2 - min_m2)) * 100
    
    # Normalização Z-Score
    mean_m2 = bairro_stats['preco_m2_medio'].mean()
    std_m2 = bairro_stats['preco_m2_medio'].std()
    bairro_stats['z_score_m2'] = (bairro_stats['preco_m2_medio'] - mean_m2) / std_m2
    
    # Ordenar por maior preço médio por m²
    bairro_stats = bairro_stats.sort_values(by='preco_m2_medio', ascending=False).reset_index(drop=True)
    bairro_stats['ranking'] = range(1, len(bairro_stats) + 1)
    
    # Reordenar colunas
    col_order = ['ranking', 'bairro_padronizado', 'total_transacoes', 'preco_m2_medio', 'preco_m2_mediana', 
                 'indice_normalizado_0_100', 'z_score_m2', 'preco_m2_desvio_padrao', 'area_media_m2', 'valor_medio']
    bairro_stats = bairro_stats[col_order]
    
    # Arredondamentos
    for c in ['preco_m2_medio', 'preco_m2_mediana', 'indice_normalizado_0_100', 'z_score_m2', 'preco_m2_desvio_padrao', 'area_media_m2', 'valor_medio']:
        bairro_stats[c] = bairro_stats[c].round(2)
        
    bairro_stats.to_csv(CSV_OUTPUT, index=False, sep=';', encoding='utf-8-sig')
    print(f"Arquivo consolidado por bairro salvo em: {CSV_OUTPUT}")
    
    # Agrupamento anual por bairro
    anual_stats = valid_filtered.groupby(['bairro_padronizado', 'ano_arquivo']).agg(
        total_transacoes=('preco_m2', 'count'),
        preco_m2_medio=('preco_m2', 'mean'),
        preco_m2_mediana=('preco_m2', 'median')
    ).reset_index()
    
    anual_stats['preco_m2_medio'] = anual_stats['preco_m2_medio'].round(2)
    anual_stats['preco_m2_mediana'] = anual_stats['preco_m2_mediana'].round(2)
    anual_stats.to_csv(CSV_ANUAL_OUTPUT, index=False, sep=';', encoding='utf-8-sig')
    print(f"Arquivo anual por bairro salvo em: {CSV_ANUAL_OUTPUT}")
    
    print("\n" + "="*80)
    print("RANKING: TOP 20 BAIRROS COM MAIOR PREÇO MÉDIO / M² EM RECIFE")
    print("="*80)
    print(bairro_stats.head(20)[['ranking', 'bairro_padronizado', 'total_transacoes', 'preco_m2_medio', 'preco_m2_mediana', 'indice_normalizado_0_100']].to_string(index=False))

if __name__ == "__main__":
    main()
