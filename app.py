import json
import random
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request
from flask_socketio import SocketIO, emit, join_room

BASE_DIR = Path(__file__).resolve().parent
INFRACOES_FILE = BASE_DIR / "infracoes" / "infracoes.json"
DATA_DIR = BASE_DIR / "data"
CAIXA_DB = DATA_DIR / "caixa.db"      # registros de vendas, pagamentos e furtos
PLACAS_DB = DATA_DIR / "placas.db"    # placas fotografadas no estacionamento

TIPOS_CAIXA = {"venda", "sem_pagar", "detido"}
FOTOS_POR_SALA = 30
FOTO_MAX_CHARS = 400_000              # ~300 KB de imagem em base64

app = Flask(__name__, template_folder=str(BASE_DIR / "Templates"))
socketio = SocketIO(app, cors_allowed_origins="*")

# Salas em memória: código -> {host, jogadores, estado, fotos}
SALAS = {}
SALA_DO_SID = {}   # sid do socket -> código da sala


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


# ---------- Páginas ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/celular")
def celular():
    return render_template("celular.html")


@app.route("/api/infracoes")
def api_infracoes():
    try:
        with INFRACOES_FILE.open(encoding="utf-8") as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        abort(404)


# ---------- Banco de dados ----------
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


# ---------- Salas (Socket.IO) ----------
def gerar_codigo():
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        cod = "".join(random.choice(alfabeto) for _ in range(5))
        if cod not in SALAS:
            return cod


def lista_jogadores(codigo):
    sala = SALAS.get(codigo)
    if not sala:
        return []
    return [
        {"id": sid, "nome": j["nome"], "papel": j["papel"], "host": sid == sala["host"]}
        for sid, j in sala["jogadores"].items()
    ]


def sala_do_socket():
    cod = SALA_DO_SID.get(request.sid)
    return cod, SALAS.get(cod)


@socketio.on("criar_sala")
def on_criar_sala(dados):
    nome = ((dados or {}).get("nome") or "").strip()[:16]
    if not nome:
        return {"erro": "Digite seu nome."}
    cod = gerar_codigo()
    SALAS[cod] = {
        "host": request.sid,
        "jogadores": {request.sid: {"nome": nome, "papel": "seguranca"}},
        "estado": "lobby",
        "fotos": [],
    }
    SALA_DO_SID[request.sid] = cod
    join_room(cod)
    return {"codigo": cod}


@socketio.on("entrar_sala")
def on_entrar_sala(dados):
    dados = dados or {}
    cod = (dados.get("codigo") or "").strip().upper()
    nome = (dados.get("nome") or "").strip()[:16]
    papel = "celular" if dados.get("papel") == "celular" else "seguranca"
    sala = SALAS.get(cod)
    if not sala:
        return {"erro": "Sala não encontrada."}
    if papel == "seguranca":
        if not nome:
            return {"erro": "Digite seu nome."}
        if sala["estado"] != "lobby":
            return {"erro": "A partida já começou. Só é possível entrar no lobby."}
    sala["jogadores"][request.sid] = {"nome": nome or "Celular", "papel": papel}
    SALA_DO_SID[request.sid] = cod
    join_room(cod)
    emit("jogadores", lista_jogadores(cod), to=cod)
    return {"codigo": cod, "fotos": sala["fotos"][-20:], "estado": sala["estado"]}


@socketio.on("iniciar")
def on_iniciar():
    cod, sala = sala_do_socket()
    if not sala or sala["host"] != request.sid:
        return {"erro": "Só o anfitrião pode iniciar."}
    sala["estado"] = "jogando"
    emit("iniciar", {}, to=cod)
    return {"ok": True}


@socketio.on("disconnect")
def on_disconnect():
    cod = SALA_DO_SID.pop(request.sid, None)
    sala = SALAS.get(cod) if cod else None
    if not sala:
        return
    if sala["host"] == request.sid:
        emit("sala_encerrada", {"motivo": "O anfitrião saiu da sala."}, to=cod)
        for sid in [s for s, c in SALA_DO_SID.items() if c == cod]:
            SALA_DO_SID.pop(sid, None)
        SALAS.pop(cod, None)
        return
    sala["jogadores"].pop(request.sid, None)
    emit("jogadores", lista_jogadores(cod), to=cod)
    emit("saiu", {"id": request.sid}, to=cod)


# Retransmissão para os outros jogadores da sala (quem envia não recebe de volta)
@socketio.on("posicao")
def on_posicao(dados):
    cod, sala = sala_do_socket()
    if sala:
        emit("posicao", {**(dados or {}), "id": request.sid}, to=cod, include_self=False)


@socketio.on("snapshot")
def on_snapshot(dados):
    cod, sala = sala_do_socket()
    if sala and sala["host"] == request.sid:
        emit("snapshot", dados, to=cod, include_self=False)


@socketio.on("evento")
def on_evento(dados):
    cod, sala = sala_do_socket()
    if sala and sala["host"] == request.sid:
        emit("evento", dados, to=cod, include_self=False)


# Ação de um convidado (ex.: abordar cliente) vai só para o anfitrião, que decide
@socketio.on("acao")
def on_acao(dados):
    cod, sala = sala_do_socket()
    if sala:
        emit("acao", {**(dados or {}), "de": request.sid}, to=sala["host"])


@socketio.on("foto")
def on_foto(dados):
    cod, sala = sala_do_socket()
    if not sala:
        return {"erro": "Você não está em uma sala."}
    imagem = (dados or {}).get("imagem") or ""
    if not imagem.startswith("data:image/") or len(imagem) > FOTO_MAX_CHARS:
        return {"erro": "Imagem inválida ou grande demais."}
    foto = {
        "id": uuid.uuid4().hex,
        "de": sala["jogadores"].get(request.sid, {}).get("nome", "?"),
        "legenda": ((dados or {}).get("legenda") or "")[:80],
        "imagem": imagem,
        "hora": datetime.now().strftime("%H:%M:%S"),
    }
    sala["fotos"].append(foto)
    del sala["fotos"][:-FOTOS_POR_SALA]
    emit("foto", foto, to=cod)
    return {"ok": True}


if __name__ == "__main__":
    socketio.run(app, debug=True)
