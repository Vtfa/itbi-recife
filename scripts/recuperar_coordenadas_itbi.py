import os
import sqlite3
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "itbi_recife.db")
RELATORIO_CSV = os.path.join(BASE_DIR, "data", "processed", "imoveis_recuperados_georreferenciados.csv")

def main():
    print("Iniciando recuperação de coordenadas geográficas dos imóveis...")
    df = pd.read_csv(CSV_INPUT, sep=';', encoding='utf-8-sig', low_memory=False)
    
    # 1. Mapa de coordenadas conhecidas por (cod_logradouro, numero)
    df_com_coords = df[df['latitude'].notna() & df['longitude'].notna()].copy()
    
    # Média de coordenadas por logradouro
    coords_por_rua = df_com_coords.groupby('cod_logradouro').agg(
        lat_rua=('latitude', 'mean'),
        lng_rua=('longitude', 'mean')
    ).reset_index()
    
    # Média de coordenadas por bairro (para ruas que não tinham nenhuma coordenada na base)
    coords_por_bairro = df_com_coords.groupby('bairro_padronizado').agg(
        lat_bairro=('latitude', 'mean'),
        lng_bairro=('longitude', 'mean')
    ).reset_index()
    
    mapa_rua_lat = dict(zip(coords_por_rua['cod_logradouro'], coords_por_rua['lat_rua']))
    mapa_rua_lng = dict(zip(coords_por_rua['cod_logradouro'], coords_por_rua['lng_rua']))
    mapa_bairro_lat = dict(zip(coords_por_bairro['bairro_padronizado'], coords_por_bairro['lat_bairro']))
    mapa_bairro_lng = dict(zip(coords_por_bairro['bairro_padronizado'], coords_por_bairro['lng_bairro']))
    
    # Identificar registros sem coordenadas
    cond_sem_coord = df['latitude'].isna() | df['longitude'].isna()
    print(f"Total de transações sem coordenadas no arquivo: {cond_sem_coord.sum():,}")
    
    # Aplicar recuperação: primeiro por rua, depois por bairro
    metodos = []
    novas_lats = []
    novas_lngs = []
    
    for idx, row in df.iterrows():
        if pd.isna(row['latitude']) or pd.isna(row['longitude']):
            cod = row['cod_logradouro']
            bairro = row['bairro_padronizado']
            
            if cod in mapa_rua_lat:
                novas_lats.append(round(mapa_rua_lat[cod], 6))
                novas_lngs.append(round(mapa_rua_lng[cod], 6))
                metodos.append("Interpolação de Logradouro (Mesma Rua)")
            elif bairro in mapa_bairro_lat:
                novas_lats.append(round(mapa_bairro_lat[bairro], 6))
                novas_lngs.append(round(mapa_bairro_lng[bairro], 6))
                metodos.append("Centroide Geográfico do Bairro")
            else:
                novas_lats.append(-8.0578)
                novas_lngs.append(-34.8829)
                metodos.append("Centro de Recife")
        else:
            novas_lats.append(row['latitude'])
            novas_lngs.append(row['longitude'])
            metodos.append("Original da Prefeitura")
            
    df['latitude'] = novas_lats
    df['longitude'] = novas_lngs
    df['metodo_geolocalizacao'] = metodos
    
    # Salvar dataset corrigido
    df.to_csv(CSV_INPUT, index=False, sep=';', encoding='utf-8-sig')
    print("CSV consolidado atualizado com 100% de coordenadas preenchidas.")
    
    # Gerar relatório dos imóveis recuperados agrupados por edifício
    df_recuperados = df[df['metodo_geolocalizacao'] != 'Original da Prefeitura'].copy()
    
    relatorio_predios = df_recuperados.groupby(['bairro_padronizado', 'endereco_edificio', 'metodo_geolocalizacao']).agg(
        total_transacoes=('valor_avaliacao_corrigido', 'count'),
        m2_privativo_medio=('preco_m2_privativo_corrigido', 'mean'),
        valor_medio_corrigido=('valor_avaliacao_corrigido', 'mean'),
        area_privativa_media=('area_privativa_estimada', 'mean'),
        latitude=('latitude', 'first'),
        longitude=('longitude', 'first')
    ).reset_index()
    
    for col in ['m2_privativo_medio', 'valor_medio_corrigido', 'area_privativa_media']:
        relatorio_predios[col] = relatorio_predios[col].round(2)
        
    relatorio_predios = relatorio_predios.sort_values(by=['bairro_padronizado', 'total_transacoes'], ascending=[True, False]).reset_index(drop=True)
    relatorio_predios.to_csv(RELATORIO_CSV, index=False, sep=';', encoding='utf-8-sig')
    print(f"Relatório de edifícios recuperados salvo em: {RELATORIO_CSV}")
    
    # Atualizar o banco SQLite
    print(f"Atualizando banco SQLite ({DB_PATH})...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    df.to_sql('transacoes', conn, index=False, if_exists='replace')
    
    cursor.execute("CREATE INDEX idx_cod_logr ON transacoes(cod_logradouro);")
    cursor.execute("CREATE INDEX idx_endereco_edificio ON transacoes(endereco_edificio);")
    cursor.execute("CREATE INDEX idx_chave_imovel ON transacoes(chave_imovel);")
    cursor.execute("CREATE INDEX idx_bairro ON transacoes(bairro_padronizado);")
    cursor.execute("CREATE INDEX idx_logradouro ON transacoes(logradouro_canonico);")
    cursor.execute("CREATE INDEX idx_data ON transacoes(data_transacao);")
    cursor.execute("CREATE INDEX idx_coords ON transacoes(latitude, longitude);")
    cursor.execute("CREATE INDEX idx_revendas ON transacoes(eh_revenda, total_vendas_imovel);")
    
    cursor.execute("DROP TABLE IF EXISTS edifcios_resumo;")
    cursor.execute("""
    CREATE TABLE edifcios_resumo AS
    SELECT 
        cod_logradouro,
        endereco_edificio,
        bairro_padronizado,
        logradouro_canonico,
        numero_fmt,
        COUNT(*) as total_transacoes,
        SUM(CASE WHEN total_vendas_imovel > 1 THEN 1 ELSE 0 END) as total_revendas,
        ROUND(AVG(preco_m2_privativo_corrigido), 2) as m2_privativo_medio,
        ROUND(AVG(valor_avaliacao_corrigido), 2) as valor_medio_corrigido,
        ROUND(MIN(valor_avaliacao_corrigido), 2) as valor_min_corrigido,
        ROUND(MAX(valor_avaliacao_corrigido), 2) as valor_max_corrigido,
        ROUND(AVG(area_privativa_estimada), 2) as area_privativa_media,
        AVG(latitude) as latitude,
        AVG(longitude) as longitude
    FROM transacoes
    WHERE preco_m2_privativo_corrigido > 500 AND preco_m2_privativo_corrigido < 35000
    GROUP BY cod_logradouro, numero_fmt, bairro_padronizado;
    """)
    cursor.execute("CREATE INDEX idx_predios_bairro ON edifcios_resumo(bairro_padronizado);")
    cursor.execute("CREATE INDEX idx_predios_coords ON edifcios_resumo(latitude, longitude);")
    
    conn.commit()
    conn.close()
    print("Banco SQLite atualizado com 100% de cobertura espacial!")
    
    # Resumo por bairro dos imóveis recuperados
    resumo_bairro = relatorio_predios.groupby('bairro_padronizado').agg(
        edificios_recuperados=('endereco_edificio', 'count'),
        transacoes_recuperadas=('total_transacoes', 'sum')
    ).reset_index().sort_values(by='transacoes_recuperadas', ascending=False)
    
    print("\n" + "="*80)
    print("TOP 25 BAIRROS COM MAIS IMÓVEIS/TRANSAÇÕES RECUPERADAS:")
    print("="*80)
    print(resumo_bairro.head(25).to_string(index=False))

if __name__ == "__main__":
    main()
