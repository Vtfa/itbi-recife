import os
import pandas as pd
import numpy as np

try:
    from scripts.criar_banco_sqlite import (
        build_sqlite_db,
        format_numero,
        read_consolidated_csv,
        safe_to_csv,
    )
except ImportError:
    from criar_banco_sqlite import (
        build_sqlite_db,
        format_numero,
        read_consolidated_csv,
        safe_to_csv,
    )

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")

SINGLE_UNIT_TYPES = {"Casa", "Galpão", "Mocambo", "Loja"}


def main(df=None, save_csv=True, build_db=True):
    if df is None:
        print(f"Lendo {CSV_INPUT} para calcular métricas de vendas repetidas...")
        df = read_consolidated_csv(CSV_INPUT)

    # Normalizar número e complemento antes de ordenar e agrupar
    df["numero_fmt"] = format_numero(df["numero_fmt"] if "numero_fmt" in df.columns else df["numero"])
    df["complemento_fmt"] = df["complemento_fmt"].fillna("").astype(str).str.strip()
    df["tem_complemento"] = df["complemento_fmt"] != ""

    # Ordenar rigorosamente por endereço, complemento e data da transação
    df = df.sort_values(by=["endereco_edificio", "complemento_fmt", "data_transacao"]).reset_index(drop=True)

    # Inicializar colunas de revenda com valores padrão seguros (compatível com Pandas 3.0)
    df["chave_imovel"] = pd.Series("", index=df.index, dtype=df["endereco_edificio"].dtype)
    df["ordem_venda"] = 1
    df["total_vendas_imovel"] = 1
    df["eh_revenda"] = False
    df["data_venda_anterior"] = pd.Series(pd.NA, index=df.index, dtype=df["data_transacao"].dtype)
    df["valor_real_anterior"] = np.nan
    df["valor_nom_anterior"] = np.nan
    df["var_real_pct"] = np.nan
    df["var_nom_pct"] = np.nan
    df["dias_entre_vendas"] = np.nan
    df["anos_entre_vendas"] = np.nan
    df["taxa_anual_real_pct"] = np.nan

    # Filtrar transações válidas para pareamento de revendas:
    # - exclui avaliações simbólicas (< R$ 15 mil) e áreas/m² anômalos
    # - exige complemento para unidades em condomínios/edifícios; sem complemento só aceita tipologias unifamiliares com número válido
    valid_metrics = (
        (df["valor_avaliacao_corrigido"] >= 15000)
        & (df["area_privativa_estimada"] >= 10)
        & (df["preco_m2_privativo_corrigido"].between(500, 50000))
    )
    valid_unit_key = df["tem_complemento"] | (
        df["tipo_imovel"].isin(SINGLE_UNIT_TYPES) & (~df["numero_fmt"].isin(["", "0", "S/N"]))
    )
    elig_mask = valid_metrics & valid_unit_key

    df_elig = df.loc[elig_mask].copy()

    base_key = df_elig["endereco_edificio"].copy()
    has_comp_elig = df_elig["tem_complemento"]
    base_key.loc[has_comp_elig] = df_elig.loc[has_comp_elig, "endereco_edificio"] + " | " + df_elig.loc[has_comp_elig, "complemento_fmt"]

    # Quebrar cadeia caso a área cadastral mude > 25% entre transações consecutivas (indica unidade/fração distinta ou demolição/reforma total)
    prev_area = df_elig.groupby(base_key)["area_total_cadastral"].shift(1)
    area_jump = prev_area.notna() & (prev_area > 0) & (
        ((df_elig["area_total_cadastral"] - prev_area).abs() / prev_area) > 0.25
    )
    subchain_id = area_jump.groupby(base_key).cumsum()
    df_elig["chave_imovel"] = np.where(subchain_id > 0, base_key + " #" + subchain_id.astype(str), base_key)

    # Ordem da venda para esta unidade específica
    df_elig["ordem_venda"] = df_elig.groupby("chave_imovel").cumcount() + 1
    df_elig["total_vendas_imovel"] = df_elig.groupby("chave_imovel")["data_transacao"].transform("count")
    df_elig["eh_revenda"] = df_elig["total_vendas_imovel"] > 1

    # Vendas anteriores
    df_elig["data_venda_anterior"] = df_elig.groupby("chave_imovel")["data_transacao"].shift(1)
    df_elig["valor_real_anterior"] = df_elig.groupby("chave_imovel")["valor_avaliacao_corrigido"].shift(1)
    df_elig["valor_nom_anterior"] = df_elig.groupby("chave_imovel")["valor_num"].shift(1)

    # Variação real e nominal
    df_elig["var_real_pct"] = (
        (df_elig["valor_avaliacao_corrigido"] - df_elig["valor_real_anterior"]) / df_elig["valor_real_anterior"] * 100
    ).round(2)
    df_elig["var_nom_pct"] = (
        (df_elig["valor_num"] - df_elig["valor_nom_anterior"]) / df_elig["valor_nom_anterior"] * 100
    ).round(2)

    # Tempo entre vendas em dias e anos
    df_elig["dias_entre_vendas"] = (
        pd.to_datetime(df_elig["data_transacao"]) - pd.to_datetime(df_elig["data_venda_anterior"])
    ).dt.days
    df_elig["anos_entre_vendas"] = (df_elig["dias_entre_vendas"] / 365.25).round(2)

    # Taxa anualizada real (% a.a. composto) para vendas com pelo menos 180 dias de intervalo
    cond_anual = (
        (df_elig["anos_entre_vendas"] >= 0.5)
        & (df_elig["valor_real_anterior"] > 0)
        & (df_elig["valor_avaliacao_corrigido"] > 0)
    )
    df_elig.loc[cond_anual, "taxa_anual_real_pct"] = (
        (
            (df_elig.loc[cond_anual, "valor_avaliacao_corrigido"] / df_elig.loc[cond_anual, "valor_real_anterior"])
            ** (1.0 / df_elig.loc[cond_anual, "anos_entre_vendas"])
            - 1.0
        )
        * 100
    ).round(2)

    # Reatribuir colunas calculadas ao DataFrame principal
    cols_to_assign = [
        "chave_imovel",
        "ordem_venda",
        "total_vendas_imovel",
        "eh_revenda",
        "data_venda_anterior",
        "valor_real_anterior",
        "valor_nom_anterior",
        "var_real_pct",
        "var_nom_pct",
        "dias_entre_vendas",
        "anos_entre_vendas",
        "taxa_anual_real_pct",
    ]
    for col in cols_to_assign:
        df.loc[elig_mask, col] = df_elig[col]

    print(f"Total de transações: {len(df):,}")
    print(f"Total de transações elegíveis para revenda: {elig_mask.sum():,}")
    print(f"Total de imóveis únicos com mais de 1 venda: {df[df['eh_revenda']]['chave_imovel'].nunique():,}")
    print(f"Total de registros em histórico de revenda: {df['eh_revenda'].sum():,}")

    if save_csv:
        # Salvar no CSV consolidado
        safe_to_csv(df, CSV_INPUT)
        print(f"Arquivo CSV atualizado em {CSV_INPUT}")

    if build_db:
        # Atualizar banco de dados SQLite usando o construtor unificado
        build_sqlite_db(df)
    return df


if __name__ == "__main__":
    main()
