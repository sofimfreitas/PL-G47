import ply.lex as ply_lex
import ply.yacc as yacc

import lexer as lexer_module
from lexer import tokens
from semantic_analyzer import SemanticAnalyzer, SemanticError

semantic = SemanticAnalyzer()


def cast_expression(expr, target_type):
    if expr["type"] == target_type:
        return expr
    if expr["type"] == "INTEGER" and target_type == "REAL":
        return {
            "node": "cast",
            "to": "REAL",
            "expr": expr,
            "type": "REAL",
        }
    raise SemanticError(f"Conversão implícita inválida de {expr['type']} para {target_type}.")


def ensure_numeric(expr):
    if expr["type"] not in ("INTEGER", "REAL"):
        raise SemanticError("Expressões aritméticas só podem usar INTEGER ou REAL.")


def make_arithmetic(op, left, right):
    ensure_numeric(left)
    ensure_numeric(right)

    if op == "MOD":
        if left["type"] != "INTEGER" or right["type"] != "INTEGER":
            raise SemanticError("MOD só pode ser usado com valores INTEGER.")
        result_type = "INTEGER"
    elif left["type"] == "REAL" or right["type"] == "REAL":
        result_type = "REAL"
        left = cast_expression(left, "REAL")
        right = cast_expression(right, "REAL")
    else:
        result_type = "INTEGER"

    return {
        "node": "binary_expression",
        "op": op,
        "left": left,
        "right": right,
        "type": result_type,
    }


def make_relational(op, left, right):
    if left["type"] in ("INTEGER", "REAL") and right["type"] in ("INTEGER", "REAL"):
        if left["type"] == "REAL" or right["type"] == "REAL":
            left = cast_expression(left, "REAL")
            right = cast_expression(right, "REAL")
    elif left["type"] != right["type"]:
        raise SemanticError("Comparação entre tipos incompatíveis.")

    return {
        "node": "condition",
        "op": op,
        "left": left,
        "right": right,
        "type": "LOGICAL",
    }


def labelled_statement(label, stmt):
    semantic.define_label(label)
    return {
        "node": "labelled",
        "label": int(label),
        "statement": stmt,
    }


precedence = (
    ("left", "LOGOP"),
    ("right", "NOT"),
    ("nonassoc", "RELOP", "EQ"),
    ("left", "PLUS", "MINUS"),
    ("left", "TIMES", "DIVIDE", "MOD"),
    ("right", "UMINUS"),
)


# ─────────────────────────────────────────────
#  Programa e linhas
# ─────────────────────────────────────────────

def p_program(p):
    """
    program : opt_newlines PROGRAM IDENTIFIER line_end declarations statements END opt_program_name opt_newlines
    """
    semantic.validate_labels()
    p[0] = {
        "node": "program",
        "name": p[3],
        "declarations": p[5],
        "statements": p[6],
    }
    print(f"Programa '{p[3]}' válido.")


def p_opt_program_name(p):
    """
    opt_program_name : IDENTIFIER
                     | empty
    """
    p[0] = p[1]


def p_line_end(p):
    """
    line_end : NEWLINE
             | SEMICOLON
             | SEMICOLON NEWLINE
    """
    p[0] = None


def p_opt_newlines_many(p):
    """
    opt_newlines : opt_newlines NEWLINE
    """
    p[0] = None


def p_opt_newlines_empty(p):
    """
    opt_newlines : empty
    """
    p[0] = None


# ─────────────────────────────────────────────
#  Declarações
# ─────────────────────────────────────────────

def p_declarations_many(p):
    """
    declarations : declarations declaration_line
    """
    p[0] = p[1] + [p[2]]


def p_declarations_blank(p):
    """
    declarations : declarations NEWLINE
    """
    p[0] = p[1]


def p_declarations_empty(p):
    """
    declarations : empty
    """
    p[0] = []


def p_declaration_line(p):
    """
    declaration_line : type_spec var_list line_end
    """
    var_type = p[1]

    for name, size in p[2]:
        semantic.declare_variable(name, var_type, size)

    p[0] = {
        "node": "declaration",
        "type": var_type,
        "variables": p[2],
    }


def p_type_spec(p):
    """
    type_spec : INTEGER
              | REAL
              | LOGICAL
    """
    p[0] = p.slice[1].type


def p_var_list_many(p):
    """
    var_list : var_list COMMA var_decl
    """
    p[0] = p[1] + [p[3]]


def p_var_list_one(p):
    """
    var_list : var_decl
    """
    p[0] = [p[1]]


def p_var_decl_simple(p):
    """
    var_decl : IDENTIFIER
    """
    p[0] = (p[1], None)


def p_var_decl_array(p):
    """
    var_decl : IDENTIFIER LPAREN NUMBER RPAREN
    """
    p[0] = (p[1], int(p[3]))


# ─────────────────────────────────────────────
#  Statements
# ─────────────────────────────────────────────

def p_statements_many(p):
    """
    statements : statements statement
    """
    p[0] = p[1] + [p[2]]


def p_statements_blank(p):
    """
    statements : statements NEWLINE
    """
    p[0] = p[1]


