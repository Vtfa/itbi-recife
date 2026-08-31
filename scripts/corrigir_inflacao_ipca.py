import os
import json
import urllib.request
import unicodedata
import pandas as pd
import numpy as np
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CONSOLIDATED = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado.csv")
INFLATION_CONSOLIDATED = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
BAIRRO_OUTPUT = os.path.join(BASE_DIR, "data", "processed", "preco_m2_corrigido_por_bairro.csv")
ANUAL_OUTPUT = os.path.join(BASE_DIR, "data", "processed", "preco_m2_corrigido_por_bairro_e_ano.csv")

def get_ipca_series():
    """Busca a série histórica do IPCA mensal (código 433) no Banco Central do Brasil."""
    print("Buscando série histórica do IPCA na API do Banco Central do Brasil (SGS 433)...")
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    
    df_ipca = pd.DataFrame(data)
    df_ipca['data'] = pd.to_datetime(df_ipca['data'], format='%d/%m/%Y')
    df_ipca['valor'] = pd.to_numeric(df_ipca['valor'], errors='coerce') / 100.0
    df_ipca['ano_mes'] = df_ipca['data'].dt.strftime('%Y-%m')
    df_ipca = df_ipca.sort_values('data').reset_index(drop=True)
    
    # Calcular índice acumulado (número-índice)
    # index_t = prod(1 + ipca)
    df_ipca['indice_acumulado'] = (1.0 + df_ipca['valor']).cumprod()
    
    # O fator de correção para a data-base mais recente (último mês disponível):
    ultimo_indice = df_ipca['indice_acumulado'].iloc[-1]
    df_ipca['fator_correcao'] = ultimo_indice / df_ipca['indice_acumulado']
    
    ultima_data_str = df_ipca['ano_mes'].iloc[-1]
    print(f"Série IPCA carregada. Data-base mais recente: {ultima_data_str} (Índice base: {ultimo_indice:.4f})")
    
    fator_map = dict(zip(df_ipca['ano_mes'], df_ipca['fator_correcao']))
    return fator_map, ultima_data_str

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
    fator_map, data_base = get_ipca_series()
    
    print(f"Lendo base consolidada ({RAW_CONSOLIDATED})...")
    df = pd.read_csv(RAW_CONSOLIDATED, sep=';', encoding='utf-8-sig', low_memory=False)
    
    df['valor_num'] = df['valor_avaliacao'].apply(clean_val)
    df['area_num'] = df['area_construida'].apply(clean_val)
    df['bairro_padronizado'] = df['bairro'].apply(normalize_text)
    
    # Extrair ano-mes da data de transacao
    df['ano_mes_transacao'] = df['data_transacao'].astype(str).str.slice(0, 7)
    
    # Atribuir fator de correção
    # Caso alguma data seja futura ou não mapeada, fallback para 1.0 ou fator mais próximo
    df['fator_ipca'] = df['ano_mes_transacao'].map(fator_map).fillna(1.0)
    
    # Calcular valores corrigidos pela inflação
    df['valor_avaliacao_corrigido'] = (df['valor_num'] * df['fator_ipca']).round(2)
    df['preco_m2_nominal'] = (df['valor_num'] / df['area_num']).round(2)
    df['preco_m2_corrigido'] = (df['valor_avaliacao_corrigido'] / df['area_num']).round(2)
    
    print(f"Salvando dataset com valores corrigidos em: {INFLATION_CONSOLIDATED}...")
    df.to_csv(INFLATION_CONSOLIDATED, index=False, sep=';', encoding='utf-8-sig')
    
    # Filtrar registros válidos para estatísticas de m2 (remover outliers de 1% a 99%)
    valid = df[(df['area_num'] >= 10) & (df['valor_avaliacao_corrigido'] >= 10000)].copy()
    p_low = valid['preco_m2_corrigido'].quantile(0.01)
    p_high = valid['preco_m2_corrigido'].quantile(0.99)
    valid_filtered = valid[(valid['preco_m2_corrigido'] >= p_low) & (valid['preco_m2_corrigido'] <= p_high)].copy()
    
    print(f"Total de registros válidos para cálculo: {len(valid_filtered):,}")
    
    # Estatísticas consolidadas por bairro com valor corrigido
    bairro_stats = valid_filtered.groupby('bairro_padronizado').agg(
        total_transacoes=('preco_m2_corrigido', 'count'),
        preco_m2_medio_corrigido=('preco_m2_corrigido', 'mean'),
        preco_m2_mediana_corrigida=('preco_m2_corrigido', 'median'),
        preco_m2_medio_nominal=('preco_m2_nominal', 'mean'),
        preco_m2_desvio_padrao=('preco_m2_corrigido', 'std'),
        area_media_m2=('area_num', 'mean'),
        valor_medio_corrigido=('valor_avaliacao_corrigido', 'mean')
    ).reset_index()
    
    # Normalização Min-Max (0 - 100)
    min_m2 = bairro_stats['preco_m2_medio_corrigido'].min()
    max_m2 = bairro_stats['preco_m2_medio_corrigido'].max()
    bairro_stats['indice_normalizado_0_100'] = ((bairro_stats['preco_m2_medio_corrigido'] - min_m2) / (max_m2 - min_m2)) * 100
    
    # Normalização Z-score
    mean_m2 = bairro_stats['preco_m2_medio_corrigido'].mean()
    std_m2 = bairro_stats['preco_m2_medio_corrigido'].std()
    bairro_stats['z_score'] = (bairro_stats['preco_m2_medio_corrigido'] - mean_m2) / std_m2
    
    # Ranking
    bairro_stats = bairro_stats.sort_values('preco_m2_medio_corrigido', ascending=False).reset_index(drop=True)
    bairro_stats['ranking'] = range(1, len(bairro_stats) + 1)
    
    col_order = [
        'ranking', 'bairro_padronizado', 'total_transacoes',
        'preco_m2_medio_corrigido', 'preco_m2_mediana_corrigida', 'preco_m2_medio_nominal',
        'indice_normalizado_0_100', 'z_score', 'preco_m2_desvio_padrao', 'area_media_m2', 'valor_medio_corrigido'
    ]
    bairro_stats = bairro_stats[col_order]
    
    for c in ['preco_m2_medio_corrigido', 'preco_m2_mediana_corrigida', 'preco_m2_medio_nominal', 'indice_normalizado_0_100', 'z_score', 'preco_m2_desvio_padrao', 'area_media_m2', 'valor_medio_corrigido']:
        bairro_stats[c] = bairro_stats[c].round(2)
        
    bairro_stats.to_csv(BAIRRO_OUTPUT, index=False, sep=';', encoding='utf-8-sig')
    print(f"Tabela de preços corrigidos por bairro salva em: {BAIRRO_OUTPUT}")
    
    # Estatísticas anuais por bairro com valores corrigidos
    anual_stats = valid_filtered.groupby(['bairro_padronizado', 'ano_arquivo']).agg(
        total_transacoes=('preco_m2_corrigido', 'count'),
        preco_m2_medio_corrigido=('preco_m2_corrigido', 'mean'),
        preco_m2_mediana_corrigida=('preco_m2_corrigido', 'median'),
        preco_m2_medio_nominal=('preco_m2_nominal', 'mean')
    ).reset_index()
    
    for c in ['preco_m2_medio_corrigido', 'preco_m2_mediana_corrigida', 'preco_m2_medio_nominal']:
        anual_stats[c] = anual_stats[c].round(2)
        
    anual_stats.to_csv(ANUAL_OUTPUT, index=False, sep=';', encoding='utf-8-sig')
    print(f"Série anual corrigida salva em: {ANUAL_OUTPUT}")
    
    print("\n" + "="*95)
    print("RANKING REAL (CORRIGIDO PELO IPCA): TOP 25 BAIRROS COM MAIOR PREÇO MÉDIO / M² EM RECIFE")
    print("="*95)
    print(bairro_stats.head(25)[['ranking', 'bairro_padronizado', 'total_transacoes', 'preco_m2_medio_corrigido', 'preco_m2_mediana_corrigida', 'preco_m2_medio_nominal', 'indice_normalizado_0_100']].to_string(index=False))

    print("\n" + "="*95)
    print("POSIÇÃO DE DOIS UNIDOS APÓS A CORREÇÃO DE INFLAÇÃO:")
    print("="*95)
    print(bairro_stats[bairro_stats['bairro_padronizado'] == 'Dois Unidos'][['ranking', 'bairro_padronizado', 'total_transacoes', 'preco_m2_medio_corrigido', 'preco_m2_mediana_corrigida', 'indice_normalizado_0_100']].to_string(index=False))

if __name__ == "__main__":
    main()
