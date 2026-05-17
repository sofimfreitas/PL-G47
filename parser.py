import re

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


def is_zero_integer_literal(expr):
    return expr["node"] == "number" and expr["value"] == 0


def labelled_statement(label, stmt):
    semantic.define_label(label)
    return {
        "node": "labelled",
        "label": int(label),
        "statement": stmt,
    }


def resolve_designator_as_variable(designator):
    name = designator["name"]
    args = designator["args"]

    if not args:
        var = semantic.check_declared(name)
        if var["size"] is not None:
            raise SemanticError(f"Array '{name}' usado sem índice.")
        return {
            "node": "variable",
            "name": name,
            "type": var["type"],
            "size": var["size"],
        }

    if semantic.is_function(name):
        raise SemanticError(f"Função '{name}' não pode ser usada como variável.")

    if len(args) != 1:
        raise SemanticError(f"Acesso a array '{name}' exige exatamente um índice.")

    var = semantic.check_array_access(name)
    if args[0]["type"] != "INTEGER":
        raise SemanticError("Índice de array deve ser INTEGER.")

    return {
        "node": "array_access",
        "name": name,
        "index": args[0],
        "type": var["type"],
        "size": var["size"],
    }


def resolve_designator_as_actual_argument(designator):
    name = designator["name"]
    args = designator["args"]

    if not args:
        var = semantic.check_declared(name)
        if var["size"] is not None:
            return {
                "node": "array_argument",
                "name": name,
                "type": var["type"],
                "size": var["size"],
            }
        return {
            "node": "variable",
            "name": name,
            "type": var["type"],
            "size": var["size"],
        }

    if semantic.is_function(name):
        return {
            "node": "function_call",
            "name": name,
            "args": args,
            "type": semantic.check_function_call(name, args),
        }

    if len(args) != 1:
        raise SemanticError(f"Acesso a array '{name}' exige exatamente um índice.")

    var = semantic.check_array_access(name)
    if args[0]["type"] != "INTEGER":
        raise SemanticError("Índice de array deve ser INTEGER.")

    return {
        "node": "array_access",
        "name": name,
        "index": args[0],
        "type": var["type"],
        "size": var["size"],
    }


def resolve_designator_as_expression(designator):
    name = designator["name"]
    args = designator["args"]

    if args and semantic.is_function(name):
        return {
            "node": "function_call",
            "name": name,
            "args": args,
            "type": semantic.check_function_call(name, args),
        }

    return resolve_designator_as_variable(designator)


precedence = (
    ("left", "LOGOP"),
    ("right", "NOT"),
    ("nonassoc", "RELOP", "EQ"),
    ("left", "PLUS", "MINUS"),
    ("left", "TIMES", "DIVIDE", "MOD"),
    ("right", "UMINUS"),
)


def p_program(p):
    """
    program : opt_newlines PROGRAM IDENTIFIER line_end declarations statements END opt_program_name opt_newlines subprograms opt_newlines
    """
    semantic.validate_labels()
    p[0] = {
        "node": "program",
        "name": p[3],
        "declarations": p[5],
        "statements": p[6],
        "subprograms": p[10],
    }
    print(f"Programa '{p[3]}' válido.")


def p_subprograms_many(p):
    """
    subprograms : subprograms subprogram
    """
    p[0] = p[1] + [p[2]]


def p_subprograms_blank(p):
    """
    subprograms : subprograms NEWLINE
    """
    p[0] = p[1]


def p_subprograms_empty(p):
    """
    subprograms : empty
    """
    p[0] = []


def p_function_definition(p):
    """
    function_definition : function_header declarations statements END opt_subprogram_name opt_newlines
    """
    semantic.finish_subprogram()
    p[0] = {
        "node": "function",
        "name": p[1]["name"],
        "return_type": p[1]["return_type"],
        "params": p[1]["params"],
        "declarations": p[2],
        "statements": p[3],
    }


def p_subroutine_definition(p):
    """
    subroutine_definition : subroutine_header declarations statements END opt_subprogram_name opt_newlines
    """
    semantic.finish_subprogram()
    p[0] = {
        "node": "subroutine",
        "name": p[1]["name"],
        "params": p[1]["params"],
        "declarations": p[2],
        "statements": p[3],
    }


def p_subprogram(p):
    """
    subprogram : function_definition
               | subroutine_definition
    """
    p[0] = p[1]


def p_subroutine_header_with_params(p):
    """
    subroutine_header : SUBROUTINE IDENTIFIER LPAREN parameter_names RPAREN line_end
    """
    semantic.start_subroutine(p[2], p[4])
    p[0] = {
        "name": p[2],
        "params": p[4],
    }


def p_subroutine_header_without_params(p):
    """
    subroutine_header : SUBROUTINE IDENTIFIER line_end
    """
    semantic.start_subroutine(p[2], [])
    p[0] = {
        "name": p[2],
        "params": [],
    }


def p_function_header(p):
    """
    function_header : type_spec FUNCTION IDENTIFIER LPAREN parameter_names RPAREN line_end
    """
    semantic.start_function(p[3], p[1], p[5])
    p[0] = {
        "name": p[3],
        "return_type": p[1],
        "params": p[5],
    }


def p_parameter_names_many(p):
    """
    parameter_names : parameter_names COMMA IDENTIFIER
    """
    p[0] = p[1] + [p[3]]


def p_parameter_names_one(p):
    """
    parameter_names : IDENTIFIER
    """
    p[0] = [p[1]]


def p_parameter_names_empty(p):
    """
    parameter_names : empty
    """
    p[0] = []