def p_statements_empty(p):
    """
    statements : empty
    """
    p[0] = []


def p_statement_simple(p):
    """
    statement : simple_statement line_end
    """
    p[0] = p[1]


def p_statement_labelled_simple(p):
    """
    statement : NUMBER simple_statement line_end
    """
    p[0] = labelled_statement(p[1], p[2])


def p_statement_continue(p):
    """
    statement : CONTINUE line_end
    """
    p[0] = {"node": "continue"}


def p_statement_if(p):
    """
    statement : if_statement
    """
    p[0] = p[1]


def p_statement_labelled_if(p):
    """
    statement : NUMBER if_statement
    """
    p[0] = labelled_statement(p[1], p[2])


def p_statement_do(p):
    """
    statement : do_statement
    """
    p[0] = p[1]


def p_statement_labelled_do(p):
    """
    statement : NUMBER do_statement
    """
    p[0] = labelled_statement(p[1], p[2])


def p_simple_statement(p):
    """
    simple_statement : assignment
                     | print_statement
                     | read_statement
                     | goto_statement
    """
    p[0] = p[1]


# ── Atribuição ──────────────────────────────

def p_assignment(p):
    """
    assignment : variable EQ expression
    """
    coercion = semantic.check_assignment(p[1]["name"], p[3]["type"])
    value = cast_expression(p[3], coercion) if coercion else p[3]

    p[0] = {
        "node": "assignment",
        "target": p[1],
        "value": value,
    }


# ── PRINT *, ... ─────────────────────────────

def p_print_statement(p):
    """
    print_statement : PRINT TIMES COMMA print_list
    """
    p[0] = {
        "node": "print",
        "items": p[4],
    }


def p_print_list_many(p):
    """
    print_list : print_list COMMA print_item
    """
    p[0] = p[1] + [p[3]]


def p_print_list_one(p):
    """
    print_list : print_item
    """
    p[0] = [p[1]]


def p_print_item_string(p):
    """
    print_item : STRING
    """
    p[0] = {
        "node": "string",
        "type": "STRING",
        "value": p[1],
    }


def p_print_item_expr(p):
    """
    print_item : expression
    """
    p[0] = p[1]


# ── READ *, ... ──────────────────────────────

def p_read_statement(p):
    """
    read_statement : READ TIMES COMMA read_list
    """
    p[0] = {
        "node": "read",
        "items": p[4],
    }


def p_read_list_many(p):
    """
    read_list : read_list COMMA variable
    """
    p[0] = p[1] + [p[3]]


def p_read_list_one(p):
    """
    read_list : variable
    """
    p[0] = [p[1]]


# ── DO label var = start, end [, step] ... label CONTINUE ─

def p_do_statement(p):
    """
    do_statement : DO NUMBER IDENTIFIER EQ expression COMMA expression do_step line_end statements NUMBER CONTINUE line_end
    """
    do_label = int(p[2])
    cont_label = int(p[11])

    if do_label != cont_label:
        raise SyntaxError(f"Labels de DO ({do_label}) e CONTINUE ({cont_label}) não coincidem")

    var = semantic.check_declared(p[3])
    if var["type"] != "INTEGER":
        raise SemanticError("A variável de controlo do DO tem de ser INTEGER.")

    if p[5]["type"] != "INTEGER" or p[7]["type"] != "INTEGER" or p[8]["type"] != "INTEGER":
        raise SemanticError("Os limites e o passo do ciclo DO têm de ser INTEGER.")

    semantic.register_do_label(do_label)
    semantic.define_label(cont_label)

    p[0] = {
        "node": "do",
        "label": do_label,
        "var": p[3],
        "start": p[5],
        "end": p[7],
        "step": p[8],
        "body": p[10],
    }


def p_do_step_explicit(p):
    """
    do_step : COMMA expression
    """
    p[0] = p[2]


def p_do_step_empty(p):
    """
    do_step : empty
    """
    p[0] = {"node": "number", "value": 1, "type": "INTEGER"}


# ── GOTO label ───────────────────────────────

def p_goto_statement(p):
    """
    goto_statement : GOTO NUMBER
    """
    semantic.register_goto(p[2])
    p[0] = {
        "node": "goto",
        "label": int(p[2]),
    }


# ── IF (cond) THEN ... [ELSE ...] ENDIF ──────

def p_if_statement_no_else(p):
    """
    if_statement : IF LPAREN condition RPAREN THEN line_end statements endif_line
    """
    p[0] = {
        "node": "if",
        "condition": p[3],
        "then": p[7],
        "else": [],
    }


def p_if_statement_else(p):
    """
    if_statement : IF LPAREN condition RPAREN THEN line_end statements ELSE line_end statements endif_line
    """
    p[0] = {
        "node": "if",
        "condition": p[3],
        "then": p[7],
        "else": p[10],
    }


def p_endif_line_single_token(p):
    """
    endif_line : ENDIF line_end
    """
    p[0] = None


def p_endif_line_two_tokens(p):
    """
    endif_line : END IF line_end
    """
    p[0] = None


# ─────────────────────────────────────────────
#  Condições
# ─────────────────────────────────────────────

