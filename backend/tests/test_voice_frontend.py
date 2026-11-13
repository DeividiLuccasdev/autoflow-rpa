import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which('node'), reason='Node.js não instalado')
def test_live_transcription_and_manual_edit_regressions():
    result = subprocess.run(
        [shutil.which('node'), '--test', str(Path(__file__).with_name('voice_frontend.test.cjs'))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
