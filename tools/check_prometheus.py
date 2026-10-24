import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="omniclaim-alerts-") as tmp:
    directory = Path(tmp)
    (directory / "rules-under-test.yaml").write_text(
        (ROOT / "observability/alerts.yaml")
        .read_text()
        .replace("__NAMESPACE__", "test")
    )
    (directory / "tests.yaml").write_text(
        (ROOT / "observability/alert-tests.yaml").read_text()
    )
    binary = os.environ.get("PROMTOOL_BINARY", "promtool")
    subprocess.run(
        [binary, "check", "rules", "rules-under-test.yaml"], cwd=directory, check=True
    )
    subprocess.run([binary, "test", "rules", "tests.yaml"], cwd=directory, check=True)
