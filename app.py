from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from banco import conectar, criar_banco, erro_integridade
import os
import uuid
import cloudinary
import cloudinary.uploader

cloudinary.config()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "chave_local_de_desenvolvimento"
)



def login_obrigatorio(funcao):
    @wraps(funcao)
    def verificar_login(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect("/login")
        return funcao(*args, **kwargs)
    return verificar_login


def admin_obrigatorio(funcao):
    @wraps(funcao)
    def verificar_admin(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect("/login")

        if session.get("usuario_perfil") not in ["admin", "admin_geral"]:
            return "Acesso negado. Apenas administradores podem acessar esta área."

        return funcao(*args, **kwargs)
    return verificar_admin


@app.route("/", methods=["GET"])
@login_obrigatorio
def inicio():
    conexao = conectar()
    cursor = conexao.cursor()

    usuario_id = session["usuario_id"]

    cursor.execute("""
        SELECT COUNT(*)
        FROM anotacoes
        WHERE visibilidade = 'publica'
           OR autor_id = ?
    """, (usuario_id,))
    total_notas = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM anotacoes
        WHERE visibilidade = 'publica'
    """)
    total_publicas = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM anotacoes
        WHERE visibilidade = 'privada'
          AND autor_id = ?
    """, (usuario_id,))
    total_privadas = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM anotacoes
        WHERE favorito = 1
          AND (visibilidade = 'publica' OR autor_id = ?)
    """, (usuario_id,))
    total_favoritos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT categoria)
        FROM anotacoes
        WHERE visibilidade = 'publica'
           OR autor_id = ?
    """, (usuario_id,))
    total_categorias = cursor.fetchone()[0]

    cursor.execute("""
        SELECT DISTINCT categoria
        FROM anotacoes
        WHERE visibilidade = 'publica'
           OR autor_id = ?
        ORDER BY categoria
    """, (usuario_id,))
    categorias = cursor.fetchall()

    cursor.execute("""
        SELECT id, titulo, categoria, texto
        FROM anotacoes
        WHERE visibilidade = 'publica'
           OR autor_id = ?
        ORDER BY titulo
    """, (usuario_id,))
    resultados = cursor.fetchall()

    conexao.close()

    return render_template(
        "inicio.html",
        categorias=categorias,
        resultados=resultados,
        termo="",
        total_notas=total_notas,
        total_publicas=total_publicas,
        total_privadas=total_privadas,
        total_favoritos=total_favoritos,
        total_categorias=total_categorias
    )

@app.route("/notas")
@login_obrigatorio
def notas():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT categoria, COUNT(*)
        FROM anotacoes
        WHERE visibilidade = 'publica'
           OR autor_id = ?
        GROUP BY categoria
        ORDER BY categoria
    """, (session["usuario_id"],))

    categorias = cursor.fetchall()
    conexao.close()

    return render_template(
        "notas.html",
        categorias=categorias,
        titulo_pagina="📝 Notas"
    )


@app.route("/notas/publicas")
@login_obrigatorio
def notas_publicas():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT categoria, COUNT(*)
        FROM anotacoes
        WHERE visibilidade = 'publica'
        GROUP BY categoria
        ORDER BY categoria
    """)

    categorias = cursor.fetchall()
    conexao.close()

    return render_template(
        "notas.html",
        categorias=categorias,
        titulo_pagina="🌐 Notas Públicas"
    )


@app.route("/notas/privadas")
@login_obrigatorio
def notas_privadas():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT categoria, COUNT(*)
        FROM anotacoes
        WHERE visibilidade = 'privada'
          AND autor_id = ?
        GROUP BY categoria
        ORDER BY categoria
    """, (session["usuario_id"],))

    categorias = cursor.fetchall()
    conexao.close()

    return render_template(
        "notas.html",
        categorias=categorias,
        titulo_pagina="🔒 Minhas Notas"
    )


@app.route("/categoria/<categoria>")
@login_obrigatorio
def categoria(categoria):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, titulo
        FROM anotacoes
        WHERE categoria = ?
          AND (
              visibilidade = 'publica'
              OR autor_id = ?
          )
        ORDER BY titulo
    """, (categoria, session["usuario_id"]))

    notas = cursor.fetchall()
    conexao.close()

    return render_template("categoria.html", categoria=categoria, notas=notas)


