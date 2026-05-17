class SemanticError(Exception):
    pass


class SemanticAnalyzer:
    def __init__(self):
        self.global_symbols = {}
        self.current_symbols = self.global_symbols
        self.subprograms = {}
        self.current_subprogram = None
        self.scope_stack = []

        self.do_labels_stack = [set()]
        self.labels_stack = [set()]
        self.gotos_stack = [set()]

    def _normalize_params(self, params):
        return [param.upper() for param in params]

    def _predeclare_subprogram(self, name, kind, params, return_type=None):
        name = name.upper()
        params = self._normalize_params(params)
        existing = self.subprograms.get(name)

        if existing and (
            existing["kind"] != kind
            or existing.get("return_type") != return_type
            or existing["params"] != params
        ):
            raise SemanticError(f"Definição inconsistente do subprograma '{name}'.")

        if not existing:
            self.subprograms[name] = {
                "kind": kind,
                "return_type": return_type,
                "params": params,
                "defined": False,
            }

    def predeclare_function(self, name, return_type, params):
        self._predeclare_subprogram(name, "function", params, return_type)

    def predeclare_subroutine(self, name, params):
        self._predeclare_subprogram(name, "subroutine", params)

    def _start_subprogram(self, name, kind, params, return_type=None):
        name = name.upper()
        params = self._normalize_params(params)

        if kind == "function":
            self.predeclare_function(name, return_type, params)
        else:
            self.predeclare_subroutine(name, params)

        prototype = self.subprograms[name]
        if prototype["defined"]:
            readable_kind = "Função" if kind == "function" else "Subrotina"
            raise SemanticError(f"{readable_kind} '{name}' definida mais do que uma vez.")

        self.scope_stack.append((self.current_symbols, self.current_subprogram))
        self.current_symbols = {}
        self.current_subprogram = {
            "name": name,
            "kind": kind,
            "return_type": return_type,
            "params": params,
            "missing_params": set(params),
        }

        self.do_labels_stack.append(set())
        self.labels_stack.append(set())
        self.gotos_stack.append(set())

        if kind == "function":
            # Em Fortran 77, o valor de retorno de uma função é obtido atribuindo
            # à variável com o mesmo nome da função.
            self.current_symbols[name] = {
                "type": return_type,
                "size": None,
            }

    def start_function(self, name, return_type, params):
        self._start_subprogram(name, "function", params, return_type)

    def start_subroutine(self, name, params):
        self._start_subprogram(name, "subroutine", params)

    def finish_subprogram(self):
        self.validate_labels()

        missing_params = sorted(self.current_subprogram["missing_params"])
        if missing_params:
            kind_name = "função" if self.current_subprogram["kind"] == "function" else "subrotina"
            raise SemanticError(
                f"Parâmetros da {kind_name} '{self.current_subprogram['name']}' sem declaração: {missing_params}"
            )

        self.subprograms[self.current_subprogram["name"]]["defined"] = True

        self.do_labels_stack.pop()
        self.labels_stack.pop()
        self.gotos_stack.pop()

        self.current_symbols, self.current_subprogram = self.scope_stack.pop()

    def declare_variable(self, name, var_type, size=None):
        name = name.upper()

        if name in self.current_symbols:
            raise SemanticError(f"Variável '{name}' já declarada.")

        if size is not None and size <= 0:
            raise SemanticError(f"Array '{name}' tem tamanho inválido: {size}.")

        self.current_symbols[name] = {
            "type": var_type,
            "size": size,
        }

        if self.current_subprogram and name in self.current_subprogram["missing_params"]:
            self.current_subprogram["missing_params"].remove(name)

    def check_declared(self, name):
        name = name.upper()

        if name not in self.current_symbols:
            raise SemanticError(f"Variável '{name}' usada sem ter sido declarada.")

        return self.current_symbols[name]

    def check_assignment(self, name, expr_type):
        var = self.check_declared(name)

        if var["type"] == expr_type:
            return None

        if var["type"] == "REAL" and expr_type == "INTEGER":
            return "REAL"

        raise SemanticError(
            f"Atribuição inválida: variável '{name}' é {var['type']} mas recebeu {expr_type}."
        )

    def check_array_access(self, name):
        var = self.check_declared(name)

        if var["size"] is None:
            raise SemanticError(f"'{name}' não é um array.")

        return var

    def is_function(self, name):
        name = name.upper()
        return name in self.subprograms and self.subprograms[name]["kind"] == "function"

    def is_subroutine(self, name):
        name = name.upper()
        return name in self.subprograms and self.subprograms[name]["kind"] == "subroutine"

    def check_function_call(self, name, arguments):
        name = name.upper()

        if name not in self.subprograms or self.subprograms[name]["kind"] != "function":
            raise SemanticError(f"Função '{name}' não está definida.")

        signature = self.subprograms[name]
        expected = len(signature["params"])
        received = len(arguments)
        if expected != received:
            raise SemanticError(
                f"Função '{name}' esperava {expected} argumentos, recebeu {received}."
            )

        return signature["return_type"]

    def check_subroutine_call(self, name, arguments):
        name = name.upper()

        if name not in self.subprograms or self.subprograms[name]["kind"] != "subroutine":
            raise SemanticError(f"Subrotina '{name}' não está definida.")

        signature = self.subprograms[name]
        expected = len(signature["params"])
        received = len(arguments)
        if expected != received:
            raise SemanticError(
                f"Subrotina '{name}' esperava {expected} argumentos, recebeu {received}."
            )

    def validate_subprogram_definitions(self):
        missing = [name for name, data in self.subprograms.items() if not data["defined"]]
        if missing:
            raise SemanticError(f"Subprogramas declarados mas não definidos: {sorted(missing)}")

    def register_do_label(self, label):
        self.do_labels_stack[-1].add(int(label))

    def define_label(self, label):
        label = int(label)
        if label in self.labels_stack[-1]:
            raise SemanticError(f"Label '{label}' definido mais do que uma vez.")
        self.labels_stack[-1].add(label)

    def register_goto(self, label):
        self.gotos_stack[-1].add(int(label))

    def validate_labels(self):
        missing_do = self.do_labels_stack[-1] - self.labels_stack[-1]
        if missing_do:
            raise SemanticError(
                f"Labels de DO sem CONTINUE correspondente: {sorted(missing_do)}"
            )

        missing_goto = self.gotos_stack[-1] - self.labels_stack[-1]
        if missing_goto:
            raise SemanticError(
                f"GOTO para labels não definidos: {sorted(missing_goto)}"
            )
