from copy import deepcopy


class OptimizationStats:
    def __init__(self):
        self.constant_folds = 0
        self.algebraic_simplifications = 0
        self.removed_assignments = 0
        self.removed_branches = 0

    @property
    def total(self):
        return (
            self.constant_folds
            + self.algebraic_simplifications
            + self.removed_assignments
            + self.removed_branches
        )

    def as_dict(self):
        return {
            "total": self.total,
            "constant_folds": self.constant_folds,
            "algebraic_simplifications": self.algebraic_simplifications,
            "removed_assignments": self.removed_assignments,
            "removed_branches": self.removed_branches,
        }


class ASTOptimizer:
    def __init__(self):
        self.stats = OptimizationStats()

    def optimize(self, ast):
        ast = deepcopy(ast)
        ast["declarations"] = ast.get("declarations", [])
        ast["statements"] = self.optimize_statements(ast.get("statements", []))
        ast["subprograms"] = [self.optimize_subprogram(sub) for sub in ast.get("subprograms", [])]
        return ast, self.stats.as_dict()

    def optimize_subprogram(self, subprogram):
        subprogram = deepcopy(subprogram)
        subprogram["statements"] = self.optimize_statements(subprogram.get("statements", []))
        return subprogram

    def optimize_statements(self, statements):
        optimized = []
        for stmt in statements:
            result = self.optimize_statement(stmt)
            if result is None:
                continue
            if isinstance(result, list):
                optimized.extend(result)
            else:
                optimized.append(result)
        return optimized

    def optimize_statement(self, stmt):
        node = stmt["node"]

        if node == "labelled":
            inner = self.optimize_statement(stmt["statement"])
            if inner is None:
                # Mantém o label vivo para não partir GOTO/DO que saltem para ele.
                return {
                    "node": "labelled",
                    "label": stmt["label"],
                    "statement": {"node": "continue"},
                }
            if isinstance(inner, list):
                first = inner[0] if inner else {"node": "continue"}
                rest = inner[1:]
                return [
                    {
                        "node": "labelled",
                        "label": stmt["label"],
                        "statement": first,
                    },
                    *rest,
                ]
            stmt = deepcopy(stmt)
            stmt["statement"] = inner
            return stmt

        if node == "assignment":
            stmt = deepcopy(stmt)
            stmt["value"] = self.optimize_expression(stmt["value"])
            stmt["target"] = self.optimize_designator_expr(stmt["target"])
            if self.is_self_assignment(stmt):
                self.stats.removed_assignments += 1
                return None
            return stmt

        if node == "print":
            stmt = deepcopy(stmt)
            stmt["items"] = [self.optimize_expression(item) for item in stmt["items"]]
            return stmt

        if node == "read":
            stmt = deepcopy(stmt)
            stmt["items"] = [self.optimize_designator_expr(item) for item in stmt["items"]]
            return stmt

        if node == "do":
            stmt = deepcopy(stmt)
            stmt["start"] = self.optimize_expression(stmt["start"])
            stmt["end"] = self.optimize_expression(stmt["end"])
            stmt["step"] = self.optimize_expression(stmt["step"])
            stmt["body"] = self.optimize_statements(stmt["body"])
            return stmt

        if node == "if":
            stmt = deepcopy(stmt)
            stmt["condition"] = self.optimize_expression(stmt["condition"])
            stmt["then"] = self.optimize_statements(stmt["then"])
            stmt["else"] = self.optimize_statements(stmt["else"])

            if self.is_bool_literal(stmt["condition"]):
                selected = stmt["then"] if stmt["condition"]["value"] else stmt["else"]
                discarded = stmt["else"] if stmt["condition"]["value"] else stmt["then"]
                if not self.contains_label(discarded):
                    self.stats.removed_branches += 1
                    return selected

            return stmt

        if node == "subroutine_call":
            stmt = deepcopy(stmt)
            stmt["args"] = [self.optimize_expression(arg) for arg in stmt["args"]]
            return stmt

        return deepcopy(stmt)

    def optimize_designator_expr(self, expr):
        expr = deepcopy(expr)
        if expr.get("node") == "array_access":
            expr["index"] = self.optimize_expression(expr["index"])
        return expr

    def optimize_expression(self, expr):
        node = expr["node"]

        if node in ("number", "real_number", "bool_literal", "string", "variable", "array_argument"):
            return deepcopy(expr)

        if node == "array_access":
            return self.optimize_designator_expr(expr)

        if node == "cast":
            expr = deepcopy(expr)
            expr["expr"] = self.optimize_expression(expr["expr"])
            if expr["to"] == "REAL" and expr["expr"]["node"] == "number":
                self.stats.constant_folds += 1
                return self.real_literal(float(expr["expr"]["value"]))
            return expr

        if node == "function_call":
            expr = deepcopy(expr)
            expr["args"] = [self.optimize_expression(arg) for arg in expr["args"]]
            return expr

        if node == "unary_expression":
            expr = deepcopy(expr)
            expr["expr"] = self.optimize_expression(expr["expr"])
            return self.optimize_unary(expr)

        if node == "binary_expression":
            expr = deepcopy(expr)
            expr["left"] = self.optimize_expression(expr["left"])
            expr["right"] = self.optimize_expression(expr["right"])
            return self.optimize_binary(expr)

        if node == "condition":
            expr = deepcopy(expr)
            expr["left"] = self.optimize_expression(expr["left"])
            expr["right"] = self.optimize_expression(expr["right"])
            return self.optimize_relational(expr)

        if node == "logical_condition":
            expr = deepcopy(expr)
            expr["left"] = self.optimize_expression(expr["left"])
            expr["right"] = self.optimize_expression(expr["right"])
            return self.optimize_logical(expr)

        if node == "not_condition":
            expr = deepcopy(expr)
            expr["expr"] = self.optimize_expression(expr["expr"])
            if self.is_bool_literal(expr["expr"]):
                self.stats.constant_folds += 1
                return self.bool_literal(0 if expr["expr"]["value"] else 1)
            return expr

        return deepcopy(expr)

    def optimize_unary(self, expr):
        inner = expr["expr"]
        if inner["node"] == "number":
            self.stats.constant_folds += 1
            return self.int_literal(-inner["value"])
        if inner["node"] == "real_number":
            self.stats.constant_folds += 1
            return self.real_literal(-inner["value"])
        if inner["node"] == "unary_expression" and inner["op"] == "-":
            self.stats.algebraic_simplifications += 1
            return inner["expr"]
        return expr

    def optimize_binary(self, expr):
        left = expr["left"]
        right = expr["right"]
        op = expr["op"]
        expr_type = expr["type"]

        folded = self.fold_arithmetic(op, left, right, expr_type)
        if folded is not None:
            self.stats.constant_folds += 1
            return folded

        simplified = self.simplify_arithmetic(op, left, right, expr_type)
        if simplified is not None:
            self.stats.algebraic_simplifications += 1
            return simplified

        return expr

    def fold_arithmetic(self, op, left, right, expr_type):
        if not self.is_numeric_literal(left) or not self.is_numeric_literal(right):
            return None

        a = left["value"]
        b = right["value"]

        try:
            if op == "+":
                value = a + b
            elif op == "-":
                value = a - b
            elif op == "*":
                value = a * b
            elif op == "/":
                if b == 0:
                    return None
                value = int(a / b) if expr_type == "INTEGER" else a / b
            elif op == "MOD":
                if b == 0:
                    return None
                value = a % b
            else:
                return None
        except ZeroDivisionError:
            return None

        return self.int_literal(int(value)) if expr_type == "INTEGER" else self.real_literal(float(value))

    def simplify_arithmetic(self, op, left, right, expr_type):
        zero = self.int_literal(0) if expr_type == "INTEGER" else self.real_literal(0.0)

        if op == "+":
            if self.is_zero(left):
                return right
            if self.is_zero(right):
                return left

        if op == "-" and self.is_zero(right):
            return left

        if op == "*":
            if self.is_zero(left) or self.is_zero(right):
                return zero
            if self.is_one(left):
                return right
            if self.is_one(right):
                return left

        if op == "/" and self.is_one(right):
            return left

        if op == "MOD" and self.is_one(right):
            return self.int_literal(0)

        return None

    def optimize_relational(self, expr):
        left = expr["left"]
        right = expr["right"]
        if not self.is_literal(left) or not self.is_literal(right):
            return expr

        op = expr["op"].upper()
        a = left["value"]
        b = right["value"]

        if op in ("=", ".EQ."):
            result = a == b
        elif op == ".NE.":
            result = a != b
        elif op in ("<", ".LT."):
            result = a < b
        elif op in ("<=", ".LE."):
            result = a <= b
        elif op in (">", ".GT."):
            result = a > b
        elif op in (">=", ".GE."):
            result = a >= b
        else:
            return expr

        self.stats.constant_folds += 1
        return self.bool_literal(1 if result else 0)

    def optimize_logical(self, expr):
        left = expr["left"]
        right = expr["right"]
        op = expr["op"]

        if self.is_bool_literal(left) and self.is_bool_literal(right):
            self.stats.constant_folds += 1
            if op == ".AND.":
                return self.bool_literal(1 if left["value"] and right["value"] else 0)
            if op == ".OR.":
                return self.bool_literal(1 if left["value"] or right["value"] else 0)

        if op == ".AND.":
            if self.is_bool_literal(left):
                self.stats.algebraic_simplifications += 1
                return right if left["value"] else self.bool_literal(0)
            if self.is_bool_literal(right):
                self.stats.algebraic_simplifications += 1
                return left if right["value"] else self.bool_literal(0)

        if op == ".OR.":
            if self.is_bool_literal(left):
                self.stats.algebraic_simplifications += 1
                return self.bool_literal(1) if left["value"] else right
            if self.is_bool_literal(right):
                self.stats.algebraic_simplifications += 1
                return self.bool_literal(1) if right["value"] else left

        return expr

    def is_self_assignment(self, stmt):
        target = stmt["target"]
        value = stmt["value"]
        return (
            target["node"] == "variable"
            and value["node"] == "variable"
            and target["name"].upper() == value["name"].upper()
        )

    def contains_label(self, statements):
        for stmt in statements:
            if stmt["node"] == "labelled":
                return True
            if stmt["node"] == "if" and (self.contains_label(stmt["then"]) or self.contains_label(stmt["else"])):
                return True
            if stmt["node"] == "do":
                return True
        return False

    def is_literal(self, expr):
        return expr["node"] in ("number", "real_number", "bool_literal")

    def is_numeric_literal(self, expr):
        return expr["node"] in ("number", "real_number")

    def is_bool_literal(self, expr):
        return expr["node"] == "bool_literal"

    def is_zero(self, expr):
        return self.is_numeric_literal(expr) and expr["value"] == 0

    def is_one(self, expr):
        return self.is_numeric_literal(expr) and expr["value"] == 1

    def int_literal(self, value):
        return {"node": "number", "value": int(value), "type": "INTEGER"}

    def real_literal(self, value):
        return {"node": "real_number", "value": float(value), "type": "REAL"}

    def bool_literal(self, value):
        return {"node": "bool_literal", "value": 1 if value else 0, "type": "LOGICAL"}


def optimize_ast(ast):
    optimizer = ASTOptimizer()
    return optimizer.optimize(ast)
