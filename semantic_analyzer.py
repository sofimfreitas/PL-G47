class SemanticError(Exception):
    pass


class SemanticAnalyzer:
    def __init__(self):
        self.symbols = {}
        self.do_labels = set()
        self.labels = set()
        self.gotos = set()

    def declare_variable(self, name, var_type, size=None):
        name = name.upper()

        if name in self.symbols:
            raise SemanticError(f"Variável '{name}' já declarada.")

        if size is not None and size <= 0:
            raise SemanticError(f"Array '{name}' tem tamanho inválido: {size}.")

        self.symbols[name] = {
            "type": var_type,
            "size": size,
        }

    def check_declared(self, name):
        name = name.upper()

        if name not in self.symbols:
            raise SemanticError(f"Variável '{name}' usada sem ter sido declarada.")

        return self.symbols[name]

    def check_assignment(self, name, expr_type):
        var = self.check_declared(name)

        if var["type"] == expr_type:
            return None

        # Promoção simples permitida: INTEGER pode ser atribuído a REAL.
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

    def register_do_label(self, label):
        self.do_labels.add(int(label))

    def define_label(self, label):
        label = int(label)
        if label in self.labels:
            raise SemanticError(f"Label '{label}' definido mais do que uma vez.")
        self.labels.add(label)

    def register_goto(self, label):
        self.gotos.add(int(label))

    def validate_labels(self):
        missing_do = self.do_labels - self.labels
        if missing_do:
            raise SemanticError(
                f"Labels de DO sem CONTINUE correspondente: {sorted(missing_do)}"
            )

        missing_goto = self.gotos - self.labels
        if missing_goto:
            raise SemanticError(
                f"GOTO para labels não definidos: {sorted(missing_goto)}"
            )
