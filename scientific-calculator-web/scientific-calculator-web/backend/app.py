"""
Scientific Calculator - Flask backend
=====================================

Endpoints
---------
GET    /                  the web app
GET    /api/health        liveness check
POST   /api/calculate     {expression, angle_mode?, ans?, memory?} -> result
GET    /api/history       calculation history for this client (X-Client-Id header)
DELETE /api/history       clear this client's history
GET    /api/functions     reference of supported functions and constants

Run:  python app.py        (or: flask --app app run)
"""

import math
import os
import re
import sqlite3
import time
from contextlib import closing

from flask import Flask, g, jsonify, request, send_from_directory

from engine import CalcError, Calculator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))
MAX_EXPRESSION_LENGTH = 500
MAX_HISTORY_RETURNED = 100
MAX_HISTORY_STORED = 500  # per client

FUNCTION_REFERENCE = [
    {"name": "Trigonometry (uses DEG/RAD mode)", "items": [
        {"name": "sin", "sig": "sin(x)", "desc": "Sine"},
        {"name": "cos", "sig": "cos(x)", "desc": "Cosine"},
        {"name": "tan", "sig": "tan(x)", "desc": "Tangent"},
        {"name": "asin", "sig": "asin(x)", "desc": "Inverse sine"},
        {"name": "acos", "sig": "acos(x)", "desc": "Inverse cosine"},
        {"name": "atan", "sig": "atan(x)", "desc": "Inverse tangent"},
        {"name": "atan2", "sig": "atan2(y, x)", "desc": "Angle of the point (x, y)"},
        {"name": "sec", "sig": "sec(x)", "desc": "Secant"},
        {"name": "csc", "sig": "csc(x)", "desc": "Cosecant"},
        {"name": "cot", "sig": "cot(x)", "desc": "Cotangent"},
    ]},
    {"name": "Hyperbolic", "items": [
        {"name": "sinh", "sig": "sinh(x)", "desc": "Hyperbolic sine"},
        {"name": "cosh", "sig": "cosh(x)", "desc": "Hyperbolic cosine"},
        {"name": "tanh", "sig": "tanh(x)", "desc": "Hyperbolic tangent"},
        {"name": "asinh", "sig": "asinh(x)", "desc": "Inverse hyperbolic sine"},
        {"name": "acosh", "sig": "acosh(x)", "desc": "Inverse hyperbolic cosine"},
        {"name": "atanh", "sig": "atanh(x)", "desc": "Inverse hyperbolic tangent"},
    ]},
    {"name": "Logarithms, powers and roots", "items": [
        {"name": "log", "sig": "log(x)", "desc": "Base-10 logarithm"},
        {"name": "ln", "sig": "ln(x)", "desc": "Natural logarithm"},
        {"name": "log2", "sig": "log2(x)", "desc": "Base-2 logarithm"},
        {"name": "logb", "sig": "logb(x, b)", "desc": "Logarithm of x in base b"},
        {"name": "exp", "sig": "exp(x)", "desc": "e raised to x"},
        {"name": "pow", "sig": "pow(x, y)", "desc": "x raised to y (also x^y)"},
        {"name": "sqrt", "sig": "sqrt(x)", "desc": "Square root"},
        {"name": "cbrt", "sig": "cbrt(x)", "desc": "Cube root"},
        {"name": "root", "sig": "root(x, n)", "desc": "n-th root of x"},
    ]},
    {"name": "Rounding and miscellaneous", "items": [
        {"name": "abs", "sig": "abs(x)", "desc": "Absolute value"},
        {"name": "floor", "sig": "floor(x)", "desc": "Round down"},
        {"name": "ceil", "sig": "ceil(x)", "desc": "Round up"},
        {"name": "round", "sig": "round(x[, digits])", "desc": "Round to nearest"},
        {"name": "trunc", "sig": "trunc(x)", "desc": "Drop the fractional part"},
        {"name": "sign", "sig": "sign(x)", "desc": "-1, 0 or 1"},
        {"name": "mod", "sig": "mod(x, y)", "desc": "Remainder of x / y"},
        {"name": "hypot", "sig": "hypot(x, y)", "desc": "sqrt(x^2 + y^2)"},
        {"name": "degrees", "sig": "degrees(x)", "desc": "Radians to degrees"},
        {"name": "radians", "sig": "radians(x)", "desc": "Degrees to radians"},
        {"name": "min", "sig": "min(a, b, ...)", "desc": "Smallest value"},
        {"name": "max", "sig": "max(a, b, ...)", "desc": "Largest value"},
        {"name": "sum", "sig": "sum(a, b, ...)", "desc": "Sum of values"},
    ]},
    {"name": "Combinatorics and number theory", "items": [
        {"name": "factorial", "sig": "factorial(n)  or  n!", "desc": "n factorial"},
        {"name": "npr", "sig": "npr(n, r)", "desc": "Permutations"},
        {"name": "ncr", "sig": "ncr(n, r)", "desc": "Combinations"},
        {"name": "gcd", "sig": "gcd(a, b, ...)", "desc": "Greatest common divisor"},
        {"name": "lcm", "sig": "lcm(a, b, ...)", "desc": "Least common multiple"},
    ]},
    {"name": "Constants", "items": [
        {"name": "pi", "sig": "pi", "desc": "3.14159..."},
        {"name": "e", "sig": "e", "desc": "2.71828..."},
        {"name": "tau", "sig": "tau", "desc": "2 * pi"},
        {"name": "phi", "sig": "phi", "desc": "Golden ratio"},
        {"name": "ans", "sig": "ans", "desc": "Previous result"},
        {"name": "mem", "sig": "mem", "desc": "Value stored in memory"},
    ]},
]