@app.route("/nota/<int:id>")
@login_obrigatorio
def ver_nota(id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT 
            a.id,
            a.titulo,
            a.categoria,
            a.texto,
            a.favorito,
            u.nome,
            a.data_criacao,
            a.data_atualizacao
        FROM anotacoes a
        LEFT JOIN usuarios u ON u.id = a.autor_id
        WHERE a.id = ?
          AND (
              a.visibilidade = 'publica'
              OR a.autor_id = ?
          )
    """, (id, session["usuario_id"]))

    nota = cursor.fetchone()
    conexao.close()

    if nota is None:
        return "Nota não encontrada ou acesso negado."

    return render_template("ver_nota.html", nota=nota)


@app.route("/editar/<int:id>", methods=["GET", "POST"])
@login_obrigatorio
def editar(id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT autor_id
        FROM anotacoes
        WHERE id = ?
    """, (id,))

    dono = cursor.fetchone()

    if dono is None:
        conexao.close()
        return "Nota não encontrada."

    if dono[0] != session["usuario_id"] and session.get("usuario_perfil") not in ["admin", "admin_geral"]:
        conexao.close()
        return "Acesso negado. Você só pode editar suas próprias notas."

    if request.method == "POST":
        titulo = request.form["titulo"]
        categoria = request.form["categoria"]
        texto = request.form.get("texto") or request.form.get("conteudo") or ""
        visibilidade = request.form.get("visibilidade", "publica")

        cursor.execute("""
            UPDATE anotacoes
            SET titulo = ?,
                categoria = ?,
                texto = ?,
                visibilidade = ?,
                data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (titulo, categoria, texto, visibilidade, id))

        conexao.commit()
        conexao.close()

        return redirect(f"/nota/{id}")

    cursor.execute("""
        SELECT id, titulo, categoria, texto, visibilidade
        FROM anotacoes
        WHERE id = ?
    """, (id,))

    nota = cursor.fetchone()

    cursor.execute("""
        SELECT nome
        FROM categorias
        ORDER BY nome
    """)

    categorias = cursor.fetchall()
    conexao.close()

    return render_template("editar.html", nota=nota, categorias=categorias)


@app.route("/excluir/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir(id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        DELETE FROM anotacoes
        WHERE id = ?
          AND (
              autor_id = ?
              OR ? IN ('admin', 'admin_geral')
          )
    """, (id, session["usuario_id"], session.get("usuario_perfil")))

    conexao.commit()
    conexao.close()

    return redirect("/notas")


@app.route("/favoritos")
@login_obrigatorio
def favoritos():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, titulo, categoria
        FROM anotacoes
        WHERE favorito = 1
          AND (
              visibilidade = 'publica'
              OR autor_id = ?
          )
        ORDER BY titulo
    """, (session["usuario_id"],))

    favoritos = cursor.fetchall()
    conexao.close()

    return render_template("favoritos.html", favoritos=favoritos)


@app.route("/favoritar/<int:id>")
@login_obrigatorio
def favoritar(id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE anotacoes
        SET favorito = CASE
            WHEN favorito = 0 THEN 1
            ELSE 0
        END
        WHERE id = ?
          AND (
              visibilidade = 'publica'
              OR autor_id = ?
          )
    """, (id, session["usuario_id"]))

    conexao.commit()
    conexao.close()

    return redirect(f"/nota/{id}")


@app.route("/usuarios")
@admin_obrigatorio
def usuarios():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, nome, email, perfil
        FROM usuarios
        ORDER BY
            CASE perfil
                WHEN 'pendente' THEN 1
                WHEN 'admin' THEN 2
                ELSE 3
            END,
            nome
    """)

    usuarios = cursor.fetchall()
    conexao.close()

    return render_template("usuarios.html", usuarios=usuarios)


@app.route("/aprovar_usuario/<int:id>", methods=["POST"])
@admin_obrigatorio
def aprovar_usuario(id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET perfil = 'usuario'
        WHERE id = ?
    """, (id,))

    conexao.commit()
    conexao.close()

    return redirect("/usuarios")


@app.route("/excluir_usuario/<int:id>", methods=["POST"])
@admin_obrigatorio
def excluir_usuario(id):
    conexao = conectar()
    cursor = conexao.cursor()

    if id == session["usuario_id"]:
        conexao.close()
        return "Você não pode excluir seu próprio usuário."

    cursor.execute("DELETE FROM usuarios WHERE id = ?", (id,))

    conexao.commit()
    conexao.close()

    return redirect("/usuarios")


