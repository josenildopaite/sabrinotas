import os
import shutil
import sqlite3
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor


ARQUIVO_SQLITE = "base.db"


def criar_backup():
    """Cria uma cópia de segurança do banco SQLite antes da migração."""
    if not os.path.exists(ARQUIVO_SQLITE):
        raise FileNotFoundError(
            f'O arquivo "{ARQUIVO_SQLITE}" não foi encontrado.'
        )

    data_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_backup = f"base_backup_{data_hora}.db"

    shutil.copy2(ARQUIVO_SQLITE, nome_backup)

    print(f"✅ Backup criado: {nome_backup}")


def conectar_sqlite():
    conexao = sqlite3.connect(ARQUIVO_SQLITE)
    conexao.row_factory = sqlite3.Row
    return conexao


def conectar_postgres():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "A variável DATABASE_URL não está configurada neste terminal."
        )

    return psycopg2.connect(
        database_url,
        cursor_factory=RealDictCursor
    )


def obter_colunas_sqlite(cursor, tabela):
    cursor.execute(f"PRAGMA table_info({tabela})")
    return [linha["name"] for linha in cursor.fetchall()]


def tabela_existe_sqlite(cursor, tabela):
    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (tabela,)
    )

    return cursor.fetchone() is not None


def criar_tabelas_postgres(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            perfil TEXT NOT NULL DEFAULT 'usuario'
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL UNIQUE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS anotacoes (
            id INTEGER PRIMARY KEY,
            titulo TEXT NOT NULL,
            categoria TEXT,
            texto TEXT,
            autor TEXT,
            autor_id INTEGER,
            favorito INTEGER DEFAULT 0,
            visibilidade TEXT DEFAULT 'privada',
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_anotacoes_usuario
                FOREIGN KEY (autor_id)
                REFERENCES usuarios(id)
                ON DELETE SET NULL
        )
        """
    )

    print("✅ Tabelas verificadas/criadas no PostgreSQL.")


def migrar_usuarios(cursor_sqlite, cursor_postgres):
    if not tabela_existe_sqlite(cursor_sqlite, "usuarios"):
        print("⚠️ A tabela usuarios não existe no SQLite.")
        return

    colunas = obter_colunas_sqlite(cursor_sqlite, "usuarios")
    cursor_sqlite.execute("SELECT * FROM usuarios ORDER BY id")
    usuarios = cursor_sqlite.fetchall()

    quantidade = 0

    for usuario in usuarios:
        dados = dict(usuario)

        cursor_postgres.execute(
            """
            INSERT INTO usuarios (
                id,
                nome,
                email,
                senha,
                perfil
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id)
            DO UPDATE SET
                nome = EXCLUDED.nome,
                email = EXCLUDED.email,
                senha = EXCLUDED.senha,
                perfil = EXCLUDED.perfil
            """,
            (
                dados.get("id"),
                dados.get("nome", ""),
                dados.get("email", ""),
                dados.get("senha", ""),
                dados.get("perfil", "usuario")
                if "perfil" in colunas
                else "usuario"
            )
        )

        quantidade += 1

    print(f"✅ Usuários migrados: {quantidade}")


def migrar_categorias(cursor_sqlite, cursor_postgres):
    if not tabela_existe_sqlite(cursor_sqlite, "categorias"):
        print("⚠️ A tabela categorias não existe no SQLite.")
        return

    cursor_sqlite.execute("SELECT * FROM categorias ORDER BY id")
    categorias = cursor_sqlite.fetchall()

    quantidade = 0

    for categoria in categorias:
        dados = dict(categoria)

        cursor_postgres.execute(
            """
            INSERT INTO categorias (id, nome)
            VALUES (%s, %s)
            ON CONFLICT (id)
            DO UPDATE SET
                nome = EXCLUDED.nome
            """,
            (
                dados.get("id"),
                dados.get("nome", "")
            )
        )

        quantidade += 1

    print(f"✅ Categorias migradas: {quantidade}")


def migrar_anotacoes(cursor_sqlite, cursor_postgres):
    if not tabela_existe_sqlite(cursor_sqlite, "anotacoes"):
        print("⚠️ A tabela anotacoes não existe no SQLite.")
        return

    colunas = obter_colunas_sqlite(cursor_sqlite, "anotacoes")

    cursor_sqlite.execute("SELECT * FROM anotacoes ORDER BY id")
    anotacoes = cursor_sqlite.fetchall()

    quantidade = 0

    for anotacao in anotacoes:
        dados = dict(anotacao)

        autor_id = (
            dados.get("autor_id")
            if "autor_id" in colunas
            else None
        )

        autor = (
            dados.get("autor")
            if "autor" in colunas
            else None
        )

        favorito = (
            dados.get("favorito", 0)
            if "favorito" in colunas
            else 0
        )

        visibilidade = (
            dados.get("visibilidade", "privada")
            if "visibilidade" in colunas
            else "privada"
        )

        data_criacao = (
            dados.get("data_criacao")
            if "data_criacao" in colunas
            else None
        )

        cursor_postgres.execute(
            """
            INSERT INTO anotacoes (
                id,
                titulo,
                categoria,
                texto,
                autor,
                autor_id,
                favorito,
                visibilidade,
                data_criacao
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                COALESCE(%s, CURRENT_TIMESTAMP)
            )
            ON CONFLICT (id)
            DO UPDATE SET
                titulo = EXCLUDED.titulo,
                categoria = EXCLUDED.categoria,
                texto = EXCLUDED.texto,
                autor = EXCLUDED.autor,
                autor_id = EXCLUDED.autor_id,
                favorito = EXCLUDED.favorito,
                visibilidade = EXCLUDED.visibilidade,
                data_criacao = EXCLUDED.data_criacao
            """,
            (
                dados.get("id"),
                dados.get("titulo", ""),
                dados.get("categoria"),
                dados.get("texto", ""),
                autor,
                autor_id,
                favorito,
                visibilidade,
                data_criacao
            )
        )

        quantidade += 1

    print(f"✅ Anotações migradas: {quantidade}")


def ajustar_sequencias(cursor):
    """
    Cria sequências para que novos registros recebam IDs
    automaticamente após a migração.
    """

    tabelas = [
        ("usuarios", "usuarios_id_seq"),
        ("categorias", "categorias_id_seq"),
        ("anotacoes", "anotacoes_id_seq")
    ]

    for tabela, sequencia in tabelas:
        cursor.execute(
            f"""
            CREATE SEQUENCE IF NOT EXISTS {sequencia}
            OWNED BY {tabela}.id
            """
        )

        cursor.execute(
            f"""
            ALTER TABLE {tabela}
            ALTER COLUMN id
            SET DEFAULT nextval('{sequencia}')
            """
        )

        cursor.execute(
            f"""
            SELECT setval(
                '{sequencia}',
                COALESCE((SELECT MAX(id) FROM {tabela}), 0) + 1,
                false
            )
            """
        )

    print("✅ Sequências de IDs ajustadas.")


def conferir_quantidades(cursor_sqlite, cursor_postgres):
    print("\n📊 CONFERÊNCIA FINAL")

    tabelas = ["usuarios", "categorias", "anotacoes"]

    for tabela in tabelas:
        quantidade_sqlite = 0
        quantidade_postgres = 0

        if tabela_existe_sqlite(cursor_sqlite, tabela):
            cursor_sqlite.execute(f"SELECT COUNT(*) AS total FROM {tabela}")
            quantidade_sqlite = cursor_sqlite.fetchone()["total"]

        cursor_postgres.execute(f"SELECT COUNT(*) AS total FROM {tabela}")
        quantidade_postgres = cursor_postgres.fetchone()["total"]

        status = (
            "✅"
            if quantidade_sqlite == quantidade_postgres
            else "⚠️"
        )

        print(
            f"{status} {tabela}: "
            f"SQLite = {quantidade_sqlite} | "
            f"PostgreSQL = {quantidade_postgres}"
        )


def executar_migracao():
    conexao_sqlite = None
    conexao_postgres = None

    try:
        print("\n🚀 Iniciando migração SQLite → PostgreSQL\n")

        criar_backup()

        conexao_sqlite = conectar_sqlite()
        conexao_postgres = conectar_postgres()

        cursor_sqlite = conexao_sqlite.cursor()
        cursor_postgres = conexao_postgres.cursor()

        criar_tabelas_postgres(cursor_postgres)

        migrar_usuarios(cursor_sqlite, cursor_postgres)
        migrar_categorias(cursor_sqlite, cursor_postgres)
        migrar_anotacoes(cursor_sqlite, cursor_postgres)

        ajustar_sequencias(cursor_postgres)

        conexao_postgres.commit()

        conferir_quantidades(
            cursor_sqlite,
            cursor_postgres
        )

        print("\n🎉 Migração concluída com sucesso!")
        print("O arquivo base.db não foi apagado.")

    except Exception as erro:
        if conexao_postgres:
            conexao_postgres.rollback()

        print("\n❌ A migração não foi concluída.")
        print(f"Motivo: {erro}")

    finally:
        if conexao_sqlite:
            conexao_sqlite.close()

        if conexao_postgres:
            conexao_postgres.close()


if __name__ == "__main__":
    executar_migracao()