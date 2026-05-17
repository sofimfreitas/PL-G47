class Translator:
    def __init__(self):
        self.code = []
        self.symbols = {}
        self.next_addr = 0
        self.label_counter = 0

    def emit(self, instruction):
        self.code.append(instruction)

    def new_label(self, prefix="L"):
        # A gramática da VM aceita labels simples, sem underscores.
        # Mantemos apenas letras/dígitos para evitar erros como:
        # "Expected ':' but '_' found".
        safe_prefix = "".join(ch for ch in str(prefix).upper() if ch.isalnum())

        if not safe_prefix or safe_prefix[0].isdigit():
            safe_prefix = f"L{safe_prefix}"

        label = f"{safe_prefix}{self.label_counter}"
        self.label_counter += 1
        return label

    def translate(self, ast):
        self.code = []
        self.symbols = {}
        self.next_addr = 0
        self.label_counter = 0

        self.emit("START")
        self.collect_declarations(ast["declarations"])

        for stmt in ast["statements"]:
            self.translate_statement(stmt)

        self.emit("STOP")
        return "\n".join(self.code) + "\n"

    def collect_declarations(self, declarations):
        total_size = 0

        for decl in declarations:
            for name, size in decl["variables"]:
                name = name.upper()
                real_size = 1 if size is None else int(size)
                self.symbols[name] = {
                    "type": decl["type"],
                    "addr": self.next_addr,
                    "size": real_size,
                    "is_array": size is not None,
                }
                self.next_addr += real_size
                total_size += real_size

        if total_size > 0:
            self.code.insert(1, f"PUSHN {total_size}")

    def addr_of(self, name):
        return self.symbols[name.upper()]["addr"]

    def symbol_of(self, name):
        return self.symbols[name.upper()]

    def quote_string(self, value):
        escaped = str(value).replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'

    def translate_statement(self, stmt):
        node = stmt["node"]

        if node == "labelled":
            self.emit(f"L{stmt['label']}:")
            self.translate_statement(stmt["statement"])

        elif node == "assignment":
            self.translate_assignment(stmt)

        elif node == "print":
            self.translate_print(stmt)

        elif node == "read":
            self.translate_read(stmt)

        elif node == "do":
            self.translate_do(stmt)

        elif node == "if":
            self.translate_if(stmt)

        elif node == "goto":
            self.emit(f"JUMP L{stmt['label']}")

        elif node == "continue":
            self.emit("NOP")

        else:
            raise NotImplementedError(f"Statement não suportado: {node}")

    def translate_assignment(self, stmt):
        self.translate_expression(stmt["value"])
        self.store_variable(stmt["target"])

    def translate_print(self, stmt):
        for item in stmt["items"]:
            if item["type"] == "STRING":
                self.emit(f"PUSHS {self.quote_string(item['value'])}")
                self.emit("WRITES")
            elif item["type"] == "INTEGER":
                self.translate_expression(item)
                self.emit("WRITEI")
            elif item["type"] == "REAL":
                self.translate_expression(item)
                self.emit("WRITEF")
            elif item["type"] == "LOGICAL":
                self.translate_expression(item)
                self.emit("WRITEI")
            else:
                raise NotImplementedError(f"Tipo não imprimível: {item['type']}")

        self.emit("WRITELN")

    def translate_read(self, stmt):
        for item in stmt["items"]:
            self.emit("READ")

            if item["type"] == "INTEGER":
                self.emit("ATOI")
            elif item["type"] == "REAL":
                self.emit("ATOF")
            elif item["type"] == "LOGICAL":
                # A VM não tem conversão booleana própria; usa-se 0/1 como LOGICAL.
                self.emit("ATOI")

            self.store_variable(item)

    def translate_do(self, stmt):
        var_name = stmt["var"].upper()
        loop_label = self.new_label("DO")
        end_label = self.new_label("ENDDO")

        self.translate_expression(stmt["start"])
        self.emit(f"STOREG {self.addr_of(var_name)}")

        self.emit(f"{loop_label}:")
        if self.is_negative_integer_literal(stmt["step"]):
            self.emit(f"PUSHG {self.addr_of(var_name)}")
            self.translate_expression(stmt["end"])
            self.emit("SUPEQ")
            self.emit(f"JZ {end_label}")
        elif self.is_integer_literal(stmt["step"]):
            self.emit(f"PUSHG {self.addr_of(var_name)}")
            self.translate_expression(stmt["end"])
            self.emit("INFEQ")
            self.emit(f"JZ {end_label}")
        else:
            positive_step_label = self.new_label("DOSTEPPOS")
            body_label = self.new_label("DOBODY")

            self.translate_expression(stmt["step"])
            self.emit("PUSHI 0")
            self.emit("INF")
            self.emit(f"JZ {positive_step_label}")

            self.emit(f"PUSHG {self.addr_of(var_name)}")
            self.translate_expression(stmt["end"])
            self.emit("SUPEQ")
            self.emit(f"JZ {end_label}")
            self.emit(f"JUMP {body_label}")

            self.emit(f"{positive_step_label}:")
            self.emit(f"PUSHG {self.addr_of(var_name)}")
            self.translate_expression(stmt["end"])
            self.emit("INFEQ")
            self.emit(f"JZ {end_label}")
            self.emit(f"{body_label}:")

        for inner_stmt in stmt["body"]:
            self.translate_statement(inner_stmt)

        self.emit(f"PUSHG {self.addr_of(var_name)}")
        self.translate_expression(stmt["step"])
        self.emit("ADD")
        self.emit(f"STOREG {self.addr_of(var_name)}")
        self.emit(f"JUMP {loop_label}")

        self.emit(f"{end_label}:")
        self.emit(f"L{stmt['label']}:")
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

    def translate_if(self, stmt):
        else_label = self.new_label("ELSE")
        end_label = self.new_label("ENDIF")

        self.translate_condition(stmt["condition"])
        self.emit(f"JZ {else_label}")

        for inner_stmt in stmt["then"]:
            self.translate_statement(inner_stmt)

        self.emit(f"JUMP {end_label}")
        self.emit(f"{else_label}:")

        for inner_stmt in stmt["else"]:
            self.translate_statement(inner_stmt)

        self.emit(f"{end_label}:")
        self.emit("NOP")

    def translate_expression(self, expr):
        node = expr["node"]

        if node == "number":
            self.emit(f"PUSHI {expr['value']}")

        elif node == "real_number":
            self.emit(f"PUSHF {expr['value']}")

        elif node == "bool_literal":
            self.emit(f"PUSHI {expr['value']}")

        elif node == "variable":
            self.emit(f"PUSHG {self.addr_of(expr['name'])}")

        elif node == "array_access":
            self.translate_array_address(expr)
            self.emit("LOAD 0")

        elif node == "cast":
            self.translate_expression(expr["expr"])
            if expr["to"] == "REAL":
                self.emit("ITOF")
            else:
                raise NotImplementedError(f"Cast não suportado: {expr['to']}")

        elif node == "unary_expression":
            if expr["type"] == "REAL":
                self.emit("PUSHF 0.0")
                self.translate_expression(expr["expr"])
                self.emit("FSUB")
            else:
                self.emit("PUSHI 0")
                self.translate_expression(expr["expr"])
                self.emit("SUB")

        elif node == "binary_expression":
            self.translate_expression(expr["left"])
            self.translate_expression(expr["right"])
            self.emit(self.operation_instruction(expr["op"], expr["type"]))

        elif node in ("condition", "logical_condition", "not_condition"):
            self.translate_condition(expr)

        else:
            raise NotImplementedError(f"Expressão não suportada: {node}")

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

    def translate_condition(self, cond):
        node = cond["node"]

        if node in ("variable", "array_access", "bool_literal"):
            self.translate_expression(cond)
            return

        if node == "not_condition":
            self.translate_condition(cond["expr"])
            self.emit("NOT")
            return

        if node == "logical_condition":
            self.translate_condition(cond["left"])
            self.translate_condition(cond["right"])
            if cond["op"] == ".AND.":
                self.emit("AND")
            elif cond["op"] == ".OR.":
                self.emit("OR")
            else:
                raise NotImplementedError(f"Operador lógico não suportado: {cond['op']}")
            return

        if node == "condition":
            self.translate_expression(cond["left"])
            self.translate_expression(cond["right"])
            if cond["op"].upper() == ".NE.":
                self.emit("EQUAL")
                self.emit("NOT")
            else:
                self.emit(self.relation_instruction(cond["op"], cond["left"]["type"], cond["right"]["type"]))
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

    def store_variable(self, var):
        if var["node"] == "variable":
            self.emit(f"STOREG {self.addr_of(var['name'])}")

        elif var["node"] == "array_access":
            self.translate_array_address(var)
            self.emit("SWAP")
            self.emit("STORE 0")

        else:
            raise NotImplementedError(f"Destino de atribuição inválido: {var['node']}")

    def translate_array_address(self, var):
        symbol = self.symbol_of(var["name"])
        base_addr = symbol["addr"]

        self.emit("PUSHGP")
        self.emit(f"PUSHI {base_addr}")
        self.emit("PADD")

        self.translate_expression(var["index"])
        self.emit(f"CHECK 1, {symbol['size']}")
        self.emit("PUSHI 1")
        self.emit("SUB")
        self.emit("PADD")
