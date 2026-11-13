"""Regera os quatro PDFs e o extrato fictício da conciliação em lote."""
from pathlib import Path
import pymupdf

target = Path(__file__).resolve().parents[1] / "backend/app/static/batch-samples"
target.mkdir(exist_ok=True)
for number, amount in [(101, "123.45"), (102, "200.00"), (103, "300.00"), (104, "87.65")]:
    path = target / f"nota-{number}.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((55, 70), "AUTOFLOW - DOCUMENTO FICTICIO / DEMONSTRACAO", fontsize=13)
        page.insert_text((55, 120), f"CNPJ emitente: 12.345.678/0001-95\nNumero: {number}\nSerie: 1\nValor total: {amount}", fontsize=12)
        page.insert_text((55, 240), "Sem valor fiscal. Sem pagamento ou lancamento em sistemas reais.", fontsize=10)
        document.save(path)
(target / "extrato.csv").write_text("cnpj,numero,serie,valor\n12.345.678/0001-95,101,1,123.45\n12.345.678/0001-95,102,1,210.00\n12.345.678/0001-95,104,1,87.65\n12.345.678/0001-95,999,1,50.00\n", encoding="utf-8")
print("Quatro notas e um extrato fictício gerados.")
