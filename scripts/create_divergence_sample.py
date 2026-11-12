"""Gera a fixture sintética da nota 43 usada no cenário de revisão."""
from pathlib import Path
import pymupdf

target = Path(__file__).resolve().parents[1] / "backend/app/static/nota-divergente.pdf"
with pymupdf.open() as pdf:
    page = pdf.new_page()
    page.insert_text((60, 70), "AUTOFLOW - DOCUMENTO FICTICIO PARA DEMONSTRACAO", fontsize=13)
    page.insert_text((60, 120), "CNPJ emitente: 12.345.678/0001-95\nNumero: 43\nSerie: 1\nValor total: 123.45", fontsize=12)
    page.insert_text((60, 240), "Sem valor fiscal. A origem simulada informa 150.00 para demonstrar revisao humana.", fontsize=10)
    pdf.save(target)
print(target.name)
