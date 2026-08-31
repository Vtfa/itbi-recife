import os
import json
import urllib.request
import unicodedata
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CONSOLIDATED = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado.csv")
OUTPUT_CONSOLIDATED = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
OUTPUT_BAIRRO_PRIVATIVO = os.path.join(BASE_DIR, "data", "processed", "preco_m2_privativo_por_bairro.csv")
OUTPUT_ANUAL_PRIVATIVO = os.path.join(BASE_DIR, "data", "processed", "preco_m2_privativo_por_bairro_e_ano.csv")

def get_ipca_series():
    """Busca a série histórica do IPCA mensal (SGS 433) no Banco Central."""
    print("Buscando série do IPCA no Banco Central do Brasil...")
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    
    df_ipca = pd.DataFrame(data)
    df_ipca['data'] = pd.to_datetime(df_ipca['data'], format='%d/%m/%Y')
    df_ipca['valor'] = pd.to_numeric(df_ipca['valor'], errors='coerce') / 100.0
    df_ipca['ano_mes'] = df_ipca['data'].dt.strftime('%Y-%m')
    df_ipca = df_ipca.sort_values('data').reset_index(drop=True)
    
    df_ipca['indice_acumulado'] = (1.0 + df_ipca['valor']).cumprod()
    ultimo_indice = df_ipca['indice_acumulado'].iloc[-1]
    df_ipca['fator_correcao'] = ultimo_indice / df_ipca['indice_acumulado']
    
    return dict(zip(df_ipca['ano_mes'], df_ipca['fator_correcao']))

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

def calc_fator_privativo(tipo, padrao):
    """
    Fator de conversão de Área Construída Cadastral (Total) para Área Privativa Útil:
    Baseado em normas técnicas (ABNT NBR 12.721 / SINDUSCON / Práticas de Engenharia de Avaliações):
    - Apartamentos de Alto Padrão / Luxo: ~68% da área total é privativa (devido a garagens maiores, lazer e áreas comuns amplas)
    - Apartamentos de Padrão Médio: ~72%
    - Apartamentos de Padrão Simples / Econômico: ~80% (pouca área comum)
    - Salas Comerciais: ~70%
    - Casas e Lojas de rua: 100% (área construída já é a área privativa útil)
    """
    t = str(tipo).upper()
    p = str(padrao).upper()
    
    if 'APART' in t:
        if 'SUPERIOR' in p or 'FINO' in p or 'LUXO' in p:
            return 0.68
        elif 'SIMPLES' in p or 'POPULAR' in p or 'RUSTICO' in p:
            return 0.80
        else:
            return 0.72
    elif 'SALA' in t or 'CONJ' in t:
        return 0.70
    elif 'CASA' in t or 'LOJA' in t or 'GALP' in t:
        return 1.00
    else:
        return 0.75

