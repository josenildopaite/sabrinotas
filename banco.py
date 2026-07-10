import os
import sqlite3

try:
    import psycopg2
    from psycopg2 import IntegrityError as PostgresIntegrityError
except ImportError:
    psycopg2 = None
    PostgresIntegrityError = Exception


erro_integridade = (sqlite3.IntegrityError, PostgresIntegrityError)


def usando_postgres():
    return bool(os.environ.get("DATABASE_URL"))


class CursorAdaptado:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, parametros=()):
        if usando_postgres():
            sql = sql.replace("?", "%s")
            sql = sql.replace("INSERT OR IGNORE INTO categorias", "INSERT INTO categorias")
            sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")

            if "INSERT INTO categorias" in sql and "ON CONFLICT" not in sql:
                sql = sql.replace("VALUES (%s)", "VALUES (%s) ON CONFLICT (nome) DO NOTHING")

        return self.cursor.execute(sql, parametros)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class ConexaoAdaptada:
    def __init__(self, conexao):
        self.conexao = conexao

    def cursor(self):
        return CursorAdaptado(self.conexao.cursor())

    def commit(self):
        return self.conexao.commit()

    def close(self):
        return self.conexao.close()


def conectar():
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        return ConexaoAdaptada(psycopg2.connect(database_url))

    return ConexaoAdaptada(sqlite3.connect("base.db"))


def criar_banco():
    conexao = conectar()
    cursor = conexao.cursor()

    if usando_postgres():
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
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anotacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT,
                categoria TEXT,
                texto TEXT,
                autor TEXT,
                favorito INTEGER DEFAULT 0,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                senha TEXT NOT NULL,
                perfil TEXT NOT NULL DEFAULT 'usuario'
            )
        """)

        for coluna, tipo in [
            ("autor_id", "INTEGER"),
            ("data_atualizacao", "TEXT"),
            ("visibilidade", "TEXT DEFAULT 'publica'")
        ]:
            try:
                cursor.execute(f"ALTER TABLE anotacoes ADD COLUMN {coluna} {tipo}")
            except sqlite3.OperationalError:
                pass

    conexao.commit()
    conexao.close()