{{/*
Shared naming and configuration.

Environment is assembled here rather than repeated per deployment: the four
services read the same settings, and a value that drifted between two of
them would produce a cluster where half the pods talk to a different
database.
*/}}

{{- define "primer.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "primer.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "primer.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "primer.labels" -}}
app.kubernetes.io/name: {{ include "primer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "primer.selectorLabels" -}}
app.kubernetes.io/name: {{ include "primer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "primer.image" -}}
{{- $image := index .root.Values.image .component -}}
{{- printf "%s:%s" $image.repository (default .root.Chart.AppVersion $image.tag) -}}
{{- end -}}

{{/*
Settings every service shares. Secrets are referenced, never inlined: a value
in the manifest is a value in `kubectl get deployment -o yaml`, and anyone
with read access to the namespace has it.
*/}}
{{- define "primer.commonEnv" -}}
- name: PRIMER_AUTH_MODE
  value: {{ .Values.auth.mode | quote }}
- name: PRIMER_DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ required "postgresql.existingSecret is required" .Values.postgresql.existingSecret }}
      key: {{ .Values.postgresql.urlKey }}
- name: PRIMER_SOURCE_STORE_URL
  value: {{ .Values.sourceStore.url | quote }}
- name: PRIMER_INTERNAL_API_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ include "primer.fullname" . }}-internal
      key: internal-token
- name: PRIMER_SERVICE_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ include "primer.fullname" . }}-internal
      key: internal-token
{{- end -}}

{{- define "primer.brokerEnv" -}}
- name: PRIMER_BROKER_URL
  valueFrom:
    secretKeyRef:
      name: {{ required "rabbitmq.existingSecret is required" .Values.rabbitmq.existingSecret }}
      key: {{ .Values.rabbitmq.urlKey }}
{{- end -}}

{{- define "primer.embeddingEnv" -}}
- name: PRIMER_EMBEDDING_BASE_URL
  value: {{ required "inference.embeddings.baseUrl is required" .Values.inference.embeddings.baseUrl | quote }}
- name: PRIMER_EMBEDDING_MODEL
  value: {{ required "inference.embeddings.model is required" .Values.inference.embeddings.model | quote }}
- name: PRIMER_EMBEDDING_DIMENSIONS
  value: {{ .Values.inference.embeddings.dimensions | quote }}
{{- if .Values.inference.embeddings.existingSecret }}
- name: PRIMER_EMBEDDING_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.inference.embeddings.existingSecret }}
      key: {{ .Values.inference.embeddings.apiKeyKey }}
{{- end }}
{{- end -}}

{{/*
A writable home and temp directory. The root filesystem is read-only, and
several libraries create a cache or config directory under $HOME on import
and fail hard without one.
*/}}
{{- define "primer.scratchVolumes" -}}
- name: tmp
  emptyDir:
    sizeLimit: 512Mi
- name: home
  emptyDir:
    sizeLimit: 64Mi
{{- end -}}

{{- define "primer.scratchMounts" -}}
- name: tmp
  mountPath: /tmp
- name: home
  mountPath: /home/primer
{{- end -}}
