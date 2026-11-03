#!/usr/bin/env python3
"""
Scientific Calculator
=====================
Calculation engine used by the web backend.

Features
--------
* + - * / // % ** (and ^ for power), parentheses, factorial with !
* Trig (sin cos tan asin acos atan) with DEG / RAD mode
* Hyperbolic (sinh cosh tanh asinh acosh atanh)
* log (base 10), ln, log2, logb(x, base), exp, sqrt, cbrt, root(x, n)
* abs, floor, ceil, round, factorial, nPr, nCr, gcd, lcm, mod, pow
* degrees(), radians(), sign(), hypot()
* Constants: pi, e, tau, phi (golden ratio)
* ans (last result), memory (M+, M-, MR, MC)
* Safe evaluation: no eval() of arbitrary code (uses the ast module)
"""

import ast
import math
import operator
import re
import sys

# --------------------------------------------------------------------------
# Calculation engine
# --------------------------------------------------------------------------


class CalcError(Exception):
    """Raised for any user-facing calculation error."""


class Calculator:
    def __init__(self):
        self.angle_mode = "DEG"  # "DEG" or "RAD"
        self.ans = 0.0
        self.memory = 0.0
        self.history = []

    # ----- angle helpers -------------------------------------------------
    def _to_rad(self, x):
        return math.radians(x) if self.angle_mode == "DEG" else x

    def _from_rad(self, x):
        return math.degrees(x) if self.angle_mode == "DEG" else x

    # ----- function table ------------------------------------------------
    def _functions(self):
        def fact(n):
            if n != int(n) or n < 0:
                raise CalcError("factorial needs a non-negative integer")
            if n > 1000:
                raise CalcError("factorial argument too large")
            return math.factorial(int(n))

        def npr(n, r):
            self._check_int(n, r)
            return math.perm(int(n), int(r))

        def ncr(n, r):
            self._check_int(n, r)
            return math.comb(int(n), int(r))

        def gcd(*a):
            self._check_int(*a)
            return math.gcd(*[int(x) for x in a])

        def lcm(*a):
            self._check_int(*a)
            return math.lcm(*[int(x) for x in a])

        def root(x, n):
            if n == 0:
                raise CalcError("root degree cannot be 0")
            if x < 0:
                if int(n) == n and int(n) % 2 == 1:
                    return -((-x) ** (1 / n))
                raise CalcError("even root of a negative number")
            return x ** (1 / n)

        def cbrt(x):
            return math.copysign(abs(x) ** (1 / 3), x)

        def sign(x):
            return (x > 0) - (x < 0)

        return {
            # trig
            "sin": lambda x: math.sin(self._to_rad(x)),
            "cos": lambda x: math.cos(self._to_rad(x)),
            "tan": lambda x: math.tan(self._to_rad(x)),
            "asin": lambda x: self._from_rad(math.asin(x)),
            "acos": lambda x: self._from_rad(math.acos(x)),
            "atan": lambda x: self._from_rad(math.atan(x)),
            "atan2": lambda y, x: self._from_rad(math.atan2(y, x)),
            "sec": lambda x: 1 / math.cos(self._to_rad(x)),
            "csc": lambda x: 1 / math.sin(self._to_rad(x)),
            "cot": lambda x: 1 / math.tan(self._to_rad(x)),
            # hyperbolic
            "sinh": math.sinh,
            "cosh": math.cosh,
            "tanh": math.tanh,
            "asinh": math.asinh,
            "acosh": math.acosh,
            "atanh": math.atanh,
            # logs / exponents / roots
            "log": math.log10,
            "log10": math.log10,
            "ln": math.log,
            "log2": math.log2,
            "logb": lambda x, b: math.log(x, b),
            "exp": math.exp,
            "sqrt": math.sqrt,
            "cbrt": cbrt,
            "root": root,
            "pow": math.pow,
            # rounding / misc
            "abs": abs,
            "floor": math.floor,
            "ceil": math.ceil,
            "round": round,
            "trunc": math.trunc,
            "sign": sign,
            "mod": math.fmod,
            "hypot": math.hypot,
            "degrees": math.degrees,
            "radians": math.radians,
            # combinatorics / number theory
            "factorial": fact,
            "fact": fact,
            "npr": npr,
            "ncr": ncr,
            "gcd": gcd,
            "lcm": lcm,
            "min": min,
            "max": max,
            "sum": lambda *a: sum(a),
        }

    @staticmethod
    def _check_int(*vals):
        for v in vals:
            if v != int(v) or v < 0:
                raise CalcError("arguments must be non-negative integers")

    def _constants(self):
        return {
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
            "phi": (1 + math.sqrt(5)) / 2,
            "ans": self.ans,
            "mem": self.memory,
        }

    # ----- parsing -------------------------------------------------------
    _BIN = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    @staticmethod
    def _preprocess(expr):
        s = expr.strip()
        s = (s.replace("×", "*").replace("÷", "/").replace("−", "-")
              .replace("π", "pi").replace("√", "sqrt").replace("^", "**"))
        # factorial postfix:  5!  ->  factorial(5);  (2+3)! handled below
        s = re.sub(r"(\d+(?:\.\d+)?)!", r"factorial(\1)", s)
        # simple parenthesised group factorial, e.g. (2+3)!
        while True:
            m = re.search(r"\(([^()]*)\)!", s)
            if not m:
                break
            s = s[:m.start()] + "factorial(" + m.group(1) + ")" + s[m.end():]
        # implicit multiplication:  2pi, 3(4+1), 2sin(30), )(
        # (numbers that are part of a name, like log10 / log2 / atan2, are skipped)
        s = re.sub(r"(?<![A-Za-z_\d.])(\d+(?:\.\d+)?)\s*([A-Za-z(])", r"\1*\2", s)
        s = re.sub(r"(\))\s*([\dA-Za-z(])", r"\1*\2", s)
        # keep scientific notation such as 1e5 intact
        s = re.sub(r"(?<![A-Za-z])(\d+(?:\.\d+)?)\*e(?=[+\-]?\d)", r"\1e", s)
        return s

    def _eval(self, node, funcs, consts):
        if isinstance(node, ast.Expression):
            return self._eval(node.body, funcs, consts)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise CalcError("invalid value")
        if isinstance(node, ast.BinOp):
            op = self._BIN.get(type(node.op))
            if op is None:
                raise CalcError("unsupported operator")
            a = self._eval(node.left, funcs, consts)
            b = self._eval(node.right, funcs, consts)
            if isinstance(node.op, ast.Pow) and abs(b) > 10000:
                raise CalcError("exponent too large")
            return op(a, b)
        if isinstance(node, ast.UnaryOp):
            op = self._UNARY.get(type(node.op))
            if op is None:
                raise CalcError("unsupported operator")
            return op(self._eval(node.operand, funcs, consts))
        if isinstance(node, ast.Name):
            key = node.id.lower()
            if key in consts:
                return consts[key]
            raise CalcError(f"unknown name '{node.id}'")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.keywords:
                raise CalcError("invalid function call")
            name = node.func.id.lower()
            if name not in funcs:
                raise CalcError(f"unknown function '{node.func.id}'")
            args = [self._eval(a, funcs, consts) for a in node.args]
            return funcs[name](*args)
        raise CalcError("invalid expression")

    # ----- public API ----------------------------------------------------
    def evaluate(self, expr):
        if not expr or not expr.strip():
            raise CalcError("empty expression")
        src = self._preprocess(expr)
        try:
            tree = ast.parse(src, mode="eval")
            result = self._eval(tree, self._functions(), self._constants())
        except CalcError:
            raise
        except ZeroDivisionError:
            raise CalcError("division by zero")
        except OverflowError:
            raise CalcError("result too large")
        except (ValueError, TypeError) as exc:
            raise CalcError(f"math error: {exc}")
        except SyntaxError:
            raise CalcError("syntax error")
        if isinstance(result, complex):
            raise CalcError("complex result")
        self.ans = result
        self.history.append((expr, result))
        return result

    @staticmethod
    def fmt(value):
        """Format a number nicely."""
        if isinstance(value, int):
            if abs(value) < 10**15:
                return str(value)
            digits = str(abs(value))  # avoids float overflow for huge integers
            sign = "-" if value < 0 else ""
            return f"{sign}{digits[0]}.{digits[1:11]}e+{len(digits) - 1}"
        if value != value:
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        # clean up float noise such as 0.30000000000000004 or sin(180)=1.2e-16
        if abs(value) < 1e-12:
            return "0"
        text = f"{value:.12g}"
        return text

    # memory
    def mem_add(self, v):
        self.memory += v

    def mem_sub(self, v):
        self.memory -= v

    def mem_clear(self):
        self.memory = 0.0
