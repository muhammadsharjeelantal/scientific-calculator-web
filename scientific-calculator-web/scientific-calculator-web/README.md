# Scientific Calculator (Flask + JavaScript)

A full-stack scientific calculator.

- **Backend:** Python / Flask. A safe expression evaluator (no `eval`), a JSON API and SQLite history.
- **Frontend:** plain HTML, CSS and JavaScript (no build step). It has a keypad, keyboard input, DEG/RAD mode, memory keys, a history panel, a function reference and light/dark themes.

## Run it

```bash
pip install -r requirements.txt
cd backend
python app.py
```

Then open <http://127.0.0.1:5000>.

Optional environment variables: `PORT` (default 5000), `HOST` (default 127.0.0.1), `CALC_DB` (SQLite file path), `FLASK_DEBUG=1`.

For production, use a WSGI server, for example `pip install gunicorn` and then `cd backend && gunicorn -w 2 app:app`.

## Project layout

```
backend/
  app.py        Flask app and API routes
  engine.py     calculation engine (parser, functions, constants, formatting)
frontend/
  index.html  style.css  script.js
tests/
  test_api.py   API tests (python -m unittest discover -s tests)
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Liveness check |
| POST | `/api/calculate` | Body: `{"expression": "sin(30)", "angle_mode": "DEG", "ans": 0, "memory": 0}`. Returns `{expression, formatted, value, angle_mode}`. Calculation errors return HTTP 422 with `{"error": "..."}` |
| GET | `/api/history?limit=50` | History for the client named in the `X-Client-Id` header (newest first) |
| DELETE | `/api/history` | Clear that client's history |
| GET | `/api/functions` | Reference of all functions and constants |

Example:

```bash
curl -X POST localhost:5000/api/calculate \
  -H 'Content-Type: application/json' \
  -d '{"expression": "ncr(10,3) + sqrt(16)"}'
```

## Supported math

- **Operators:** `+ - * / // % ^ **`, parentheses, factorial `5!`, and implicit multiplication (`2pi`, `3(4+1)`).
- **Trig (DEG/RAD):** `sin cos tan asin acos atan atan2 sec csc cot`.
- **Hyperbolic:** `sinh cosh tanh asinh acosh atanh`.
- **Logs and roots:** `log ln log2 logb exp pow sqrt cbrt root`.
- **Other:** `abs floor ceil round trunc sign mod hypot degrees radians min max sum factorial npr ncr gcd lcm`.
- **Constants:** `pi e tau phi ans mem`.

## Notes

- History is stored per browser, using a random id kept in `localStorage`. There are no accounts.
- Limits: expressions up to 500 characters, factorial arguments up to 1000, exponents up to 10000.
