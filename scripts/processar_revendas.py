import os
import sqlite3
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "itbi_recife.db")

def main():
    print(f"Lendo {CSV_INPUT} para calcular métricas de vendas repetidas...")
    df = pd.read_csv(CSV_INPUT, sep=';', encoding='utf-8-sig', low_memory=False)
    
    # Ordenar rigorosamente por endereço, complemento e data da transação
    df['complemento_fmt'] = df['complemento_fmt'].fillna('').astype(str).str.strip()
    df = df.sort_values(by=['endereco_edificio', 'complemento_fmt', 'data_transacao']).reset_index(drop=True)
    
    # Identificar unidades válidas
    df['tem_complemento'] = (df['complemento_fmt'] != '')
    
    # Agrupar por imóvel único
    # Se tem complemento, agrupa por (endereco_edificio, complemento_fmt)
    # Se não tem complemento (ex: casa isolada), agrupa por endereco_edificio
    df['chave_imovel'] = df['endereco_edificio']
    df.loc[df['tem_complemento'], 'chave_imovel'] = df['endereco_edificio'] + ' | ' + df['complemento_fmt']
    
    # Ordem da venda para esta unidade específica
    df['ordem_venda'] = df.groupby('chave_imovel').cumcount() + 1
    df['total_vendas_imovel'] = df.groupby('chave_imovel')['data_transacao'].transform('count')
    df['eh_revenda'] = df['total_vendas_imovel'] > 1
    
    # Vendas anteriores
    df['data_venda_anterior'] = df.groupby('chave_imovel')['data_transacao'].shift(1)
    df['valor_real_anterior'] = df.groupby('chave_imovel')['valor_avaliacao_corrigido'].shift(1)
    df['valor_nom_anterior'] = df.groupby('chave_imovel')['valor_num'].shift(1)
    
    # Variação real e nominal
    df['var_real_pct'] = ((df['valor_avaliacao_corrigido'] - df['valor_real_anterior']) / df['valor_real_anterior'] * 100).round(2)
    df['var_nom_pct'] = ((df['valor_num'] - df['valor_nom_anterior']) / df['valor_nom_anterior'] * 100).round(2)
    
    # Tempo entre vendas em dias e anos
    df['dias_entre_vendas'] = (pd.to_datetime(df['data_transacao']) - pd.to_datetime(df['data_venda_anterior'])).dt.days
    df['anos_entre_vendas'] = (df['dias_entre_vendas'] / 365.25).round(2)
    
    # Taxa anualizada real (% a.a. composto) para vendas com pelo menos 180 dias de intervalo
    cond_anual = (df['anos_entre_vendas'] >= 0.5) & (df['valor_real_anterior'] > 0) & (df['valor_avaliacao_corrigido'] > 0)
    df['taxa_anual_real_pct'] = np.nan
    df.loc[cond_anual, 'taxa_anual_real_pct'] = (((df.loc[cond_anual, 'valor_avaliacao_corrigido'] / df.loc[cond_anual, 'valor_real_anterior']) ** (1.0 / df.loc[cond_anual, 'anos_entre_vendas']) - 1.0) * 100).round(2)
    
    print(f"Total de transações: {len(df):,}")
    print(f"Total de imóveis únicos com mais de 1 venda: {df[df['eh_revenda']]['chave_imovel'].nunique():,}")
    print(f"Total de registros em histórico de revenda: {df['eh_revenda'].sum():,}")
    
    # Salvar no CSV consolidado
    df.to_csv(CSV_INPUT, index=False, sep=';', encoding='utf-8-sig')
    print(f"Arquivo CSV atualizado em {CSV_INPUT}")
    
    # Atualizar banco de dados SQLite
    print(f"Atualizando banco SQLite ({DB_PATH})...")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    conn = sqlite3.connect(DB_PATH)
    df.to_sql('transacoes', conn, index=False, if_exists='replace')
    
    cursor = conn.cursor()
    cursor.execute("CREATE INDEX idx_cod_logr ON transacoes(cod_logradouro);")
    cursor.execute("CREATE INDEX idx_endereco_edificio ON transacoes(endereco_edificio);")
    cursor.execute("CREATE INDEX idx_chave_imovel ON transacoes(chave_imovel);")
    cursor.execute("CREATE INDEX idx_bairro ON transacoes(bairro_padronizado);")
    cursor.execute("CREATE INDEX idx_logradouro ON transacoes(logradouro_canonico);")
    cursor.execute("CREATE INDEX idx_data ON transacoes(data_transacao);")
    cursor.execute("CREATE INDEX idx_revendas ON transacoes(eh_revenda, total_vendas_imovel);")
    
    # Recriar tabela edifcios_resumo com métricas de revenda
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
    print("Banco de dados SQLite atualizado com índices e tabelas de revendas!")

if __name__ == "__main__":
    main()