@app.route("/tornar_admin/<int:id>", methods=["POST"])
@admin_obrigatorio
def tornar_admin(id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE usuarios
        SET perfil = 'admin'
        WHERE id = ?
    """, (id,))

    conexao.commit()
    conexao.close()

    return redirect("/usuarios")


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form["nome"].strip().upper()
        email = request.form["email"].strip().lower()
        senha = request.form["senha"]

        senha_criptografada = generate_password_hash(senha)

        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute("SELECT COUNT(*) FROM usuarios")
        total_usuarios = cursor.fetchone()[0]

        perfil = "admin" if total_usuarios == 0 else "pendente"

        try:
            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha, perfil)
                VALUES (?, ?, ?, ?)
            """, (nome, email, senha_criptografada, perfil))

            conexao.commit()
            conexao.close()

            return redirect("/login")

        except erro_integridade:
            conexao.close()
            return "Este e-mail já está cadastrado."

    return render_template("cadastro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        senha = request.form["senha"]

        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT id, nome, email, senha, perfil
            FROM usuarios
            WHERE email = ?
        """, (email,))

        usuario = cursor.fetchone()
        conexao.close()

        if usuario and check_password_hash(usuario[3], senha):

            if usuario[4] == "pendente":
                return "Seu cadastro ainda está aguardando aprovação do administrador."

            session["usuario_id"] = usuario[0]
            session["usuario_nome"] = usuario[1]
            session["usuario_email"] = usuario[2]
            session["usuario_perfil"] = usuario[4]

            return redirect("/")

        return "E-mail ou senha inválidos."

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/upload_imagem", methods=["POST"])
@login_obrigatorio
def upload_imagem():
    if "upload" not in request.files:
        return jsonify({
            "error": {"message": "Nenhuma imagem enviada."}
        }), 400

    arquivo = request.files["upload"]

    if arquivo.filename == "":
        return jsonify({
            "error": {"message": "Arquivo inválido."}
        }), 400

    extensao = os.path.splitext(arquivo.filename)[1].lower()

    extensoes_permitidas = [".jpg", ".jpeg", ".png", ".gif", ".webp"]

    if extensao not in extensoes_permitidas:
        return jsonify({
            "error": {"message": "Formato de imagem não permitido."}
        }), 400

    try:
        resultado = cloudinary.uploader.upload(
            arquivo,
            folder="sabrinotas/imagens",
            resource_type="image"
        )

        url_imagem = resultado.get("secure_url")

        if not url_imagem:
            return jsonify({
                "error": {"message": "O Cloudinary não retornou a URL da imagem."}
            }), 500

        return jsonify({
            "url": url_imagem
        })

    except Exception as erro:
        print(f"Erro ao enviar imagem ao Cloudinary: {erro}")

        return jsonify({
            "error": {
                "message": "Não foi possível enviar a imagem. Tente novamente."
            }
        }), 500



@app.route("/nova_categoria", methods=["POST"])
@login_obrigatorio
def nova_categoria():
    nome = request.form["categoria"].strip().upper()

    if nome:
        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute(
            "INSERT OR IGNORE INTO categorias (nome) VALUES (?)",
            (nome,)
        )

        conexao.commit()
        conexao.close()

    return redirect("/nova")


@app.route("/categorias")
@login_obrigatorio
def gerenciar_categorias():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT c.id, c.nome, COUNT(a.id)
        FROM categorias c
        LEFT JOIN anotacoes a
            ON a.categoria = c.nome
           AND (
               a.visibilidade = 'publica'
               OR a.autor_id = ?
           )
        GROUP BY c.id, c.nome
        ORDER BY c.nome
    """, (session["usuario_id"],))

    categorias = cursor.fetchall()
    conexao.close()

    return render_template("categorias.html", categorias=categorias)


@app.route("/editar_categoria/<int:id>", methods=["POST"])
@login_obrigatorio
def editar_categoria(id):
    novo_nome = request.form["nome"].strip().upper()

    if novo_nome:
        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute("SELECT nome FROM categorias WHERE id = ?", (id,))
        resultado = cursor.fetchone()

        if resultado:
            categoria_antiga = resultado[0]

            cursor.execute(
                "UPDATE categorias SET nome = ? WHERE id = ?",
                (novo_nome, id)
            )

            cursor.execute(
                "UPDATE anotacoes SET categoria = ? WHERE categoria = ?",
                (novo_nome, categoria_antiga)
            )

            conexao.commit()

        conexao.close()

    return redirect("/categorias")


