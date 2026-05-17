import ply.lex as lex

# Palavras reservadas suportadas pelo subconjunto Fortran 77 do projeto.
reserved = {
    "PROGRAM": "PROGRAM",
    "INTEGER": "INTEGER",
    "REAL": "REAL",
    "LOGICAL": "LOGICAL",
    "FUNCTION": "FUNCTION",
    "RETURN": "RETURN",
    "IF": "IF",
    "THEN": "THEN",
    "ELSE": "ELSE",
    "ENDIF": "ENDIF",
    "DO": "DO",
    "CONTINUE": "CONTINUE",
    "GOTO": "GOTO",
    "END": "END",
    "READ": "READ",
    "PRINT": "PRINT",
    "MOD": "MOD",
    "TRUE": "TRUE",
    "FALSE": "FALSE",
}

tokens = (
    "IDENTIFIER",
    "NUMBER",
    "REAL_NUMBER",
    "STRING",
    "PLUS",
    "MINUS",
    "TIMES",
    "DIVIDE",
    "EQ",
    "RELOP",
    "LOGOP",
    "NOT",
    "COMMA",
    "LPAREN",
    "RPAREN",
    "SEMICOLON",
    "NEWLINE",
) + tuple(set(reserved.values()))

# Espaços e tabs não são relevantes. As quebras de linha são tokens porque
# Fortran é uma linguagem orientada a linhas e isso evita ambiguidades no parser.
t_ignore = " \t\r"


def t_COMMENT(t):
    r"!.*"
    pass


def t_TRUE(t):
    r"(?i:\.TRUE\.)"
    t.value = 1
    return t


def t_FALSE(t):
    r"(?i:\.FALSE\.)"
    t.value = 0
    return t


def t_LOGOP(t):
    r"(?i:\.AND\.|\.OR\.)"
    t.value = t.value.upper()
    return t


def t_NOT(t):
    r"(?i:\.NOT\.)"
    t.value = t.value.upper()
    return t


def t_RELOP(t):
    r"(?i:\.EQ\.|\.NE\.|\.LT\.|\.LE\.|\.GT\.|\.GE\.)|<=|>=|<|>"
    t.value = t.value.upper()
    return t


def t_REAL_NUMBER(t):
    r"(\d+\.\d*|\d*\.\d+)([Ee][+-]?\d+)?|\d+[Ee][+-]?\d+"
    t.value = float(t.value)
    return t


def t_NUMBER(t):
    r"\d+"
    t.value = int(t.value)
    return t


def t_STRING(t):
    r"'([^']|'')*'"
    # Remove as aspas exteriores e converte '' em '.
    t.value = t.value[1:-1].replace("''", "'")
    return t


t_PLUS = r"\+"
t_MINUS = r"-"
t_TIMES = r"\*"
t_DIVIDE = r"/"
t_EQ = r"="
t_COMMA = r","
t_LPAREN = r"\("
t_RPAREN = r"\)"
t_SEMICOLON = r";"


def t_IDENTIFIER(t):
    r"[A-Za-z][A-Za-z0-9_]*"
    value = t.value.upper()
    t.type = reserved.get(value, "IDENTIFIER")
    t.value = value
    return t


def t_NEWLINE(t):
    r"\n+"
    t.lexer.lineno += len(t.value)
    return t


def t_error(t):
    raise SyntaxError(f"Caractere ilegal '{t.value[0]}' na linha {t.lexer.lineno}")


lexer = lex.lex()