def p_opt_program_name(p):
    """
    opt_program_name : IDENTIFIER
                     | empty
    """
    p[0] = p[1]


def p_opt_subprogram_name(p):
    """
    opt_subprogram_name : IDENTIFIER
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
                     | call_statement
                     | return_statement
    """
    p[0] = p[1]


def p_assignment(p):
    """
    assignment : designator EQ expression
    """
    target = resolve_designator_as_variable(p[1])
    coercion = semantic.check_assignment(target["name"], p[3]["type"])
    value = cast_expression(p[3], coercion) if coercion else p[3]

    p[0] = {
        "node": "assignment",
        "target": target,
        "value": value,
    }


def p_return_statement(p):
    """
    return_statement : RETURN
    """
    p[0] = {"node": "return"}


def p_call_statement_with_args(p):
    """
    call_statement : CALL IDENTIFIER LPAREN actual_arguments RPAREN
    """
    semantic.check_subroutine_call(p[2], p[4])
    p[0] = {
        "node": "subroutine_call",
        "name": p[2],
        "args": p[4],
    }


def p_call_statement_without_args(p):
    """
    call_statement : CALL IDENTIFIER
    """
    semantic.check_subroutine_call(p[2], [])
    p[0] = {
        "node": "subroutine_call",
        "name": p[2],
        "args": [],
    }


def p_actual_arguments_list(p):
    """
    actual_arguments : actual_argument_list
    """
    p[0] = p[1]


def p_actual_arguments_empty(p):
    """
    actual_arguments : empty
    """
    p[0] = []


def p_actual_argument_list_many(p):
    """
    actual_argument_list : actual_argument_list COMMA designator
    """
    p[0] = p[1] + [resolve_designator_as_actual_argument(p[3])]


def p_actual_argument_list_one(p):
    """
    actual_argument_list : designator
    """
    p[0] = [resolve_designator_as_actual_argument(p[1])]


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
    read_list : read_list COMMA designator
    """
    p[0] = p[1] + [resolve_designator_as_variable(p[3])]


def p_read_list_one(p):
    """
    read_list : designator
    """
    p[0] = [resolve_designator_as_variable(p[1])]


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

    if is_zero_integer_literal(p[8]):
        raise SemanticError("O passo do ciclo DO não pode ser zero.")

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


def p_goto_statement(p):
    """
    goto_statement : GOTO NUMBER
    """
    semantic.register_goto(p[2])
    p[0] = {
        "node": "goto",
        "label": int(p[2]),
    }


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


def p_expression_relational(p):
    """
    expression : expression RELOP expression
               | expression EQ expression
    """
    p[0] = make_relational(p[2], p[1], p[3])


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


def p_expression_designator(p):
    """
    expression : designator
    """
    p[0] = resolve_designator_as_expression(p[1])


def p_expression_paren(p):
    """
    expression : LPAREN expression RPAREN
    """
    p[0] = p[2]


def p_designator_simple(p):
    """
    designator : IDENTIFIER
    """
    p[0] = {
        "name": p[1],
        "args": [],
    }


def p_designator_indexed_or_call(p):
    """
    designator : IDENTIFIER LPAREN expression_list RPAREN
    """
    p[0] = {
        "name": p[1],
        "args": p[3],
    }


def p_expression_list_many(p):
    """
    expression_list : expression_list COMMA expression
    """
    p[0] = p[1] + [p[3]]


def p_expression_list_one(p):
    """
    expression_list : expression
    """
    p[0] = [p[1]]


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
        # Comentários Fortran 77 em coluna 1. A condição do "C" não pode
        # eliminar instruções válidas como CALL ou CONTINUE em free-form.
        if line and line[0].upper() == "C" and (len(line) == 1 or line[1].isspace()):
            continue
        if line and line[0] == "*":
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("!"):
            continue
        lines.append(stripped)
    return "\n".join(lines) + "\n"


def predeclare_subprograms(normalized_source):
    function_pattern = re.compile(
        r"^(INTEGER|REAL|LOGICAL)\s+FUNCTION\s+([A-Z][A-Z0-9_]*)\s*\(([^)]*)\)$",
        re.IGNORECASE,
    )
    subroutine_pattern = re.compile(
        r"^SUBROUTINE\s+([A-Z][A-Z0-9_]*)(?:\s*\(([^)]*)\))?$",
        re.IGNORECASE,
    )

    for raw_line in normalized_source.splitlines():
        line = raw_line.strip()

        function_match = function_pattern.match(line)
        if function_match:
            return_type = function_match.group(1).upper()
            name = function_match.group(2).upper()
            raw_params = function_match.group(3).strip()
            params = []
            if raw_params:
                params = [param.strip().upper() for param in raw_params.split(",") if param.strip()]

            semantic.predeclare_function(name, return_type, params)
            continue

        subroutine_match = subroutine_pattern.match(line)
        if subroutine_match:
            name = subroutine_match.group(1).upper()
            raw_params = (subroutine_match.group(2) or "").strip()
            params = []
            if raw_params:
                params = [param.strip().upper() for param in raw_params.split(",") if param.strip()]

            semantic.predeclare_subroutine(name, params)


def parse_code(data):
    global semantic
    semantic = SemanticAnalyzer()

    fresh_lexer = ply_lex.lex(module=lexer_module)
    normalized = preprocess_source(data)
    predeclare_subprograms(normalized)

    try:
        result = parser.parse(normalized, lexer=fresh_lexer, debug=False)
        if result is not None:
            semantic.validate_subprogram_definitions()
        return result
    except SemanticError as e:
        print(f"Erro semântico: {e}")
        return None
    except SyntaxError as e:
        print(f"Erro sintático: {e}")
        return None
