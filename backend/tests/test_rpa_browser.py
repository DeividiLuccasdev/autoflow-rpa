import os
import socket
import threading
from pathlib import Path
import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_RPA_TESTS") != "1", reason="RPA exige Chromium instalado")

@pytest.mark.parametrize("url", ["https://example.com", "http://127.0.0.1.evil.example:8020", "file:///tmp/erp", "http://user:password@localhost:8020"])
def test_robot_rejects_nonlocal_or_authenticated_targets(tmp_path, url):
    from rpa.run import run
    with pytest.raises(ValueError, match="loopback"):
        run(tmp_path / "missing.pdf",url,tmp_path / "evidence")

def test_browser_saves_confirms_and_skips_duplicate(tmp_path, monkeypatch):
    import uvicorn
    from simulators.erp import app
    from rpa.run import run
    monkeypatch.setenv("RPA_SIM_DB", str(tmp_path / "erp.db"))
    listener = socket.socket()
    listener.bind(("127.0.0.1",0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app,log_level="error"))
    thread = threading.Thread(target=server.run,kwargs={"sockets":[listener]},daemon=True)
    thread.start()
    import time
    deadline = time.monotonic()+10
    while not server.started and thread.is_alive() and time.monotonic()<deadline:
        time.sleep(.05)
    assert server.started
    try:
        pdf = Path(__file__).resolve().parents[1] / "app/static/nota-ficticia.pdf"
        first = run(pdf,f"http://127.0.0.1:{port}",tmp_path / "first")
        second = run(pdf,f"http://127.0.0.1:{port}",tmp_path / "second")
        assert first["status"] == "completed"
        assert second["status"] == "already_present"
        assert first["protocol"] == second["protocol"]
        assert (tmp_path / "first/trace.zip").is_file()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
