import json
import os
import re
import subprocess
from pathlib import Path

commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
if not re.fullmatch("[a-f0-9]{40}", commit):
    raise SystemExit("Invalid commit")
repo = os.environ["IMAGE_REPOSITORY"]
release = {"commit": commit}
if not re.fullmatch(r"[a-z0-9][a-z0-9./:_-]+", repo):
    raise SystemExit("Invalid registry repository")
for component in ["backend", "frontend"]:
    digest = json.loads(Path(f"build/{component}-metadata.json").read_text())[
        "containerimage.digest"
    ]
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise SystemExit("Missing immutable digest")
    release[component] = f"{repo}/{component}@{digest}"
Path("build/release.json").write_text(json.dumps(release, indent=2) + "\n")
