import sys

from optimizer import optimize_ast
from parser import parse_code
from translator import Translator


def compile_file(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        source = f.read()

    ast = parse_code(source)

    if ast is None:
        print("Compilação interrompida.")
        return False

    optimized_ast, optimization_stats = optimize_ast(ast)
    if optimization_stats["total"] > 0:
        print(
            "Otimizações aplicadas: "
            f"{optimization_stats['total']} "
            f"(constantes: {optimization_stats['constant_folds']}, "
            f"simplificações: {optimization_stats['algebraic_simplifications']}, "
            f"atribuições removidas: {optimization_stats['removed_assignments']}, "
            f"ramos removidos: {optimization_stats['removed_branches']})"
        )

    translator = Translator()
    vm_code = translator.translate(optimized_ast)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(vm_code)

    print(f"Código VM gerado em: {output_path}")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python3 compiler.py input.f77 output.vm")
        sys.exit(1)

    sys.exit(0 if compile_file(sys.argv[1], sys.argv[2]) else 1)
