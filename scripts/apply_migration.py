"""
scripts/apply_migration.py
Aplica una migración SQL contra la BD PostgreSQL de Supabase.

Dos modos de conexión:

    1. Con DATABASE_URL completa en .env (recomendado):
         DATABASE_URL=postgresql://postgres:<PASSWORD>@db.<REF>.supabase.co:5432/postgres

       O con pooler:
         DATABASE_URL=postgresql://postgres.<REF>:<PASSWORD>@aws-0-<REGION>.pooler.supabase.com:6543/postgres

    2. Con variables sueltas:
         POSTGRES_HOST=db.<REF>.supabase.co
         POSTGRES_PORT=5432
         POSTGRES_USER=postgres
         POSTGRES_PASSWORD=<PASSWORD>
         POSTGRES_DB=postgres

Si no hay credenciales de PostgreSQL, el script imprime el SQL a aplicar
manualmente en Supabase Dashboard > SQL Editor.

Uso:
    cd lvca_agua
    python -m scripts.apply_migration database/migrations/010_parametros_eca_metadata.sql
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from dotenv import load_dotenv


def _resolver_conexion() -> str | None:
    """Devuelve una DATABASE_URL resolviendo desde .env."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url

    host = os.environ.get("POSTGRES_HOST", "").strip()
    user = os.environ.get("POSTGRES_USER", "postgres").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()
    port = os.environ.get("POSTGRES_PORT", "5432").strip()
    db = os.environ.get("POSTGRES_DB", "postgres").strip()
    if host and password:
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return None


def _aplicar_via_psycopg(sql: str, conn_url: str) -> None:
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 no está instalado.")
        print("       Instala con: pip install psycopg2-binary")
        sys.exit(1)

    print(f"  Conectando a PostgreSQL...")
    conn = psycopg2.connect(conn_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            # Capturar NOTICEs que emiten los bloques DO $$ de verificación
            for notice in conn.notices:
                print(f"    [DB] {notice.strip()}")
        conn.commit()
        print("  Migración aplicada correctamente.")
    except Exception as exc:
        conn.rollback()
        print(f"  ERROR: {exc}")
        print("  Transacción revertida. Nada fue modificado en la BD.")
        sys.exit(1)
    finally:
        conn.close()


def _imprimir_instrucciones_manual(sql: str, migration_path: Path) -> None:
    print()
    print("=" * 70)
    print("  No se encontraron credenciales de PostgreSQL en .env")
    print("=" * 70)
    print()
    print(f"  Opción A — aplicar manualmente en Supabase:")
    print(f"    1. Abrir Supabase Dashboard > SQL Editor > New query")
    print(f"    2. Copiar el contenido de: {migration_path}")
    print(f"    3. Ejecutar (botón RUN)")
    print()
    print(f"  Opción B — automatizar este script:")
    print(f"    Añadir a .env una de estas variantes:")
    print()
    print(f"      DATABASE_URL=postgresql://postgres:<PASSWORD>@db.<REF>.supabase.co:5432/postgres")
    print()
    print(f"    O bien variables sueltas:")
    print(f"      POSTGRES_HOST=db.<REF>.supabase.co")
    print(f"      POSTGRES_PASSWORD=<tu password>")
    print()
    print(f"    La password se encuentra en: Supabase Dashboard > Settings > Database")
    print("=" * 70)


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.apply_migration <ruta_al_sql>")
        sys.exit(1)

    migration_path = Path(sys.argv[1]).resolve()
    if not migration_path.exists():
        print(f"ERROR: archivo no encontrado: {migration_path}")
        sys.exit(1)

    sql = migration_path.read_text(encoding="utf-8")
    print(f"\n  Archivo: {migration_path.name}")
    print(f"  Tamaño:  {len(sql)} caracteres, {sql.count(chr(10))} líneas")

    conn_url = _resolver_conexion()
    if conn_url:
        _aplicar_via_psycopg(sql, conn_url)
    else:
        _imprimir_instrucciones_manual(sql, migration_path)


if __name__ == "__main__":
    main()
