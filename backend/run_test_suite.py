"""Runner compartilhado por Docker e CI. Skip também resulta em falha."""

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

if not os.getenv("TEST_POSTGRES_URL") or not os.getenv("TEST_REDIS_URL"):
    sys.exit("PostgreSQL e Redis de teste são obrigatórios; execute python scripts/test_all.py na raiz.")
database = urlsplit(os.environ["TEST_POSTGRES_URL"])
broker = urlsplit(os.environ["TEST_REDIS_URL"])
if (
    database.scheme != "postgresql+psycopg"
    or database.hostname not in {"localhost", "127.0.0.1", "postgres", "request-db"}
    or not database.path.endswith("_test")
):
    sys.exit("Banco recusado: PostgreSQL local/container dedicado e nome terminado em _test obrigatórios.")
if (
    broker.scheme != "redis"
    or broker.hostname not in {"localhost", "127.0.0.1", "redis", "request-redis"}
    or broker.path != "/15"
):
    sys.exit("Redis recusado: serviço local/container dedicado no banco 15 obrigatório.")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["RUN_RPA_TESTS"] = "1"
report = Path("test-results.xml")
coverage = Path("coverage.xml")
result = subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        f"--junitxml={report}",
        "--cov=app",
        "--cov-report=term-missing:skip-covered",
        f"--cov-report=xml:{coverage}",
    ]
)
if result.returncode:
    sys.exit(result.returncode)
suites = list(ET.parse(report).getroot().iter("testsuite"))
if any(int(suite.get("skipped", "0")) for suite in suites):
    sys.exit("Suíte incompleta: testes pulados são proibidos neste runner.")

# Resumo no GitHub Actions; fora do CI a variável não existe e nada é escrito.
if summary := os.getenv("GITHUB_STEP_SUMMARY"):
    total = sum(int(suite.get("tests", "0")) for suite in suites)
    rate = float(ET.parse(coverage).getroot().get("line-rate", "0")) * 100
    with open(summary, "a", encoding="utf-8") as output:
        output.write(f"### Testes\n\n{total} testes aprovados, 0 pulados · cobertura de linhas de `app`: {rate:.1f}%\n")
