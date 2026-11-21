import os
import sys
import time
import sqlite3

try:
    from scripts import (
        process_itbi,
        corrigir_area_e_inflacao,
        padronizar_logradouros,
        processar_revendas,
        recuperar_coordenadas_itbi,
        gerar_relatorio_recuperados,
    )
    from scripts.criar_banco_sqlite import DB_PATH
except ImportError:
    import process_itbi
    import corrigir_area_e_inflacao
    import padronizar_logradouros
    import processar_revendas
    import recuperar_coordenadas_itbi
    import gerar_relatorio_recuperados
    from criar_banco_sqlite import DB_PATH


def get_db_snapshot():
    if not os.path.exists(DB_PATH):
        return {"total_tx": 0, "max_date": "-", "total_edificios": 0}
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        total_tx, max_date = cur.execute(
            "SELECT COUNT(*), COALESCE(MAX(data_transacao), '-') FROM transacoes"
        ).fetchone()
        total_ed = cur.execute("SELECT COUNT(*) FROM edifcios_resumo").fetchone()[0]
        conn.close()
        return {
            "total_tx": total_tx or 0,
            "max_date": max_date or "-",
            "total_edificios": total_ed or 0,
        }
    except Exception:
        return {"total_tx": 0, "max_date": "-", "total_edificios": 0}


def main(force_all=False):
    t0 = time.time()
    before = get_db_snapshot()

    print("=" * 85)
    print("PIPELINE DE ATUALIZAÇÃO AUTOMÁTICA - ITBI PREFEITURA DO RECIFE")
    print("=" * 85)
    print(
        f"Estado anterior: {before['total_tx']:,} transações | "
        f"Última data: {before['max_date']} | "
        f"Edifícios: {before['total_edificios']:,}"
    )

    print("\n[1/6] Consultando Portal de Dados Abertos do Recife e atualizando CSVs...")
    process_itbi.main(force_all=force_all)

    print("\n[2/6] Aplicando correção monetária (IPCA - Banco Central) e área privativa...")
    df = corrigir_area_e_inflacao.main(save_csv=False)

    print("\n[3/6] Padronizando logradouros canônicos e endereços de edifícios...")
    df = padronizar_logradouros.main(df=df, save_csv=False, build_db=False)

    print("\n[4/6] Calculando histórico de revendas por unidade...")
    df = processar_revendas.main(df=df, save_csv=False, build_db=False)

    print("\n[5/6] Recuperando coordenadas geográficas e reconstruindo banco SQLite (.db e .db.gz)...")
    df = recuperar_coordenadas_itbi.main(df=df)

    print("\n[6/6] Atualizando relatórios de auditoria espacial...")
    gerar_relatorio_recuperados.main(df_cons=df)

    after = get_db_snapshot()
    elapsed = time.time() - t0
    delta_tx = after["total_tx"] - before["total_tx"]
    delta_ed = after["total_edificios"] - before["total_edificios"]

    print("\n" + "=" * 85)
    print("ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 85)
    print(f"Transações totais : {before['total_tx']:,} -> {after['total_tx']:,} ({delta_tx:+,})")
    print(f"Data mais recente : {before['max_date']} -> {after['max_date']}")
    print(f"Edifícios no mapa : {before['total_edificios']:,} -> {after['total_edificios']:,} ({delta_ed:+,})")
    print(f"Tempo total       : {elapsed:.1f}s")
    print("=" * 85)


if __name__ == "__main__":
    force = "--all" in sys.argv or "--force" in sys.argv
    main(force_all=force)
