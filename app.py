import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
INFRACOES_FILE = BASE_DIR / "infracoes" / "infracoes.json"
DATA_DIR = BASE_DIR / "data"
CAIXA_DB = DATA_DIR / "caixa.db"      # registros de vendas, pagamentos e furtos
PLACAS_DB = DATA_DIR / "placas.db"    # placas fotografadas no estacionamento

TIPOS_CAIXA = {"venda", "sem_pagar", "detido"}

app = Flask(__name__, template_folder=str(BASE_DIR / "Templates"))


def db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return closing(conn)


def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    with db(CAIXA_DB) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS registros_caixa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sessao TEXT,
                criado_em TEXT NOT NULL,
                tipo TEXT NOT NULL,
                cliente_id INTEGER,
                itens INTEGER,
                total REAL,
                forma_pagamento TEXT,
                observacao TEXT
            )"""
        )
        conn.commit()
    with db(PLACAS_DB) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS placas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sessao TEXT,
                placa TEXT NOT NULL,
                capturada_em TEXT NOT NULL
            )"""
        )
        conn.commit()


init_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/infracoes")
def api_infracoes():
    try:
        with INFRACOES_FILE.open(encoding="utf-8") as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        abort(404)


@app.route("/api/caixa", methods=["POST"])
def criar_registro_caixa():
    dados = request.get_json(silent=True) or {}
    tipo = dados.get("tipo")
    if tipo not in TIPOS_CAIXA:
        return jsonify({"erro": "tipo deve ser venda, sem_pagar ou detido"}), 400
    agora = datetime.now().isoformat(timespec="seconds")
    with db(CAIXA_DB) as conn:
        cur = conn.execute(
            """INSERT INTO registros_caixa
               (sessao, criado_em, tipo, cliente_id, itens, total, forma_pagamento, observacao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dados.get("sessao"), agora, tipo, dados.get("cliente_id"),
                dados.get("itens"), dados.get("total"),
                dados.get("forma_pagamento"), dados.get("observacao"),
            ),
        )
        conn.commit()
        return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/caixa", methods=["GET"])
def listar_registros_caixa():
    limite = min(request.args.get("limite", 100, type=int), 1000)
    with db(CAIXA_DB) as conn:
        rows = conn.execute(
            "SELECT * FROM registros_caixa ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/placas", methods=["POST"])
def registrar_placa():
    dados = request.get_json(silent=True) or {}
    placa = (dados.get("placa") or "").strip().upper()
    if not placa or len(placa) > 10:
        return jsonify({"erro": "placa inválida"}), 400
    agora = dados.get("capturada_em") or datetime.now().isoformat(timespec="seconds")
    with db(PLACAS_DB) as conn:
        cur = conn.execute(
            "INSERT INTO placas (sessao, placa, capturada_em) VALUES (?, ?, ?)",
            (dados.get("sessao"), placa, agora),
        )
        conn.commit()
        return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/placas", methods=["GET"])
def listar_placas():
    limite = min(request.args.get("limite", 100, type=int), 1000)
    with db(PLACAS_DB) as conn:
        rows = conn.execute(
            "SELECT * FROM placas ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(debug=True)
