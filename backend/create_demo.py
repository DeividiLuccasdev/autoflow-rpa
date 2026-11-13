"""Gera um PDF fictício para experimentar o upload pelo Swagger."""

from pathlib import Path

import pymupdf

target = Path(__file__).resolve().parent.parent / "examples" / "nota-ficticia.pdf"
target.parent.mkdir(exist_ok=True)
with pymupdf.open() as document:
    page = document.new_page()
    page.draw_rect((40, 40, 555, 155), color=None, fill=(0.04, 0.12, 0.22))
    page.insert_text((60, 85), "AutoFlow RPA", fontsize=26, color=(1, 1, 1))
    page.insert_text((60, 120), "DOCUMENTO FICTICIO - SEM VALOR FISCAL", fontsize=12, color=(0.6, 0.85, 1))
    page.insert_text((60, 200), "NovaTech Servicos | Demonstracao financeira", fontsize=15)
    page.insert_text(
        (60, 250),
        "CNPJ emitente: 12.345.678/0001-95\nNumero: 42\nSerie: 1\nValor total: 123.45",
        fontsize=14,
        lineheight=2,
    )
    page.insert_text(
        (60, 440),
        "Uso exclusivo no ambiente local de portfolio.\nDados sinteticos para validar extracao e duplicidade.",
        fontsize=11,
        lineheight=1.6,
    )
    document.save(target)
print(target)
