"""Comando único: infraestrutura descartável e todos os testes, sem skips."""

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
command = ["docker", "compose", "-f", str(root / "compose.test.yaml"), "-p", "autoflow-tests-" + uuid4().hex[:10]]
if subprocess.run(["docker", "info"], capture_output=True).returncode:
    sys.exit("Docker Desktop indisponível ou sem permissão. Inicie o Docker para executar o ambiente isolado.")
try:
    result = subprocess.run(
        [*command, "up", "--build", "--abort-on-container-exit", "--exit-code-from", "tests"], cwd=root
    )
finally:
    subprocess.run([*command, "down", "--volumes", "--remove-orphans"], cwd=root, check=True)
sys.exit(result.returncode)
