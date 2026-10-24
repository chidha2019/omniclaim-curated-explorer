{{- define "explorer.name" -}}{{ .Release.Name }}{{- end -}}
{{- define "explorer.labels" -}}
app.kubernetes.io/part-of: omniclaim-explorer
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "explorer.validate" -}}
{{- if not (has .Values.app.environment (list "staging" "production")) }}{{ fail "Only staging/production can deploy this chart" }}{{ end -}}
{{- if not .Values.app.version }}{{ fail "app.version must be the tested commit SHA" }}{{ end -}}
{{- if not (regexMatch "^[a-zA-Z0-9.-]+$" .Values.app.host) }}{{ fail "Set a valid app.host" }}{{ end -}}
{{- if not (regexMatch "^https://[a-zA-Z0-9.-]+(:[0-9]+)?$" .Values.app.issuerOrigin) }}{{ fail "Set the exact HTTPS issuerOrigin for CSP" }}{{ end -}}
{{- if not .Values.app.accessPolicy.tenants }}{{ fail "Set app.accessPolicy.tenants" }}{{ end -}}
{{- if not .Values.network.externalCIDRs }}{{ fail "Set network.externalCIDRs to your approved IdP/Snowflake/telemetry egress ranges" }}{{ end -}}
{{- if not .Values.monitoring.runbookBaseUrl }}{{ fail "Set monitoring.runbookBaseUrl to the published runbooks" }}{{ end -}}
{{- range list .Values.api.image .Values.web.image .Values.collector.image -}}
{{- if not (regexMatch "^[^ ]+@sha256:[a-f0-9]{64}$" .) }}{{ fail "All images require immutable sha256 digests" }}{{ end -}}
{{- end -}}
{{- end -}}
