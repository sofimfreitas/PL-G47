from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
COMPILER = ROOT / "compiler.py"


def run_compiler(source, output):
    return subprocess.run(
        [sys.executable, str(COMPILER), str(source), str(output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def assert_valid_tests():
    valid_sources = sorted((TESTS / "valid").glob("*.f77"))

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        for source in valid_sources:
            generated = tmpdir / f"{source.stem}.vm"
            expected = TESTS / "output" / f"{source.stem}.vm"

            result = run_compiler(source, generated)
            if result.returncode != 0:
                print(result.stdout)
                raise AssertionError(f"{source.name} devia compilar com sucesso")

            if not expected.exists():
                raise AssertionError(f"Falta o ficheiro esperado {expected}")

            if generated.read_text() != expected.read_text():
                raise AssertionError(f"Output VM diferente para {source.name}")


def assert_invalid_tests():
    invalid_sources = sorted((TESTS / "invalid").glob("*.f77"))

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        for source in invalid_sources:
            result = run_compiler(source, tmpdir / f"{source.stem}.vm")
            if result.returncode == 0:
                raise AssertionError(f"{source.name} devia falhar")


def main():
    assert_valid_tests()
    assert_invalid_tests()
    print("Todos os testes passaram.")


if __name__ == "__main__":
    main()
