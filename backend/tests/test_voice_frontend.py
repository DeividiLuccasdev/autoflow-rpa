import shutil
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path


def test_live_transcription_and_manual_edit_regressions():
    node = shutil.which("node")
    if not node:
        # O ambiente completo já inclui o Node distribuído com Playwright.
        spec = find_spec("playwright")
        if spec and spec.origin:
            bundled = Path(spec.origin).parent / "driver" / ("node.exe" if sys.platform == "win32" else "node")
            if bundled.is_file():
                node = str(bundled)
    assert node, "Instale Node.js ou requirements-rpa.txt para validar a interface de voz"
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("voice_frontend.test.cjs"))],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
