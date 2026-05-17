# Compilador Fortran 77 para VM

- José Miguel Paredes Sampaio - a106908
- José Pedro Joaquim Pereira - a106874
- Sofia Margarida Rodrigues Freitas - a106798

## Objetivo

Compilador em Python, com PLY, para um subconjunto de Fortran 77. O projeto faz análise léxica, análise sintática, análise semântica e tradução direta para a máquina virtual da UC.

## Funcionalidades suportadas

- `PROGRAM ... END`
- Declarações `INTEGER`, `REAL` e `LOGICAL`
- Variáveis escalares e arrays unidimensionais
- Expressões aritméticas com `+`, `-`, `*`, `/` e `MOD`
- Expressões relacionais com `.EQ.`, `.NE.`, `.LT.`, `.LE.`, `.GT.`, `.GE.` e equivalentes simbólicos
- Expressões lógicas com `.AND.`, `.OR.`, `.NOT.`, `.TRUE.` e `.FALSE.`
- `PRINT *, ...` e `READ *, ...`
- `IF ... THEN ... ELSE ... ENDIF`
- `DO label var = inicio, fim[, passo] ... label CONTINUE`
- `GOTO label`

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Compilação

```bash
python3 compiler.py tests/valid/somaarr.f77 tests/output/somaarr.vm
```

## Testes

```bash
python3 tests/run_tests.py
```

- `tests/valid/`: programas que devem compilar
- `tests/invalid/`: programas que devem falhar
- `tests/output/`: código VM esperado para os programas válidos

## Estrutura

- `lexer.py`: analisador léxico
- `parser.py`: gramática e construção da AST
- `semantic_analyzer.py`: validações semânticas
- `translator.py`: geração de código VM
- `compiler.py`: interface de linha de comando
- `tests/`: testes e outputs esperados

