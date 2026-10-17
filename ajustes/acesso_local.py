# -*- coding: utf-8 -*-
"""
Nous sem tela de login: abre direto no chat, como qualquer programa do PC.

O Nous so' escuta em 127.0.0.1 (ninguem da rede chega nele), entao a senha so'
protegia contra quem ja' esta' no seu Windows - e isso a senha do Windows faz.
Esquecer a senha do Nous, por outro lado, travava o leigo fora das conversas.

O Open WebUI 0.9.6 desliga o login com WEBUI_AUTH=False, mas so' aceita isso se
a unica conta for a fixa admin@localhost (senha "admin"); com qualquer outra
conta ele recusa ("existing users"). Por isso este script decide o modo a cada
inicio e, com UMA conta, converte essa conta na fixa - mesmo id, entao conversas,
memorias, documentos e configuracoes continuam todos la'. O email e o hash da
senha originais ficam em NousData/.conta_original.json para desfazer.

  0 contas            -> sem login (o Open WebUI cria a conta no 1o acesso)
  1 conta             -> sem login (converte a conta, uma vez)
  2+ contas (familia) -> com login: ai' ele separa as conversas de cada pessoa;
                         a conta convertida volta ao email/senha de antes
  NousData/.exigir_login existe -> com login (e desfaz a conversao)

Imprime "sem-login" ou "com-login". Qualquer erro = "com-login": ligar
WEBUI_AUTH=False com a conta errada trancaria o usuario fora.

USO:
    python ajustes/acesso_local.py [--data-dir <DATA_DIR>]
    python ajustes/acesso_local.py --nome [--data-dir <DATA_DIR>]
        (servidor ja' no ar: troca o nome "User" da conta criada pelo Open WebUI
         pelo nome do Windows, para a tela inicial dizer "Boa tarde, Fulano")
"""
import os
import sys
import json
import time
import argparse
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "evaluation"))
from register_arena import _resolve_db  # noqa: E402

FIXA = "admin@localhost"
SENHA_FIXA = "admin"
ORIGINAL = ".conta_original.json"
EXIGIR = ".exigir_login"


def _hash(senha):
    import bcrypt
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _contas(cx):
    return cx.execute("SELECT u.id, u.email, a.password FROM user u "
                      "LEFT JOIN auth a ON a.id = u.id").fetchall()


def _trocar(cx, uid, email, senha_hash):
    cx.execute("UPDATE user SET email = ?, updated_at = ? WHERE id = ?", (email, int(time.time()), uid))
    cx.execute("UPDATE auth SET email = ?, password = ? WHERE id = ?", (email, senha_hash, uid))


def converter(cx, data_dir, conta):
    uid, email, senha = conta
    if email.lower() == FIXA:
        return
    with open(os.path.join(data_dir, ORIGINAL), "w", encoding="utf-8") as f:
        json.dump({"id": uid, "email": email, "password": senha}, f)
    _trocar(cx, uid, FIXA, _hash(SENHA_FIXA))


def desfazer(cx, data_dir):
    """Volta a conta convertida ao email/senha de antes (se ainda der)."""
    caminho = os.path.join(data_dir, ORIGINAL)
    if not os.path.isfile(caminho):
        return
    with open(caminho, encoding="utf-8") as f:
        orig = json.load(f)
    row = cx.execute("SELECT email FROM user WHERE id = ?", (orig["id"],)).fetchone()
    ocupado = cx.execute("SELECT 1 FROM user WHERE lower(email) = lower(?) AND id != ?",
                         (orig["email"], orig["id"])).fetchone()
    if row and row[0].lower() == FIXA and not ocupado:
        _trocar(cx, orig["id"], orig["email"], orig["password"])
    os.remove(caminho)


def decidir(db, data_dir):
    cx = sqlite3.connect(db, timeout=10)
    try:
        with cx:
            contas = _contas(cx)
            if os.path.exists(os.path.join(data_dir, EXIGIR)) or len(contas) > 1:
                desfazer(cx, data_dir)
                return "com-login"
            if contas:
                converter(cx, data_dir, contas[0])
            return "sem-login"
    finally:
        cx.close()


def nome_do_windows():
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        tam = ctypes.c_ulong(256)
        if ctypes.windll.secur32.GetUserNameExW(3, buf, ctypes.byref(tam)) and buf.value.strip():
            nome = buf.value.strip()  # 3 = NameDisplay ("Nome Sobrenome")
            return nome[:1].upper() + nome[1:]
    except Exception:
        pass
    nome = os.environ.get("USERNAME", "").strip()
    return nome[:1].upper() + nome[1:] if nome else ""


def ajustar_nome(db):
    cx = sqlite3.connect(db, timeout=10)
    try:
        with cx:
            contas = cx.execute("SELECT id, email, name FROM user").fetchall()
            if len(contas) == 1 and contas[0][1].lower() == FIXA and contas[0][2] == "User":
                nome = nome_do_windows()
                if nome:
                    cx.execute("UPDATE user SET name = ? WHERE id = ?", (nome, contas[0][0]))
    finally:
        cx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir")
    ap.add_argument("--nome", action="store_true")
    args = ap.parse_args()
    try:
        db = _resolve_db(args.data_dir)
        if not db or not os.path.isfile(db):
            # instalacao nova: o Open WebUI cria o banco e a conta fixa sozinho
            if not args.nome:
                print("sem-login")
            return
        if args.nome:
            ajustar_nome(db)
            return
        print(decidir(db, os.path.dirname(db)))
    except Exception as e:
        print(f"com-login  # {e}", file=sys.stderr)
        print("com-login")


if __name__ == "__main__":
    main()
