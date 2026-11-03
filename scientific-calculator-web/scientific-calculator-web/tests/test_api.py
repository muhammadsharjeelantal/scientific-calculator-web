import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import create_app  # noqa: E402


class ApiTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app(self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.db_path)

    def calc(self, expression, client_id="tester", **extra):
        body = {"expression": expression, **extra}
        return self.client.post("/api/calculate", json=body,
                                headers={"X-Client-Id": client_id})

    # ---- basics ----
    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")

    def test_index_and_static(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        for f in ("style.css", "script.js"):
            r = self.client.get(f"/static/{f}")
            self.assertEqual(r.status_code, 200, f)
            r.close()

    def test_arithmetic(self):
        r = self.calc("2+3*4")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["formatted"], "14")
        self.assertEqual(data["value"], 14)

    def test_angle_modes(self):
        self.assertEqual(self.calc("sin(30)").get_json()["formatted"], "0.5")
        rad = self.calc("sin(pi/2)", angle_mode="RAD").get_json()
        self.assertEqual(rad["formatted"], "1")

    def test_functions(self):
        cases = {
            "5!": "120", "ncr(10,3)": "120", "npr(5,2)": "20", "gcd(12,18)": "6",
            "log(1000)": "3", "log2(8)": "3", "sqrt(16)": "4", "2^10": "1024",
            "cbrt(-27)": "-3", "atan2(1,1)": "45", "2pi": "6.28318530718",
        }
        for expr, expected in cases.items():
            r = self.calc(expr)
            self.assertEqual(r.status_code, 200, expr)
            self.assertEqual(r.get_json()["formatted"], expected, expr)

    def test_ans_and_memory(self):
        self.assertEqual(self.calc("ans*2", ans=21).get_json()["formatted"], "42")
        self.assertEqual(self.calc("mem+1", memory=9).get_json()["formatted"], "10")

    def test_huge_factorial_does_not_crash(self):
        r = self.calc("1000!")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("e+2567", data["formatted"])
        self.assertIsNone(data["value"])

    # ---- errors ----
    def test_calculation_errors(self):
        for expr in ["1/0", "sqrt(-1)", "foo(2)", "2+", "__import__('os')",
                     "(-1)!", "9**99999", "1001!"]:
            r = self.calc(expr)
            self.assertEqual(r.status_code, 422, expr)
            self.assertIn("error", r.get_json())

    def test_validation(self):
        self.assertEqual(self.calc("").status_code, 400)
        self.assertEqual(self.calc("1+" * 300).status_code, 400)
        self.assertEqual(self.calc("1", angle_mode="GRAD").status_code, 400)
        self.assertEqual(self.calc("1", ans="abc").status_code, 400)
        r = self.client.post("/api/calculate", data="not json",
                             content_type="text/plain")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/calculate", json=[1, 2])
        self.assertEqual(r.status_code, 400)

    def test_unknown_routes_and_methods(self):
        self.assertEqual(self.client.get("/api/nope").status_code, 404)
        self.assertEqual(self.client.get("/api/calculate").status_code, 405)

    # ---- history ----
    def test_history_per_client_and_clear(self):
        self.calc("1+1", client_id="alice")
        self.calc("2+2", client_id="alice")
        self.calc("3+3", client_id="bob")
        self.calc("1/0", client_id="alice")  # failures are not stored

        h = self.client.get("/api/history", headers={"X-Client-Id": "alice"}).get_json()
        self.assertEqual([i["expression"] for i in h["history"]], ["2+2", "1+1"])
        self.assertEqual(h["history"][0]["result"], "4")

        b = self.client.get("/api/history", headers={"X-Client-Id": "bob"}).get_json()
        self.assertEqual(len(b["history"]), 1)

        r = self.client.delete("/api/history", headers={"X-Client-Id": "alice"})
        self.assertEqual(r.status_code, 200)
        h = self.client.get("/api/history", headers={"X-Client-Id": "alice"}).get_json()
        self.assertEqual(h["history"], [])
        b = self.client.get("/api/history", headers={"X-Client-Id": "bob"}).get_json()
        self.assertEqual(len(b["history"]), 1)

    def test_history_limit_validation(self):
        self.assertEqual(self.client.get("/api/history?limit=abc").status_code, 400)
        self.assertEqual(self.client.get("/api/history?limit=5").status_code, 200)

    def test_functions_reference(self):
        data = self.client.get("/api/functions").get_json()
        names = {i["name"] for g in data["groups"] for i in g["items"]}
        for expected in ("sin", "log", "ncr", "factorial", "pi"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()
