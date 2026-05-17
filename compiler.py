import sys

from parser import parse_code
from translator import Translator


def compile_file(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        source = f.read()

    ast = parse_code(source)

    if ast is None:
        print("Compilação interrompida.")
        return False

    translator = Translator()
    vm_code = translator.translate(ast)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(vm_code)

    print(f"Código VM gerado em: {output_path}")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python3 compiler.py input.f77 output.vm")
        sys.exit(1)

    sys.exit(0 if compile_file(sys.argv[1], sys.argv[2]) else 1)
