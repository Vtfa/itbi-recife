import os
import gzip
import shutil
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "itbi_recife.db")
DB_GZ_PATH = DB_PATH + ".gz"

STRING_COLS = [
    "logradouro",
    "numero",
    "complemento",
    "numero_fmt",
    "complemento_fmt",
    "logradouro_canonico",
    "bairro_padronizado",
    "endereco_edificio",
    "endereco_completo",
    "chave_imovel",
    "data_transacao",
    "data_venda_anterior",
    "metodo_geolocalizacao",
]


def format_numero(series):
    """Formata números de logradouro removendo '.0' apenas no final e preenchendo vazios com 'S/N'."""
    cleaned = (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    return cleaned.replace({"": "S/N", "nan": "S/N", "None": "S/N"})


def read_consolidated_csv(csv_path=CSV_INPUT):
    """Lê a base consolidada preservando colunas textuais como strings."""
    dtype_map = {col: str for col in STRING_COLS}
    return pd.read_csv(
        csv_path,
        sep=";",
        encoding="utf-8-sig",
        low_memory=False,
        dtype=dtype_map,
    )


def build_sqlite_db(df=None, compress_gz=True):
    """Reconstrói o banco SQLite (transacoes + edifcios_resumo + índices) e atualiza o .db.gz."""
    if df is None:
        print(f"Lendo base consolidada para importar no SQLite ({CSV_INPUT})...")
        df = read_consolidated_csv(CSV_INPUT)
    else:
        df = df.copy()

    # Garantir colunas textuais essenciais
    if "logradouro_canonico" not in df.columns:
        df["logradouro_canonico"] = df["logradouro"].fillna("").astype(str).str.strip().str.title()

    df["numero_fmt"] = format_numero(df["numero_fmt"] if "numero_fmt" in df.columns else df["numero"])
    comp_source = df["complemento_fmt"] if "complemento_fmt" in df.columns else df["complemento"]
    df["complemento_fmt"] = comp_source.fillna("").astype(str).str.strip().str.title()

    if "bairro_padronizado" not in df.columns:
        df["bairro_padronizado"] = df["bairro"].fillna("Desconhecido").astype(str).str.strip().str.title()

    df["endereco_edificio"] = df["logradouro_canonico"] + ", " + df["numero_fmt"] + " - " + df["bairro_padronizado"]
    df["endereco_completo"] = (
        df["logradouro_canonico"]
        + ", "
        + df["numero_fmt"]
        + " "
        + df["complemento_fmt"]
        + " - "
        + df["bairro_padronizado"]
    ).str.replace(r"\s+", " ", regex=True).str.strip()

    # Garantir colunas de revenda e geolocalização mesmo em execuções parciais
    if "total_vendas_imovel" not in df.columns:
        df["total_vendas_imovel"] = 1
    if "eh_revenda" not in df.columns:
        df["eh_revenda"] = False
    if "ordem_venda" not in df.columns:
        df["ordem_venda"] = 1
    if "metodo_geolocalizacao" not in df.columns:
        df["metodo_geolocalizacao"] = "Original da Prefeitura"

    # Tipagem numérica segura
    for num_col in ["ano_construcao", "latitude", "longitude"]:
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")

    print(f"Criando banco de dados SQLite em {DB_PATH}...")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    sql_dtypes = {col: "TEXT" for col in STRING_COLS if col in df.columns}
    df.to_sql("transacoes", conn, index=False, if_exists="replace", dtype=sql_dtypes)

    cursor = conn.cursor()
    print("Criando índices em transacoes...")
    cursor.execute("CREATE INDEX idx_cod_logr ON transacoes(cod_logradouro);")
    cursor.execute("CREATE INDEX idx_endereco_edificio ON transacoes(endereco_edificio);")
    if "chave_imovel" in df.columns:
        cursor.execute("CREATE INDEX idx_chave_imovel ON transacoes(chave_imovel);")
    cursor.execute("CREATE INDEX idx_bairro ON transacoes(bairro_padronizado);")
    cursor.execute("CREATE INDEX idx_logradouro ON transacoes(logradouro_canonico);")
    cursor.execute("CREATE INDEX idx_data ON transacoes(data_transacao);")
    cursor.execute("CREATE INDEX idx_coords ON transacoes(latitude, longitude);")
    cursor.execute("CREATE INDEX idx_revendas ON transacoes(eh_revenda, total_vendas_imovel);")

    # Tabela agregada de edifícios
    # Prioriza 'Original da Prefeitura' se houver ao menos uma coordenada original no prédio
    cursor.execute("""
    CREATE TABLE edifcios_resumo AS
    SELECT
        cod_logradouro,
        endereco_edificio,
        bairro_padronizado,
        logradouro_canonico,
        numero_fmt,
        COUNT(*) as total_transacoes,
        SUM(CASE WHEN eh_revenda = 1 THEN 1 ELSE 0 END) as total_revendas,
        ROUND(AVG(preco_m2_privativo_corrigido), 2) as m2_privativo_medio,
        ROUND(AVG(valor_avaliacao_corrigido), 2) as valor_medio_corrigido,
        ROUND(MIN(valor_avaliacao_corrigido), 2) as valor_min_corrigido,
        ROUND(MAX(valor_avaliacao_corrigido), 2) as valor_max_corrigido,
        ROUND(AVG(area_privativa_estimada), 2) as area_privativa_media,
        AVG(latitude) as latitude,
        AVG(longitude) as longitude,
        CASE
            WHEN MAX(CASE WHEN metodo_geolocalizacao = 'Original da Prefeitura' THEN 1 ELSE 0 END) = 1
                THEN 'Original da Prefeitura'
            ELSE MAX(metodo_geolocalizacao)
        END as metodo_geolocalizacao
    FROM transacoes
    WHERE preco_m2_privativo_corrigido > 500 AND preco_m2_privativo_corrigido < 35000
    GROUP BY cod_logradouro, numero_fmt, bairro_padronizado;
    """)

    cursor.execute("CREATE INDEX idx_predios_endereco ON edifcios_resumo(endereco_edificio);")
    cursor.execute("CREATE INDEX idx_predios_bairro ON edifcios_resumo(bairro_padronizado);")
    cursor.execute("CREATE INDEX idx_predios_total ON edifcios_resumo(total_transacoes DESC);")
    cursor.execute("CREATE INDEX idx_predios_coords ON edifcios_resumo(latitude, longitude);")

    conn.commit()
    conn.close()
    print(f"Banco SQLite configurado com sucesso! Total de transações: {len(df):,}")

    if compress_gz:
        print(f"Gerando arquivo compactado para deploy ({DB_GZ_PATH})...")
        tmp_gz = DB_GZ_PATH + ".tmp"
        with open(DB_PATH, "rb") as f_in:
            with gzip.open(tmp_gz, "wb", compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.replace(tmp_gz, DB_GZ_PATH)
        gz_mb = os.path.getsize(DB_GZ_PATH) / (1024 * 1024)
        print(f"Arquivo {DB_GZ_PATH} atualizado ({gz_mb:.1f} MB).")


def main():
    build_sqlite_db()


if __name__ == "__main__":
    main()
