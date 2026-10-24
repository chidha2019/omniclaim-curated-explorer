pipeline {
  agent { label 'omniclaim-linux' }
  options {
    skipDefaultCheckout(true)
    disableConcurrentBuilds()
    timestamps()
    timeout(time: 90, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '15'))
  }
  parameters { booleanParam(name: 'PROMOTE_PRODUCTION', defaultValue: false, description: 'Promote the tested image digests after release approval') }
  environment { CI = 'true' }
  stages {
    stage('Checkout') { steps { deleteDir(); checkout scm } }
    stage('Install locked dependencies') {
      steps { sh '''set -eu
        python3 -m venv .venv
        .venv/bin/pip install --require-hashes -r backend/requirements-dev.lock
        npm --prefix frontend ci --ignore-scripts --no-audit --no-fund
      ''' }
    }
    stage('Code, contracts and tests') {
      steps { sh '''set -eu
        mkdir -p validation
        .venv/bin/ruff check backend
        .venv/bin/ruff format --check backend
        .venv/bin/python tools/export_openapi.py --check
        (cd backend && ../.venv/bin/python -m pytest --junitxml=../validation/backend-tests.xml --cov=app --cov-fail-under=85 --cov-report=xml:../validation/coverage.xml)
        npm --prefix frontend run contract
        git diff --exit-code -- frontend/src/api-schema.d.ts
        npm --prefix frontend run format:check
        npm --prefix frontend test
        npm --prefix frontend run build
        .venv/bin/python tools/check_assets.py
        .venv/bin/python tools/check_prometheus.py
      ''' }
    }
    stage('Browser integration') {
      steps { sh '''set -eu
        # Chromium and its OS libraries must be present on the pinned CI agent.
        npm --prefix frontend run test:e2e
      ''' }
    }
    stage('Telemetry integration') {
      steps { sh '''set -eu
        : "${OTELCOL_BINARY:?Set the pinned otelcol-contrib 0.163.2 binary}"
        .venv/bin/python tools/verify_observability.py > validation/observability.log 2>&1
      ''' }
    }
    stage('Security gates') {
      steps { sh '''set -eu
        .venv/bin/pip-audit -r backend/requirements.lock --disable-pip --no-deps -f json -o validation/python-audit.json
        npm --prefix frontend audit --audit-level=high
        trivy fs --scanners secret,misconfig --skip-dirs .venv,frontend/node_modules --severity HIGH,CRITICAL --exit-code 1 .
      ''' }
    }
    stage('Build, scan and sign images') {
      when { allOf { branch 'main'; not { changeRequest() } } }
      steps {
        withCredentials([usernamePassword(credentialsId: 'omniclaim-registry', usernameVariable: 'REGISTRY_USER', passwordVariable: 'REGISTRY_PASSWORD')]) {
          sh '''set -eu
            : "${REGISTRY_HOST:?}" "${IMAGE_REPOSITORY:?}" "${COSIGN_KEY_REF:?}"
            printf '%s' "$REGISTRY_PASSWORD" | docker login "$REGISTRY_HOST" --username "$REGISTRY_USER" --password-stdin
            trap 'docker logout "$REGISTRY_HOST" >/dev/null 2>&1' EXIT
            bash ci/build.sh
          '''
        }
      }
    }
    stage('Staging deployment and live gates') {
      when { allOf { branch 'main'; not { changeRequest() } } }
      steps {
        lock(resource: 'omniclaim-explorer-staging') {
          withCredentials([file(credentialsId: 'omniclaim-staging-kubeconfig', variable: 'KUBECONFIG'),file(credentialsId: 'omniclaim-staging-values', variable: 'DEPLOY_VALUES'),file(credentialsId: 'omniclaim-staging-smoke', variable: 'SMOKE_CONFIG'),file(credentialsId: 'omniclaim-cosign-public-key', variable: 'COSIGN_PUBLIC_KEY')]) {
            script {
              sh '.venv/bin/python ci/deploy.py staging'
              try { sh '.venv/bin/python tools/live_smoke.py' }
              catch (err) { sh '.venv/bin/python ci/deploy.py staging --rollback'; throw err }
            }
          }
        }
      }
    }
    stage('Production release approval') {
      when { allOf { branch 'main'; not { changeRequest() }; expression { params.PROMOTE_PRODUCTION } } }
      steps {
        timeout(time: 30, unit: 'MINUTES') {
          input message: 'Promote build/release.json digests that passed staging? Review archived test and security reports.', submitter: 'omniclaim-release-managers'
        }
      }
    }
    stage('Production promotion') {
      when { allOf { branch 'main'; not { changeRequest() }; expression { params.PROMOTE_PRODUCTION } } }
      steps {
        lock(resource: 'omniclaim-explorer-production') {
          withCredentials([file(credentialsId: 'omniclaim-production-kubeconfig', variable: 'KUBECONFIG'),file(credentialsId: 'omniclaim-production-values', variable: 'DEPLOY_VALUES'),file(credentialsId: 'omniclaim-production-smoke', variable: 'SMOKE_CONFIG'),file(credentialsId: 'omniclaim-cosign-public-key', variable: 'COSIGN_PUBLIC_KEY')]) {
            script {
              sh '.venv/bin/python ci/deploy.py production'
              try { sh '.venv/bin/python tools/live_smoke.py' }
              catch (err) { sh '.venv/bin/python ci/deploy.py production --rollback'; throw err }
            }
          }
        }
      }
    }
  }
  post {
    always {
      junit allowEmptyResults: true, testResults: 'validation/backend-tests.xml,frontend/test-results/e2e.xml'
      archiveArtifacts allowEmptyArchive: true, artifacts: 'validation/*.json,validation/*.xml,validation/observability.log,build/release.json,build/*.cdx.json,frontend/playwright-report/**'
      // Synthetic-only browser traces are archived. Do not capture production customer screens.
    }
    cleanup { deleteDir() }
  }
}
