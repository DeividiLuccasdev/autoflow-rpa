# RPA com navegador real

Esta entrega adiciona um ERP fictício separado e um robô Python com Playwright. O robô lê a nota, abre o ERP, confere se já existe, preenche os campos, clica em Salvar, verifica o protocolo e recarrega a tela para confirmar persistência. Na segunda execução, não salva novamente. O lançamento não é feito por chamada direta à API: acontece pelo formulário HTML.

## Rodar no Windows

Na pasta backend:

```powershell
.venv\Scripts\python -m pip install -r requirements-rpa.txt
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m uvicorn simulators.erp:app --host 127.0.0.1 --port 8020
```

Em outro terminal, na mesma pasta, para ver o navegador trabalhando:

```powershell
.venv\Scripts\python -m rpa.run --headed
```

O ERP local fica em http://127.0.0.1:8020. Usa simulator.db com dados fictícios. As evidências ficam em rpa-evidence na raiz: captura do preenchimento, captura da confirmação, resultado JSON, vídeo WebM e trace Playwright. Execute novamente para verificar o estado already_present com o mesmo protocolo. Use outra pasta --output para preservar as evidências da primeira execução.

```powershell
.venv\Scripts\python -m playwright show-trace ../rpa-evidence/trace.zip
```

## Garantias e limites

O robô aceita somente endereço loopback e bloqueia requisições do navegador para outras origens. O ERP é apenas local, sem autenticação, e não é incluído nas rotas da API publicada. Não publique esse simulador na internet. A restrição única no SQLite bloqueia notas repetidas. Em falhas, o robô guarda evidência unconfirmed e não repete automaticamente o clique em salvar. A próxima execução consulta a tela antes de salvar.

O CI possui um job dedicado que inicia um servidor efêmero, executa Chromium headless e verifica a primeira gravação e a segunda execução sem duplicidade. Publica um artefato com capturas, resultados, vídeos e traces de dados fictícios. Chromium e Playwright são dependências opcionais em requirements-rpa.txt e não serão instalados no Render gratuito. A demonstração pública continua baseada nos adaptadores simulados do backend. A execução do navegador na hospedagem pública ainda não está implementada.
