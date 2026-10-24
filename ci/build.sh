#!/usr/bin/env bash
set -euo pipefail
: "${IMAGE_REPOSITORY:?Registry hostname plus repository prefix required}"
: "${COSIGN_KEY_REF:?Use a KMS/HSM key reference; no plaintext private key in the workspace}"
mkdir -p build
commit="$(git rev-parse HEAD)"
for component in backend frontend; do
  image="${IMAGE_REPOSITORY}/${component}:${commit}"
  docker buildx build --platform linux/amd64 --provenance=mode=max --sbom=true --push --label "org.opencontainers.image.revision=$commit" \
    --metadata-file "build/${component}-metadata.json" --tag "$image" "$component"
done
.venv/bin/python ci/release_manifest.py
for component in backend frontend; do
  ref="$(.venv/bin/python -c 'import json,sys; print(json.load(open("build/release.json"))[sys.argv[1]])' "$component")"
  trivy image --image-src remote --severity HIGH,CRITICAL --exit-code 1 "$ref"
  trivy image --image-src remote --format cyclonedx --output "build/${component}.cdx.json" "$ref"
  cosign sign --yes --key "$COSIGN_KEY_REF" "$ref"
  cosign attest --yes --key "$COSIGN_KEY_REF" --type cyclonedx --predicate "build/${component}.cdx.json" "$ref"
done
