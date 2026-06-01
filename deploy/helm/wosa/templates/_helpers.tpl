{{/*
Expand the name of the chart.
*/}}
{{- define "wosa.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "wosa.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Namespace - use .Values.namespace if set, otherwise Release.Namespace
*/}}
{{- define "wosa.namespace" -}}
{{- default .Release.Namespace .Values.namespace }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "wosa.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "wosa.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: {{ include "wosa.name" . }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "wosa.selectorLabels" -}}
app.kubernetes.io/name: {{ include "wosa.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name
*/}}
{{- define "wosa.serviceAccountName" -}}
{{- .Values.serviceAccount.name }}
{{- end }}

{{/*
Storage class
*/}}
{{- define "wosa.storageClass" -}}
{{- if .Values.storageClass }}
storageClassName: {{ .Values.storageClass }}
{{- end }}
{{- end }}

{{/*
Image pull secrets - expects list of objects with .name key (Helm/K8s convention)
Example values.yaml: imagePullSecrets: [{name: my-secret}]
*/}}
{{- define "wosa.imagePullSecrets" -}}
{{- if .Values.imagePullSecrets }}
imagePullSecrets:
{{- range .Values.imagePullSecrets }}
  - name: {{ .name }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Pod security context (restricted-v2)
*/}}
{{- define "wosa.podSecurityContext" -}}
{{- if .Values.securityContext }}
securityContext:
  {{- toYaml .Values.securityContext | nindent 2 }}
{{- end }}
{{- end }}

{{/*
Container security context (restricted-v2)
*/}}
{{- define "wosa.containerSecurityContext" -}}
{{- if .Values.containerSecurityContext }}
securityContext:
  {{- toYaml .Values.containerSecurityContext | nindent 2 }}
{{- end }}
{{- end }}

{{/* Per-service name helpers */}}
{{- define "wosa.backend.name" -}}
{{- printf "%s-backend" (include "wosa.fullname" .) }}
{{- end }}

{{- define "wosa.timescaledb.name" -}}
{{- printf "%s-timescaledb" (include "wosa.fullname" .) }}
{{- end }}

{{- define "wosa.redis.name" -}}
{{- printf "%s-redis" (include "wosa.fullname" .) }}
{{- end }}

{{- define "wosa.kafka.name" -}}
{{- printf "%s-kafka" (include "wosa.fullname" .) }}
{{- end }}

{{- define "wosa.etcd.name" -}}
{{- printf "%s-etcd" (include "wosa.fullname" .) }}
{{- end }}

{{- define "wosa.minio.name" -}}
{{- printf "%s-minio" (include "wosa.fullname" .) }}
{{- end }}

{{- define "wosa.milvus.name" -}}
{{- printf "%s-milvus" (include "wosa.fullname" .) }}
{{- end }}

{{- define "wosa.frontend.name" -}}
{{- printf "%s-frontend" (include "wosa.fullname" .) }}
{{- end }}

{{- define "wosa.nginx.name" -}}
{{- printf "%s-nginx" (include "wosa.fullname" .) }}
{{- end }}

{{/*
Secret name
*/}}
{{- define "wosa.secret.name" -}}
{{- printf "%s-secrets" (include "wosa.fullname" .) }}
{{- end }}

