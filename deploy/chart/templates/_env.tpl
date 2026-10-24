{{- define "explorer.env" -}}
- name: APP_ENVIRONMENT
  value: {{ .Values.app.environment | quote }}
- name: APP_VERSION
  value: {{ .Values.app.version | quote }}
- name: APP_DATA_MODE
  value: snowflake
- name: APP_TELEMETRY_ENABLED
  value: "true"
- name: APP_POLICY_FILE
  value: /config/access-policy.json
- name: APP_ALLOWED_HOSTS
  value: {{ list .Values.app.host "127.0.0.1" "localhost" (printf "%s-api" .Release.Name) | toJson | quote }}
- name: APP_CURSOR_KEY_FILE
  value: /secrets/cursor.key
- name: APP_AUDIT_KEY_FILE
  value: /secrets/audit.key
- name: APP_SNOWFLAKE_KEY_FILE
  value: /secrets/snowflake.p8
- name: APP_OTLP_ENDPOINT
  value: https://{{ .Release.Name }}-collector:4318
- name: APP_OTLP_CA_FILE
  value: /tls/ca.crt
- name: APP_OTLP_CERT_FILE
  value: /tls/tls.crt
- name: APP_OTLP_KEY_FILE
  value: /tls/tls.key
- name: APP_FRESHNESS_SECONDS
  value: {{ .Values.monitoring.freshnessSeconds | quote }}
- name: OTEL_RESOURCE_ATTRIBUTES
  value: service.instance.id=$(POD_NAME)
{{- range $key,$value := .Values.app.settings }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
{{- end -}}
