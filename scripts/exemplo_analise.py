import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado.csv")

def main():
    print(f"Carregando dataset consolidado de: {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH, sep=';', encoding='utf-8-sig', low_memory=False)
    
    print("\n" + "="*50)
    print("RESUMO GERAL")
    print("="*50)
    print(f"Total de registros: {len(df):,}")
    print(f"Total de colunas: {len(df.columns)}")
    
    print("\n" + "="*50)
    print("TRANSAÇÕES POR ANO")
    print("="*50)
    if 'ano_arquivo' in df.columns:
        print(df['ano_arquivo'].value_counts().sort_index().to_string())
    
    print("\n" + "="*50)
    print("TOP 10 BAIRROS COM MAIS TRANSAÇÕES")
    print("="*50)
    if 'bairro' in df.columns:
        print(df['bairro'].value_counts().head(10).to_string())
        
    print("\n" + "="*50)
    print("TIPOS DE IMÓVEL MAIS FREQUENTES")
    print("="*50)
    if 'tipo_imovel' in df.columns:
        print(df['tipo_imovel'].value_counts().head(10).to_string())

if __name__ == "__main__":
    main()