def p_condition_relational(p):
    """
    condition : expression relop expression
    """
    p[0] = make_relational(p[2], p[1], p[3])


def p_relop(p):
    """
    relop : RELOP
          | EQ
    """
    p[0] = p[1]


def p_condition_logical(p):
    """
    condition : condition LOGOP condition
    """
    if p[1]["type"] != "LOGICAL" or p[3]["type"] != "LOGICAL":
        raise SemanticError("Operadores lógicos só podem ser usados com LOGICAL.")

    p[0] = {
        "node": "logical_condition",
        "op": p[2],
        "left": p[1],
        "right": p[3],
        "type": "LOGICAL",
    }


def p_condition_not(p):
    """
    condition : NOT condition
    """
    if p[2]["type"] != "LOGICAL":
        raise SemanticError(".NOT. só pode ser usado com LOGICAL.")

    p[0] = {
        "node": "not_condition",
        "expr": p[2],
        "type": "LOGICAL",
    }


def p_condition_paren(p):
    """
    condition : LPAREN condition RPAREN
    """
    p[0] = p[2]


def p_condition_expression(p):
    """
    condition : expression
    """
    if p[1]["type"] != "LOGICAL":
        raise SemanticError("A condição do IF tem de ser LOGICAL ou relacional.")
    p[0] = p[1]


# ─────────────────────────────────────────────
#  Expressões
# ─────────────────────────────────────────────

def p_expression_binary(p):
    """
    expression : expression PLUS expression
               | expression MINUS expression
               | expression TIMES expression
               | expression DIVIDE expression
               | expression MOD expression
    """
    op = p[2]
    if p.slice[2].type == "MOD":
        op = "MOD"
    p[0] = make_arithmetic(op, p[1], p[3])


def p_expression_unary_minus(p):
    """
    expression : MINUS expression %prec UMINUS
    """
    ensure_numeric(p[2])
    p[0] = {
        "node": "unary_expression",
        "op": "-",
        "expr": p[2],
        "type": p[2]["type"],
    }


def p_expression_mod_function(p):
    """
    expression : MOD LPAREN expression COMMA expression RPAREN
    """
    p[0] = make_arithmetic("MOD", p[3], p[5])


def p_expression_number_int(p):
    """
    expression : NUMBER
    """
    p[0] = {
        "node": "number",
        "value": int(p[1]),
        "type": "INTEGER",
    }


def p_expression_number_real(p):
    """
    expression : REAL_NUMBER
    """
    p[0] = {
        "node": "real_number",
        "value": float(p[1]),
        "type": "REAL",
    }


def p_expression_true(p):
    """
    expression : TRUE
    """
    p[0] = {"node": "bool_literal", "value": 1, "type": "LOGICAL"}


def p_expression_false(p):
    """
    expression : FALSE
    """
    p[0] = {"node": "bool_literal", "value": 0, "type": "LOGICAL"}


def p_expression_variable(p):
    """
    expression : variable
    """
    p[0] = p[1]


def p_expression_paren(p):
    """
    expression : LPAREN expression RPAREN
    """
    p[0] = p[2]


# ─────────────────────────────────────────────
#  Variáveis e arrays
# ─────────────────────────────────────────────

def p_variable_simple(p):
    """
    variable : IDENTIFIER
    """
    var = semantic.check_declared(p[1])
    if var["size"] is not None:
        raise SemanticError(f"Array '{p[1]}' usado sem índice.")
    p[0] = {
        "node": "variable",
        "name": p[1],
        "type": var["type"],
        "size": var["size"],
    }


def p_variable_array(p):
    """
    variable : IDENTIFIER LPAREN expression RPAREN
    """
    var = semantic.check_array_access(p[1])

    if p[3]["type"] != "INTEGER":
        raise SemanticError("Índice de array deve ser INTEGER.")

    p[0] = {
        "node": "array_access",
        "name": p[1],
        "index": p[3],
        "type": var["type"],
        "size": var["size"],
    }


# ─────────────────────────────────────────────
#  Auxiliares
# ─────────────────────────────────────────────

def p_empty(p):
    """
    empty :
    """
    p[0] = []


def p_error(p):
    if p:
        print(f"Erro de sintaxe no token '{p.value}' (tipo: {p.type}, linha: {p.lineno})")
    else:
        print("Erro de sintaxe no fim da entrada.")


parser = yacc.yacc(debug=False, write_tables=False)


def preprocess_source(data):
    """Normaliza para free-form: ignora linhas vazias e espaços à volta das linhas."""
    lines = []
    for line in data.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("!"):
            continue
        lines.append(stripped)
    return "\n".join(lines) + "\n"


def parse_code(data):
    global semantic
    semantic = SemanticAnalyzer()

    fresh_lexer = ply_lex.lex(module=lexer_module)
    normalized = preprocess_source(data)

    try:
        result = parser.parse(normalized, lexer=fresh_lexer, debug=False)
        return result
    except SemanticError as e:
        print(f"Erro semântico: {e}")
        return None
    except SyntaxError as e:
        print(f"Erro sintático: {e}")
        return None