def create_app(db_path=None):
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="/static")
    app.config["DB_PATH"] = db_path or os.environ.get(
        "CALC_DB", os.path.join(BASE_DIR, "history.db"))
    app.config["JSON_SORT_KEYS"] = False

    # ---------------- database ----------------
    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DB_PATH"])
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        with closing(sqlite3.connect(app.config["DB_PATH"])) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS history (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       client_id TEXT NOT NULL,
                       expression TEXT NOT NULL,
                       result TEXT NOT NULL,
                       angle_mode TEXT NOT NULL,
                       created_at REAL NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_history_client "
                       "ON history (client_id, id)")
            db.commit()

    init_db()

    def client_id():
        raw = request.headers.get("X-Client-Id", "")
        cleaned = re.sub(r"[^A-Za-z0-9_-]", "", raw)[:64]
        return cleaned or "anonymous"

    def error(message, status):
        return jsonify({"error": message}), status

    # ---------------- pages ----------------
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    # ---------------- API ----------------
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/functions")
    def functions():
        return jsonify({"groups": FUNCTION_REFERENCE})

    @app.post("/api/calculate")
    def calculate():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Request body must be a JSON object.", 400)

        expression = data.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            return error("Please enter an expression.", 400)
        if len(expression) > MAX_EXPRESSION_LENGTH:
            return error(f"Expression is too long (max {MAX_EXPRESSION_LENGTH} characters).", 400)

        mode = str(data.get("angle_mode", "DEG")).upper()
        if mode not in ("DEG", "RAD"):
            return error("angle_mode must be DEG or RAD.", 400)

        calc = Calculator()
        calc.angle_mode = mode
        try:
            calc.ans = float(data.get("ans", 0) or 0)
            calc.memory = float(data.get("memory", 0) or 0)
        except (TypeError, ValueError):
            return error("ans and memory must be numbers.", 400)
        if not (math.isfinite(calc.ans) and math.isfinite(calc.memory)):
            return error("ans and memory must be finite numbers.", 400)

        try:
            result = calc.evaluate(expression)
        except CalcError as exc:
            return error(str(exc), 422)

        formatted = calc.fmt(result)
        try:
            value = float(result)
            if not math.isfinite(value):
                value = None
        except OverflowError:
            value = None

        db = get_db()
        cid = client_id()
        db.execute(
            "INSERT INTO history (client_id, expression, result, angle_mode, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (cid, expression.strip(), formatted, mode, time.time()))
        # keep only the newest MAX_HISTORY_STORED rows for this client
        db.execute(
            "DELETE FROM history WHERE client_id = ? AND id NOT IN "
            "(SELECT id FROM history WHERE client_id = ? ORDER BY id DESC LIMIT ?)",
            (cid, cid, MAX_HISTORY_STORED))
        db.commit()

        return jsonify({
            "expression": expression.strip(),
            "formatted": formatted,
            "value": value,
            "angle_mode": mode,
        })

    @app.get("/api/history")
    def history_list():
        try:
            limit = int(request.args.get("limit", 50))
        except ValueError:
            return error("limit must be an integer.", 400)
        limit = max(1, min(limit, MAX_HISTORY_RETURNED))
        rows = get_db().execute(
            "SELECT id, expression, result, angle_mode, created_at FROM history "
            "WHERE client_id = ? ORDER BY id DESC LIMIT ?",
            (client_id(), limit)).fetchall()
        return jsonify({"history": [dict(r) for r in rows]})

    @app.delete("/api/history")
    def history_clear():
        db = get_db()
        db.execute("DELETE FROM history WHERE client_id = ?", (client_id(),))
        db.commit()
        return jsonify({"status": "cleared"})

    # ---------------- error handlers ----------------
    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return error("Not found.", 404)
        return error("Page not found.", 404)

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return error("Method not allowed.", 405)

    @app.errorhandler(500)
    def server_error(_e):
        return error("Internal server error.", 500)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port,
            debug=os.environ.get("FLASK_DEBUG") == "1")
