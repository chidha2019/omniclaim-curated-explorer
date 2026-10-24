import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
for name, source in [
    ("nginx.conf", "frontend/nginx.conf"),
    ("collector.yaml", "observability/collector.yaml"),
    ("alerts.yaml", "observability/alerts.yaml"),
]:
    if (ROOT / "deploy/chart/files" / name).read_bytes() != (
        ROOT / source
    ).read_bytes():
        raise SystemExit("Chart file drift: " + name)
for item in ROOT.rglob("*.json"):
    if any(
        x in item.parts
        for x in ["node_modules", ".venv", "dist", "validation", "build"]
    ):
        continue
    json.loads(item.read_text())
helm = os.environ.get("HELM_BINARY", "helm")
for env in ["staging", "production"]:
    args = [
        helm,
        "template",
        "explorer",
        str(ROOT / "deploy/chart"),
        "-n",
        "omniclaim-" + env,
        "-f",
        str(ROOT / f"deploy/environments/{env}.example.yaml"),
        "--set",
        "app.version=validation",
        "--set",
        "api.image=example/api@sha256:" + "a" * 64,
        "--set",
        "web.image=example/web@sha256:" + "b" * 64,
    ]
    resources = list(yaml.safe_load_all(subprocess.check_output(args, text=True)))
    kinds = {r["kind"] for r in resources}
    assert {
        "Deployment",
        "StatefulSet",
        "HTTPRoute",
        "NetworkPolicy",
        "CronJob",
        "PrometheusRule",
        "Probe",
    } <= kinds
    for resource in resources:
        if resource["kind"] in {"Deployment", "StatefulSet"}:
            pod = resource["spec"]["template"]["spec"]
            assert not pod["automountServiceAccountToken"]
            for c in pod["containers"]:
                assert (
                    c["securityContext"]["readOnlyRootFilesystem"]
                    and not c["securityContext"]["allowPrivilegeEscalation"]
                )
                assert (
                    c["resources"]["limits"]
                    and c["readinessProbe"]
                    and c["livenessProbe"]
                )
        if resource["kind"] == "PrometheusRule":
            for group in resource["spec"]["groups"]:
                for rule in group["rules"]:
                    assert "__NAMESPACE__" not in rule["expr"]
print(
    "Helm resources, locked assets and JSON contracts validated for staging and production"
)
