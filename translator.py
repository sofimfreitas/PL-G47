class Translator:
    def __init__(self):
        self.code = []
        self.next_addr = 0
        self.label_counter = 0
        self.main_symbols = {}
        self.subprograms = {}
        self.active_subprogram_calls = []

    def emit(self, instruction):
        self.code.append(instruction)

    def new_label(self, prefix="L"):
        safe_prefix = "".join(ch for ch in str(prefix).upper() if ch.isalnum())

        if not safe_prefix or safe_prefix[0].isdigit():
            safe_prefix = f"L{safe_prefix}"

        label = f"{safe_prefix}{self.label_counter}"
        self.label_counter += 1
        return label

    def translate(self, ast):
        self.code = []
        self.next_addr = 0
        self.label_counter = 0
        self.main_symbols = {}
        self.subprograms = {}
        self.active_subprogram_calls = []

        self.collect_program_layout(ast)

        self.emit("START")
        if self.next_addr > 0:
            self.emit(f"PUSHN {self.next_addr}")

        main_context = self.make_context(self.main_symbols)

        for stmt in ast["statements"]:
            self.translate_statement(stmt, main_context)

        self.emit("STOP")
        return "\n".join(self.code) + "\n"

    def make_context(self, symbols, return_label=None, subprogram_name=None, aliases=None):
        return {
            "symbols": symbols,
            "labels": {},
            "return_label": return_label,
            "subprogram_name": subprogram_name,
            "aliases": aliases or {},
        }

    def collect_program_layout(self, ast):
        self.main_symbols = self.allocate_scope_symbols(ast["declarations"])

        for subprogram in ast.get("subprograms", []):
            return_entry = None
            if subprogram["node"] == "function":
                return_entry = {
                    "name": subprogram["name"],
                    "type": subprogram["return_type"],
                }

            self.subprograms[subprogram["name"].upper()] = {
                "node": subprogram["node"],
                "name": subprogram["name"].upper(),
                "params": [param.upper() for param in subprogram["params"]],
                "return_type": subprogram.get("return_type"),
                "return_name": subprogram["name"].upper() if return_entry else None,
                "symbols": self.allocate_scope_symbols(subprogram["declarations"], return_entry),
                "statements": subprogram["statements"],
            }

    def allocate_scope_symbols(self, declarations, return_entry=None):
        symbols = {}

        if return_entry is not None:
            symbols[return_entry["name"].upper()] = {
                "type": return_entry["type"],
                "addr": self.next_addr,
                "size": 1,
                "is_array": False,
            }
            self.next_addr += 1

        for decl in declarations:
            for name, size in decl["variables"]:
                name = name.upper()
                real_size = 1 if size is None else int(size)
                symbols[name] = {
                    "type": decl["type"],
                    "addr": self.next_addr,
                    "size": real_size,
                    "is_array": size is not None,
                }
                self.next_addr += real_size

        return symbols

    def symbol_of(self, context, name):
        return context["symbols"][name.upper()]

    def addr_of(self, context, name):
        return self.symbol_of(context, name)["addr"]

    def alias_of(self, context, name):
        return context.get("aliases", {}).get(name.upper())

    def label_name(self, context, label):
        label = int(label)
        if label not in context["labels"]:
            context["labels"][label] = self.new_label(f"L{label}")
        return context["labels"][label]

    def quote_string(self, value):
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def variable_node(self, context, name):
        symbol = self.symbol_of(context, name)
        return {
            "node": "variable",
            "name": name.upper(),
            "type": symbol["type"],
            "size": None,
        }

    def translate_statement(self, stmt, context):
        node = stmt["node"]

        if node == "labelled":
            self.emit(f"{self.label_name(context, stmt['label'])}:")
            self.translate_statement(stmt["statement"], context)

        elif node == "assignment":
            self.translate_assignment(stmt, context)

        elif node == "print":
            self.translate_print(stmt, context)

        elif node == "read":
            self.translate_read(stmt, context)

        elif node == "do":
            self.translate_do(stmt, context)

        elif node == "if":
            self.translate_if(stmt, context)

        elif node == "goto":
            self.emit(f"JUMP {self.label_name(context, stmt['label'])}")

        elif node == "subroutine_call":
            self.translate_subroutine_call(stmt, context)

        elif node == "continue":
            self.emit("NOP")

        elif node == "return":
            if context["return_label"] is None:
                raise NotImplementedError("RETURN só é suportado dentro de FUNCTION ou SUBROUTINE.")
            self.emit(f"JUMP {context['return_label']}")

        else:
            raise NotImplementedError(f"Statement não suportado: {node}")

    def translate_assignment(self, stmt, context):
        self.translate_expression(stmt["value"], context)
        self.store_variable(stmt["target"], context)

    def translate_print(self, stmt, context):
        for item in stmt["items"]:
            if item["type"] == "STRING":
                self.emit(f"PUSHS {self.quote_string(item['value'])}")
                self.emit("WRITES")
            elif item["type"] == "INTEGER":
                self.translate_expression(item, context)
                self.emit("WRITEI")
            elif item["type"] == "REAL":
                self.translate_expression(item, context)
                self.emit("WRITEF")
            elif item["type"] == "LOGICAL":
                self.translate_expression(item, context)
                self.emit("WRITEI")
            else:
                raise NotImplementedError(f"Tipo não imprimível: {item['type']}")

        self.emit("WRITELN")

    def translate_read(self, stmt, context):
        for item in stmt["items"]:
            self.emit("READ")

            if item["type"] == "INTEGER":
                self.emit("ATOI")
            elif item["type"] == "REAL":
                self.emit("ATOF")
            elif item["type"] == "LOGICAL":
                self.emit("ATOI")

            self.store_variable(item, context)

    def translate_do(self, stmt, context):
        var_name = stmt["var"].upper()
        var_node = self.variable_node(context, var_name)
        loop_label = self.new_label("DO")
        end_label = self.new_label("ENDDO")

        self.translate_expression(stmt["start"], context)
        self.store_variable(var_node, context)

        self.emit(f"{loop_label}:")
        if self.is_negative_integer_literal(stmt["step"]):
            self.translate_expression(var_node, context)
            self.translate_expression(stmt["end"], context)
            self.emit("SUPEQ")
            self.emit(f"JZ {end_label}")
        elif self.is_integer_literal(stmt["step"]):
            self.translate_expression(var_node, context)
            self.translate_expression(stmt["end"], context)
            self.emit("INFEQ")
            self.emit(f"JZ {end_label}")
        else:
            positive_step_label = self.new_label("DOSTEPPOS")
            body_label = self.new_label("DOBODY")

            self.translate_expression(stmt["step"], context)
            self.emit("PUSHI 0")
            self.emit("INF")
            self.emit(f"JZ {positive_step_label}")

            self.translate_expression(var_node, context)
            self.translate_expression(stmt["end"], context)
            self.emit("SUPEQ")
            self.emit(f"JZ {end_label}")
            self.emit(f"JUMP {body_label}")

            self.emit(f"{positive_step_label}:")
            self.translate_expression(var_node, context)
            self.translate_expression(stmt["end"], context)
            self.emit("INFEQ")
            self.emit(f"JZ {end_label}")
            self.emit(f"{body_label}:")

        for inner_stmt in stmt["body"]:
            self.translate_statement(inner_stmt, context)

        self.translate_expression(var_node, context)
        self.translate_expression(stmt["step"], context)
        self.emit("ADD")
        self.store_variable(var_node, context)
        self.emit(f"JUMP {loop_label}")

        self.emit(f"{end_label}:")
        self.emit(f"{self.label_name(context, stmt['label'])}:")
        self.emit("NOP")

    def is_negative_integer_literal(self, expr):
        if expr["node"] == "number":
            return expr["value"] < 0
        return (
            expr["node"] == "unary_expression"
            and expr["op"] == "-"
            and expr["expr"]["node"] == "number"
            and expr["expr"]["value"] > 0
        )

    def is_integer_literal(self, expr):
        return expr["node"] == "number" or (
            expr["node"] == "unary_expression"
            and expr["op"] == "-"
            and expr["expr"]["node"] == "number"
        )

    def translate_if(self, stmt, context):
        else_label = self.new_label("ELSE")
        end_label = self.new_label("ENDIF")

        self.translate_condition(stmt["condition"], context)
        self.emit(f"JZ {else_label}")

        for inner_stmt in stmt["then"]:
            self.translate_statement(inner_stmt, context)

        self.emit(f"JUMP {end_label}")
        self.emit(f"{else_label}:")

        for inner_stmt in stmt["else"]:
            self.translate_statement(inner_stmt, context)

        self.emit(f"{end_label}:")
        self.emit("NOP")

    def translate_expression(self, expr, context):
        node = expr["node"]

        if node == "number":
            self.emit(f"PUSHI {expr['value']}")

        elif node == "real_number":
            self.emit(f"PUSHF {expr['value']}")

        elif node == "bool_literal":
            self.emit(f"PUSHI {expr['value']}")

        elif node == "variable":
            alias = self.alias_of(context, expr["name"])
            if alias is not None and alias["target"]["node"] != "array_argument":
                self.translate_expression(alias["target"], alias["context"])
            else:
                self.emit(f"PUSHG {self.addr_of(context, expr['name'])}")

        elif node == "array_access":
            self.translate_array_address(expr, context)
            self.emit("LOAD 0")

        elif node == "array_argument":
            raise NotImplementedError("Um array inteiro só pode ser passado como argumento de SUBROUTINE.")

        elif node == "cast":
            self.translate_expression(expr["expr"], context)
            if expr["to"] == "REAL":
                self.emit("ITOF")
            else:
                raise NotImplementedError(f"Cast não suportado: {expr['to']}")

        elif node == "unary_expression":
            if expr["type"] == "REAL":
                self.emit("PUSHF 0.0")
                self.translate_expression(expr["expr"], context)
                self.emit("FSUB")
            else:
                self.emit("PUSHI 0")
                self.translate_expression(expr["expr"], context)
                self.emit("SUB")

        elif node == "binary_expression":
            self.translate_expression(expr["left"], context)
            self.translate_expression(expr["right"], context)
            self.emit(self.operation_instruction(expr["op"], expr["type"]))

        elif node in ("condition", "logical_condition", "not_condition"):
            self.translate_condition(expr, context)

        elif node == "function_call":
            self.translate_function_call(expr, context)

        else:
            raise NotImplementedError(f"Expressão não suportada: {node}")

    def translate_function_call(self, expr, caller_context):
        function_name = expr["name"].upper()
        subprogram = self.subprograms[function_name]

        if function_name in self.active_subprogram_calls:
            raise NotImplementedError("Recursão de subprogramas ainda não é suportada.")

        for param_name, arg_expr in zip(subprogram["params"], expr["args"]):
            self.translate_expression(arg_expr, caller_context)
            self.emit(f"STOREG {subprogram['symbols'][param_name]['addr']}")

        return_label = self.new_label(f"RET{function_name}")
        inline_context = self.make_context(
            subprogram["symbols"],
            return_label=return_label,
            subprogram_name=function_name,
        )

        self.active_subprogram_calls.append(function_name)
        for stmt in subprogram["statements"]:
            self.translate_statement(stmt, inline_context)
        self.active_subprogram_calls.pop()

        self.emit(f"{return_label}:")
        self.emit(f"PUSHG {subprogram['symbols'][subprogram['return_name']]['addr']}")

    def translate_subroutine_call(self, stmt, caller_context):
        subroutine_name = stmt["name"].upper()
        subprogram = self.subprograms[subroutine_name]

        if subroutine_name in self.active_subprogram_calls:
            raise NotImplementedError("Recursão de subprogramas ainda não é suportada.")

        aliases = {}
        for param_name, arg in zip(subprogram["params"], stmt["args"]):
            param_symbol = subprogram["symbols"][param_name]

            if arg["node"] == "array_argument":
                if not param_symbol["is_array"]:
                    raise NotImplementedError(
                        f"Parâmetro escalar '{param_name}' recebeu array completo."
                    )
                aliases[param_name] = {"target": arg, "context": caller_context}

            elif arg["node"] in ("variable", "array_access"):
                if param_symbol["is_array"]:
                    raise NotImplementedError(
                        f"Parâmetro array '{param_name}' exige um array completo como argumento."
                    )
                aliases[param_name] = {"target": arg, "context": caller_context}

            else:
                if param_symbol["is_array"]:
                    raise NotImplementedError(
                        f"Parâmetro array '{param_name}' não pode receber uma expressão escalar."
                    )
                self.translate_expression(arg, caller_context)
                self.emit(f"STOREG {param_symbol['addr']}")

        return_label = self.new_label(f"RET{subroutine_name}")
        inline_context = self.make_context(
            subprogram["symbols"],
            return_label=return_label,
            subprogram_name=subroutine_name,
            aliases=aliases,
        )

        self.active_subprogram_calls.append(subroutine_name)
        for inner_stmt in subprogram["statements"]:
            self.translate_statement(inner_stmt, inline_context)
        self.active_subprogram_calls.pop()

        self.emit(f"{return_label}:")
        self.emit("NOP")

    def operation_instruction(self, op, expr_type):
        if expr_type == "INTEGER":
            mapping = {
                "+": "ADD",
                "-": "SUB",
                "*": "MUL",
                "/": "DIV",
                "MOD": "MOD",
            }
        else:
            mapping = {
                "+": "FADD",
                "-": "FSUB",
                "*": "FMUL",
                "/": "FDIV",
            }

        if op not in mapping:
            raise NotImplementedError(f"Operador '{op}' não suportado para {expr_type}.")

        return mapping[op]

    def translate_condition(self, cond, context):
        node = cond["node"]

        if node in ("variable", "array_access", "bool_literal"):
            self.translate_expression(cond, context)
            return

        if node == "not_condition":
            self.translate_condition(cond["expr"], context)
            self.emit("NOT")
            return

        if node == "logical_condition":
            self.translate_condition(cond["left"], context)
            self.translate_condition(cond["right"], context)
            if cond["op"] == ".AND.":
                self.emit("AND")
            elif cond["op"] == ".OR.":
                self.emit("OR")
            else:
                raise NotImplementedError(f"Operador lógico não suportado: {cond['op']}")
            return

        if node == "condition":
            self.translate_expression(cond["left"], context)
            self.translate_expression(cond["right"], context)
            if cond["op"].upper() == ".NE.":
                self.emit("EQUAL")
                self.emit("NOT")
            else:
                self.emit(
                    self.relation_instruction(
                        cond["op"],
                        cond["left"]["type"],
                        cond["right"]["type"],
                    )
                )
            return

        raise NotImplementedError(f"Condição não suportada: {node}")

    def relation_instruction(self, op, left_type, right_type):
        op = op.upper()
        use_float = left_type == "REAL" or right_type == "REAL"

        if op in ("=", ".EQ."):
            return "EQUAL"

        int_mapping = {
            "<": "INF",
            ".LT.": "INF",
            "<=": "INFEQ",
            ".LE.": "INFEQ",
            ">": "SUP",
            ".GT.": "SUP",
            ">=": "SUPEQ",
            ".GE.": "SUPEQ",
        }
        float_mapping = {
            "<": "FINF",
            ".LT.": "FINF",
            "<=": "FINFEQ",
            ".LE.": "FINFEQ",
            ">": "FSUP",
            ".GT.": "FSUP",
            ">=": "FSUPEQ",
            ".GE.": "FSUPEQ",
        }

        mapping = float_mapping if use_float else int_mapping
        if op not in mapping:
            raise NotImplementedError(f"Operador relacional não suportado: {op}")
        return mapping[op]

    def store_variable(self, var, context):
        if var["node"] == "variable":
            alias = self.alias_of(context, var["name"])
            if alias is not None and alias["target"]["node"] != "array_argument":
                self.store_variable(alias["target"], alias["context"])
            else:
                self.emit(f"STOREG {self.addr_of(context, var['name'])}")

        elif var["node"] == "array_access":
            self.translate_array_address(var, context)
            self.emit("SWAP")
            self.emit("STORE 0")

        else:
            raise NotImplementedError(f"Destino de atribuição inválido: {var['node']}")

    def emit_array_base_address(self, context, name):
        base_addr = self.addr_of(context, name)
        self.emit("PUSHGP")
        self.emit(f"PUSHI {base_addr}")
        self.emit("PADD")

    def translate_array_address(self, var, context):
        alias = self.alias_of(context, var["name"])

        if alias is not None:
            target = alias["target"]
            target_context = alias["context"]

            if target["node"] != "array_argument":
                raise NotImplementedError(
                    f"Parâmetro escalar '{var['name']}' não pode ser usado como array."
                )

            target_symbol = self.symbol_of(target_context, target["name"])
            self.emit_array_base_address(target_context, target["name"])
            self.translate_expression(var["index"], context)
            self.emit(f"CHECK 1, {target_symbol['size']}")
            self.emit("PUSHI 1")
            self.emit("SUB")
            self.emit("PADD")
            return

        symbol = self.symbol_of(context, var["name"])
        self.emit_array_base_address(context, var["name"])
        self.translate_expression(var["index"], context)
        self.emit(f"CHECK 1, {symbol['size']}")
        self.emit("PUSHI 1")
        self.emit("SUB")
        self.emit("PADD")