@app.route("/excluir_categoria/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir_categoria(id):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("SELECT nome FROM categorias WHERE id = ?", (id,))
    resultado = cursor.fetchone()

    if resultado:
        categoria = resultado[0]

        cursor.execute(
            "SELECT COUNT(*) FROM anotacoes WHERE categoria = ?",
            (categoria,)
        )

        total_notas = cursor.fetchone()[0]

        if total_notas == 0:
            cursor.execute("DELETE FROM categorias WHERE id = ?", (id,))
            conexao.commit()

    conexao.close()

    return redirect("/categorias")


@app.route("/buscar")
@login_obrigatorio
def buscar():
    termo = request.args.get("q", "")

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, titulo, categoria, texto
        FROM anotacoes
        WHERE (
            titulo LIKE ?
            OR categoria LIKE ?
            OR texto LIKE ?
        )
        AND (
            visibilidade = 'publica'
            OR autor_id = ?
        )
        ORDER BY titulo
        LIMIT 20
    """, (
        f"%{termo}%",
        f"%{termo}%",
        f"%{termo}%",
        session["usuario_id"]
    ))

    resultados = cursor.fetchall()
    conexao.close()

    return jsonify(resultados)


@app.route("/nova", methods=["GET", "POST"])
@login_obrigatorio
def nova():

    conexao = conectar()
    cursor = conexao.cursor()

    if request.method == "POST":

        titulo = request.form["titulo"]

        categoria = request.form["categoria"]
        nova_categoria = request.form.get("nova_categoria", "").strip()

        if categoria == "__nova__":
            categoria = nova_categoria

            if categoria:

                cursor.execute("""
                    SELECT id
                    FROM categorias
                    WHERE nome = ?
                """, (categoria,))

                existe = cursor.fetchone()

                if not existe:

                    cursor.execute("""
                        INSERT INTO categorias(nome)
                        VALUES (?)
                    """, (categoria,))

        texto = request.form["conteudo"]
        visibilidade = request.form["visibilidade"]
        autor_id = session["usuario_id"]

        cursor.execute("""
            INSERT INTO anotacoes (
                titulo,
                categoria,
                texto,
                autor_id,
                visibilidade,
                data_criacao,
                data_atualizacao
            )
            VALUES (
                ?, ?, ?, ?, ?,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
        """, (
            titulo,
            categoria,
            texto,
            autor_id,
            visibilidade
        ))

        conexao.commit()
        conexao.close()

        return redirect("/")

    cursor.execute("""
        SELECT nome
        FROM categorias
        ORDER BY nome
    """)

    categorias = cursor.fetchall()

    conexao.close()

    return render_template(
        "nova.html",
        categorias=categorias
    )

@app.route("/redefinir_senha/<int:id>", methods=["GET", "POST"])
@login_obrigatorio
def redefinir_senha(id):

    if session.get("usuario_perfil") != "admin":
        return "Acesso negado."

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, nome, email
        FROM usuarios
        WHERE id = ?
    """, (id,))

    usuario = cursor.fetchone()

    if not usuario:
        conexao.close()
        return "Usuário não encontrado."

    if request.method == "POST":
        nova_senha = request.form["nova_senha"]
        confirmar_senha = request.form["confirmar_senha"]

        if nova_senha != confirmar_senha:
            conexao.close()
            return "As senhas não conferem."

        senha_criptografada = generate_password_hash(nova_senha)

        cursor.execute("""
            UPDATE usuarios
            SET senha = ?
            WHERE id = ?
        """, (senha_criptografada, id))

        conexao.commit()
        conexao.close()

        return redirect("/usuarios")

    conexao.close()

    return render_template("redefinir_senha.html", usuario=usuario)

@app.route("/meu_perfil", methods=["GET", "POST"])
@login_obrigatorio
def meu_perfil():
    mensagem = ""

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, nome, email
        FROM usuarios
        WHERE id = ?
    """, (session["usuario_id"],))

    usuario = cursor.fetchone()

    if request.method == "POST":
        senha_atual = request.form["senha_atual"]
        nova_senha = request.form["nova_senha"]
        confirmar_senha = request.form["confirmar_senha"]

        cursor.execute("""
            SELECT senha
            FROM usuarios
            WHERE id = ?
        """, (session["usuario_id"],))

        senha_banco = cursor.fetchone()[0]

        if not check_password_hash(senha_banco, senha_atual):
            mensagem = "Senha atual incorreta."

        elif nova_senha != confirmar_senha:
            mensagem = "A nova senha e a confirmação não conferem."

        else:
            senha_criptografada = generate_password_hash(nova_senha)

            cursor.execute("""
                UPDATE usuarios
                SET senha = ?
                WHERE id = ?
            """, (senha_criptografada, session["usuario_id"]))

            conexao.commit()
            mensagem = "Senha alterada com sucesso."

    conexao.close()

    return render_template("meu_perfil.html", usuario=usuario, mensagem=mensagem)

criar_banco()

if __name__ == "__main__":
    app.run(debug=True)