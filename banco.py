import os
import sqlite3

try:
    import psycopg2
    from psycopg2 import IntegrityError as PostgresIntegrityError
except ImportError:
    psycopg2 = None
    PostgresIntegrityError = Exception


erro_integridade = (
    sqlite3.IntegrityError,
    PostgresIntegrityError
)


def usando_postgres():
    """
    Retorna True quando a variável DATABASE_URL estiver configurada.
    No Render e no teste local com Neon, será usado PostgreSQL.
    Caso contrário, será usado SQLite.
    """
    return bool(os.environ.get("DATABASE_URL"))


class CursorAdaptado:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, parametros=()):
        if usando_postgres():
            # Converte os marcadores do SQLite para PostgreSQL.
            sql = sql.replace("?", "%s")

            # Adapta o INSERT OR IGNORE do SQLite.
            sql = sql.replace(
                "INSERT OR IGNORE INTO categorias",
                "INSERT INTO categorias"
            )

            sql = sql.replace(
                "INSERT OR IGNORE INTO",
                "INSERT INTO"
            )

            # Evita categoria duplicada no PostgreSQL.
            if (
                "INSERT INTO categorias" in sql
                and "ON CONFLICT" not in sql
            ):
                sql = sql.replace(
                    "VALUES (%s)",
                    "VALUES (%s) ON CONFLICT (nome) DO NOTHING"
                )

        return self.cursor.execute(sql, parametros)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    @property
    def lastrowid(self):
        """
        Mantém compatibilidade com trechos do sistema
        que consultem lastrowid.
        """
        return getattr(self.cursor, "lastrowid", None)


class ConexaoAdaptada:
    def __init__(self, conexao):
        self.conexao = conexao

    def cursor(self):
        return CursorAdaptado(self.conexao.cursor())

    def commit(self):
        return self.conexao.commit()

    def rollback(self):
        return self.conexao.rollback()

    def close(self):
        return self.conexao.close()


def conectar():
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        if psycopg2 is None:
            raise RuntimeError(
                "O PostgreSQL foi configurado, mas o pacote "
                "psycopg2-binary não está instalado."
            )

        conexao = psycopg2.connect(database_url)
        return ConexaoAdaptada(conexao)

    conexao = sqlite3.connect("base.db")
    return ConexaoAdaptada(conexao)


def criar_banco():
    conexao = conectar()
    cursor = conexao.cursor()

    try:
        if usando_postgres():
            criar_tabelas_postgres(cursor)
            atualizar_tabelas_postgres(cursor)
        else:
            criar_tabelas_sqlite(cursor)
            atualizar_tabelas_sqlite(cursor)

        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


def criar_tabelas_postgres(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            perfil TEXT NOT NULL DEFAULT 'usuario'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id SERIAL PRIMARY KEY,
            nome TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anotacoes (
            id SERIAL PRIMARY KEY,
            titulo TEXT,
            categoria TEXT,
            texto TEXT,
            autor TEXT,
            favorito INTEGER DEFAULT 0,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            autor_id INTEGER,
            data_atualizacao TIMESTAMP,
            visibilidade TEXT DEFAULT 'publica'
        )
    """)


def atualizar_tabelas_postgres(cursor):
    """
    Acrescenta automaticamente colunas novas em bancos
    PostgreSQL que já existiam antes da atualização.
    """

    cursor.execute("""
        ALTER TABLE anotacoes
        ADD COLUMN IF NOT EXISTS autor_id INTEGER
    """)

    cursor.execute("""
        ALTER TABLE anotacoes
        ADD COLUMN IF NOT EXISTS data_atualizacao TIMESTAMP
    """)

    cursor.execute("""
        ALTER TABLE anotacoes
        ADD COLUMN IF NOT EXISTS visibilidade TEXT DEFAULT 'publica'
    """)

    cursor.execute("""
        ALTER TABLE anotacoes
        ADD COLUMN IF NOT EXISTS favorito INTEGER DEFAULT 0
    """)

    cursor.execute("""
        ALTER TABLE anotacoes
        ADD COLUMN IF NOT EXISTS data_criacao
        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    """)

    cursor.execute("""
        UPDATE anotacoes
        SET data_atualizacao = data_criacao
        WHERE data_atualizacao IS NULL
    """)

    cursor.execute("""
        UPDATE anotacoes
        SET visibilidade = 'publica'
        WHERE visibilidade IS NULL
    """)

    cursor.execute("""
        UPDATE anotacoes
        SET favorito = 0
        WHERE favorito IS NULL
    """)


def criar_tabelas_sqlite(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            perfil TEXT NOT NULL DEFAULT 'usuario'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anotacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT,
            categoria TEXT,
            texto TEXT,
            autor TEXT,
            favorito INTEGER DEFAULT 0,
            data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
            autor_id INTEGER,
            data_atualizacao TEXT,
            visibilidade TEXT DEFAULT 'publica'
        )
    """)


def atualizar_tabelas_sqlite(cursor):
    """
    Acrescenta colunas que possam estar faltando
    no banco SQLite antigo.
    """

    colunas = [
        ("autor_id", "INTEGER"),
        ("data_atualizacao", "TEXT"),
        ("visibilidade", "TEXT DEFAULT 'publica'"),
        ("favorito", "INTEGER DEFAULT 0"),
        ("data_criacao", "TEXT DEFAULT CURRENT_TIMESTAMP")
    ]

    for nome_coluna, tipo_coluna in colunas:
        try:
            cursor.execute(
                f"""
                ALTER TABLE anotacoes
                ADD COLUMN {nome_coluna} {tipo_coluna}
                """
            )
        except sqlite3.OperationalError:
            # A coluna provavelmente já existe.
            pass

    cursor.execute("""
        UPDATE anotacoes
        SET data_atualizacao = data_criacao
        WHERE data_atualizacao IS NULL
    """)

    cursor.execute("""
        UPDATE anotacoes
        SET visibilidade = 'publica'
        WHERE visibilidade IS NULL
    """)

    cursor.execute("""
        UPDATE anotacoes
        SET favorito = 0
        WHERE favorito IS NULL
    """)