def main():
    fator_map = get_ipca_series()
    
    print(f"Carregando {INPUT_CONSOLIDATED}...")
    df = pd.read_csv(INPUT_CONSOLIDATED, sep=';', encoding='utf-8-sig', low_memory=False)
    
    df['valor_num'] = df['valor_avaliacao'].apply(clean_val)
    df['area_total_cadastral'] = df['area_construida'].apply(clean_val)
    df['bairro_padronizado'] = df['bairro'].apply(normalize_text)
    
    # 1. Correção IPCA
    df['ano_mes_transacao'] = df['data_transacao'].astype(str).str.slice(0, 7)
    df['fator_ipca'] = df['ano_mes_transacao'].map(fator_map).fillna(1.0)
    df['valor_avaliacao_corrigido'] = (df['valor_num'] * df['fator_ipca']).round(2)
    
    # 2. Correção de Área Privativa
    df['fator_area_privativa'] = df.apply(lambda r: calc_fator_privativo(r['tipo_imovel'], r['padrao_acabamento']), axis=1)
    df['area_privativa_estimada'] = (df['area_total_cadastral'] * df['fator_area_privativa']).round(2)
    
    # 3. Métricas de Preço por m²
    df['preco_m2_total_nominal'] = (df['valor_num'] / df['area_total_cadastral']).round(2)
    df['preco_m2_total_corrigido'] = (df['valor_avaliacao_corrigido'] / df['area_total_cadastral']).round(2)
    df['preco_m2_privativo_nominal'] = (df['valor_num'] / df['area_privativa_estimada']).round(2)
    df['preco_m2_privativo_corrigido'] = (df['valor_avaliacao_corrigido'] / df['area_privativa_estimada']).round(2)
    
    print(f"Salvando dataset consolidado com todas as correções em {OUTPUT_CONSOLIDATED}...")
    df.to_csv(OUTPUT_CONSOLIDATED, index=False, sep=';', encoding='utf-8-sig')
    
    # Filtro de registros válidos para estatísticas (removendo 1% e 99% de outliers)
    valid = df[(df['area_privativa_estimada'] >= 10) & (df['valor_avaliacao_corrigido'] >= 10000)].copy()
    p_low = valid['preco_m2_privativo_corrigido'].quantile(0.01)
    p_high = valid['preco_m2_privativo_corrigido'].quantile(0.99)
    valid_filtered = valid[(valid['preco_m2_privativo_corrigido'] >= p_low) & (valid['preco_m2_privativo_corrigido'] <= p_high)].copy()
    
    # Agrupamento consolidado por bairro
    bairro_stats = valid_filtered.groupby('bairro_padronizado').agg(
        total_transacoes=('preco_m2_privativo_corrigido', 'count'),
        m2_privativo_medio=('preco_m2_privativo_corrigido', 'mean'),
        m2_privativo_mediana=('preco_m2_privativo_corrigido', 'median'),
        m2_total_medio_corrigido=('preco_m2_total_corrigido', 'mean'),
        m2_privativo_nominal_medio=('preco_m2_privativo_nominal', 'mean'),
        m2_privativo_desvio_padrao=('preco_m2_privativo_corrigido', 'std'),
        area_privativa_media=('area_privativa_estimada', 'mean'),
        valor_medio_corrigido=('valor_avaliacao_corrigido', 'mean')
    ).reset_index()
    
    # Normalização Min-Max (0 a 100) baseada no m2 privativo médio
    min_m2 = bairro_stats['m2_privativo_medio'].min()
    max_m2 = bairro_stats['m2_privativo_medio'].max()
    bairro_stats['indice_normalizado_0_100'] = ((bairro_stats['m2_privativo_medio'] - min_m2) / (max_m2 - min_m2)) * 100
    
    # Normalização Z-score
    mean_m2 = bairro_stats['m2_privativo_medio'].mean()
    std_m2 = bairro_stats['m2_privativo_medio'].std()
    bairro_stats['z_score'] = (bairro_stats['m2_privativo_medio'] - mean_m2) / std_m2
    
    bairro_stats = bairro_stats.sort_values('m2_privativo_medio', ascending=False).reset_index(drop=True)
    bairro_stats['ranking'] = range(1, len(bairro_stats) + 1)
    
    col_order = [
        'ranking', 'bairro_padronizado', 'total_transacoes',
        'm2_privativo_medio', 'm2_privativo_mediana', 'm2_total_medio_corrigido',
        'indice_normalizado_0_100', 'z_score', 'area_privativa_media', 'valor_medio_corrigido'
    ]
    bairro_stats = bairro_stats[col_order]
    
    for c in ['m2_privativo_medio', 'm2_privativo_mediana', 'm2_total_medio_corrigido', 'indice_normalizado_0_100', 'z_score', 'area_privativa_media', 'valor_medio_corrigido']:
        bairro_stats[c] = bairro_stats[c].round(2)
        
    bairro_stats.to_csv(OUTPUT_BAIRRO_PRIVATIVO, index=False, sep=';', encoding='utf-8-sig')
    print(f"Tabela por bairro salva em: {OUTPUT_BAIRRO_PRIVATIVO}")
    
    # Série anual por bairro
    anual_stats = valid_filtered.groupby(['bairro_padronizado', 'ano_arquivo']).agg(
        total_transacoes=('preco_m2_privativo_corrigido', 'count'),
        m2_privativo_medio=('preco_m2_privativo_corrigido', 'mean'),
        m2_privativo_mediana=('preco_m2_privativo_corrigido', 'median')
    ).reset_index()
    
    anual_stats['m2_privativo_medio'] = anual_stats['m2_privativo_medio'].round(2)
    anual_stats['m2_privativo_mediana'] = anual_stats['m2_privativo_mediana'].round(2)
    anual_stats.to_csv(OUTPUT_ANUAL_PRIVATIVO, index=False, sep=';', encoding='utf-8-sig')
    print(f"Série anual salva em: {OUTPUT_ANUAL_PRIVATIVO}")

if __name__ == "__main__":
    main()
