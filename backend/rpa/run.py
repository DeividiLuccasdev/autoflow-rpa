"""Robô real Playwright para o ERP fictício local; nunca chama a API de lançamento."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
from app.documents import extract_invoice

def run(pdf: Path, base_url: str, output: Path, headed=False):
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("O robô só pode operar o ERP fictício em HTTP loopback")
    invoice = extract_invoice(pdf.read_bytes())
    output.mkdir(parents=True, exist_ok=True)
    events = []
    def event(action):
        events.append({"action": action, "time": datetime.now(timezone.utc).isoformat()})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed, slow_mo=150)
        context = browser.new_context(viewport={"width":1280,"height":850}, record_video_dir=str(output / "video"), record_video_size={"width":1280,"height":850})
        context.tracing.start(screenshots=True, snapshots=True)
        page = context.new_page()
        page.set_default_timeout(15000)
        # Bloqueia qualquer saída do navegador para hosts externos, inclusive redirects.
        def restrict(route):
            url = urlsplit(route.request.url)
            if url.scheme == "http" and url.hostname == parsed.hostname and url.port == parsed.port:
                route.continue_()
            else:
                route.abort()
        context.route("**/*", restrict)
        result = None
        try:
            page.goto(base_url, wait_until="domcontentloaded")
            expect(page.get_by_role("heading", name="Orbit Finance", exact=True)).to_be_visible()
            event("ERP fictício aberto pelo navegador")
            row = page.get_by_test_id(f"invoice-{invoice.issuer_cnpj}-{invoice.number}-{invoice.series}")
            if row.count() == 0:
                page.get_by_label("CNPJ emitente").fill(invoice.issuer_cnpj)
                page.get_by_label("Número da nota").fill(invoice.number)
                page.get_by_label("Série", exact=True).fill(invoice.series)
                page.get_by_label("Valor total").fill(str(invoice.amount))
                event("Campos preenchidos pela interface")
                page.screenshot(path=str(output / "01-preenchimento.png"), full_page=True)
                page.get_by_role("button", name="Salvar lançamento").click()
                expect(page.get_by_role("status")).to_contain_text("confirmad")
                event("Salvar acionado e confirmação recebida")
                state = "completed"
            else:
                state = "already_present"
                event("Nota já existente; nenhum novo clique em salvar")
            expect(row).to_have_count(1)
            expect(row).to_contain_text(f"R$ {invoice.amount:.2f}")
            protocol = row.locator("td").nth(4).inner_text()
            if not protocol.startswith("RPA-"):
                raise RuntimeError("Protocolo de confirmação ausente")
            page.reload(wait_until="domcontentloaded")
            expect(row).to_contain_text(protocol)
            event("Persistência conferida após recarregar a tela")
            page.screenshot(path=str(output / "02-confirmacao.png"), full_page=True)
            result = {"status":state,"protocol":protocol,"invoice":invoice.model_dump(mode="json"),"events":events}
            (output / "result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            return result
        finally:
            if result is None:
                page.screenshot(path=str(output / "erro.png"), full_page=True)
                (output / "failure.json").write_text(json.dumps({"status":"unconfirmed","events":events},ensure_ascii=False,indent=2),encoding="utf-8")
            context.tracing.stop(path=str(output / "trace.zip"))
            context.close()
            browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RPA real sobre ERP fictício local")
    parser.add_argument("--pdf", type=Path, default=Path("app/static/nota-ficticia.pdf"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8020")
    parser.add_argument("--output", type=Path, default=Path("../rpa-evidence"))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.pdf,args.base_url,args.output,args.headed),ensure_ascii=False,indent=2))
