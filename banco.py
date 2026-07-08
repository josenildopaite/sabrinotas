import sqlite3


def conectar():
    return sqlite3.connect("base.db")


def criar_banco():
    conexao = conectar()
    cursor = conexao.cursor()

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

    cursor.execute("""
        INSERT OR IGNORE INTO categorias (nome)
        SELECT DISTINCT categoria
        FROM anotacoes
        WHERE categoria IS NOT NULL AND categoria != ''
    """)

    conexao.commit()
    conexao.close()