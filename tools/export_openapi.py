import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.main import create_app

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
app = create_app(
    Settings(environment="test", policy_file=ROOT / "config/access-policy.example.json")
)
result = json.dumps(app.openapi(), indent=2) + "\n"
path = ROOT / "contracts/openapi.json"
if args.check:
    if path.read_text() != result:
        raise SystemExit("OpenAPI drift: run python tools/export_openapi.py")
else:
    path.write_text(result)
