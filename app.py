import json
from pathlib import Path

from flask import Flask, abort, jsonify, render_template

BASE_DIR = Path(__file__).resolve().parent
INFRACOES_FILE = BASE_DIR / "infracoes" / "infracoes.json"

app = Flask(__name__, template_folder=str(BASE_DIR / "Templates"))


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


if __name__ == "__main__":
    app.run(debug=True)
