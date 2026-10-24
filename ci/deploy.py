"""Promote signed immutable digests; roll back only this application's Helm release."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

import yaml

parser = argparse.ArgumentParser()
parser.add_argument("environment", choices=["staging", "production"])
parser.add_argument("--rollback", action="store_true")
a = parser.parse_args()
namespace = "omniclaim-" + a.environment
release = "explorer"
history_file = Path(f"build/previous-{a.environment}.json")


def run(args, **kw):
    return subprocess.run(args, check=True, **kw)


if a.rollback:
    previous = json.loads(history_file.read_text())["revision"]
    if previous:
        run(
            [
                "helm",
                "rollback",
                release,
                str(previous),
                "-n",
                namespace,
                "--wait",
                "--timeout",
                "5m",
            ]
        )
    else:
        run(
            ["helm", "uninstall", release, "-n", namespace, "--wait", "--timeout", "5m"]
        )
    raise SystemExit(0)
values = Path(os.environ["DEPLOY_VALUES"])
data = yaml.safe_load(values.read_text())
if data["app"]["environment"] != a.environment:
    raise SystemExit("Environment mismatch")
text = values.read_text()
if any(
    t in text
    for t in ["example.invalid", "REPLACE_ACCOUNT", "192.0.2.0/24", "198.51.100.0/24"]
):
    raise SystemExit("Replace documentation placeholders before deploying")
release_data = json.loads(Path("build/release.json").read_text())
for component in ["backend", "frontend"]:
    image = release_data[component]
    if not re.fullmatch(r"[^ ]+@sha256:[a-f0-9]{64}", image):
        raise SystemExit("Image digest required")
    run(
        ["cosign", "verify", "--key", os.environ["COSIGN_PUBLIC_KEY"], image],
        stdout=subprocess.DEVNULL,
    )
overrides = {
    "app": {"version": release_data["commit"]},
    "api": {"image": release_data["backend"]},
    "web": {"image": release_data["frontend"]},
}
Path("build/images.yaml").write_text(yaml.safe_dump(overrides))
# A failed history lookup is not assumed to mean first deployment. List releases first.
existing = json.loads(
    subprocess.check_output(
        ["helm", "list", "-n", namespace, "--all", "-o", "json"], text=True
    )
)
owned = next((r for r in existing if r["name"] == release), None)
if owned and owned["status"] != "deployed":
    raise SystemExit(
        "Existing release is not deployed; inspect/recover it before promotion"
    )
history_file.write_text(
    json.dumps({"revision": int(owned["revision"]) if owned else None})
)
args = [
    "helm",
    "template",
    release,
    "deploy/chart",
    "-n",
    namespace,
    "-f",
    str(values),
    "-f",
    "build/images.yaml",
]
rendered = subprocess.check_output(args)
# Cluster-side CRD/schema/admission validation is mandatory; no skipped unknown resources.
run(
    ["kubectl", "apply", "--dry-run=server", "-n", namespace, "-f", "-"],
    input=rendered,
    stdout=subprocess.DEVNULL,
)
run(
    [
        "helm",
        "upgrade",
        "--install",
        release,
        "deploy/chart",
        "-n",
        namespace,
        "-f",
        str(values),
        "-f",
        "build/images.yaml",
        "--atomic",
        "--wait",
        "--timeout",
        "5m",
        "--history-max",
        "10",
    ]
)
# Fail closed if Gateway API controller has not accepted the route and resolved the backend.
try:
    run(
        [
            "kubectl",
            "wait",
            "httproute/" + release,
            "-n",
            namespace,
            '--for=jsonpath={.status.parents[0].conditions[?(@.type=="Accepted")].status}=True',
            "--timeout=120s",
        ]
    )
    run(
        [
            "kubectl",
            "wait",
            "httproute/" + release,
            "-n",
            namespace,
            '--for=jsonpath={.status.parents[0].conditions[?(@.type=="ResolvedRefs")].status}=True',
            "--timeout=120s",
        ]
    )
except subprocess.CalledProcessError:
    previous = json.loads(history_file.read_text())["revision"]
    if previous:
        run(
            [
                "helm",
                "rollback",
                release,
                str(previous),
                "-n",
                namespace,
                "--wait",
                "--timeout",
                "5m",
            ]
        )
    else:
        run(
            ["helm", "uninstall", release, "-n", namespace, "--wait", "--timeout", "5m"]
        )
    raise
