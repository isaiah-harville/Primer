# HTTP API

Generated from the running services' OpenAPI schemas, so it cannot
drift from the routes it describes.

Every error response is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
problem document with a stable `code`. Endpoints under `/internal` are
not listed: they are reachable only from inside the cluster, and the
edge proxy must not route them.

## Control API

Everything a user's browser talks to: libraries, documents, and identity.

### `GET /api/v1/libraries`

List the caller's libraries.

| Status | Meaning |
| --- | --- |
| `200` | Successful Response |

### `POST /api/v1/libraries`

Create a private library.

| Status | Meaning |
| --- | --- |
| `201` | Successful Response |
| `422` | Validation Error |

### `GET /api/v1/libraries/{library_id}`

Read one library.

| Parameter | In | Required |
| --- | --- | --- |
| `library_id` | path | yes |

| Status | Meaning |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

### `PATCH /api/v1/libraries/{library_id}`

Rename a library.

| Parameter | In | Required |
| --- | --- | --- |
| `library_id` | path | yes |

| Status | Meaning |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

### `DELETE /api/v1/libraries/{library_id}`

Delete a library.

| Parameter | In | Required |
| --- | --- | --- |
| `library_id` | path | yes |

| Status | Meaning |
| --- | --- |
| `204` | Successful Response |
| `422` | Validation Error |

### `GET /api/v1/libraries/{library_id}/documents`

List a library's documents.

| Parameter | In | Required |
| --- | --- | --- |
| `library_id` | path | yes |

| Status | Meaning |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

### `POST /api/v1/libraries/{library_id}/documents`

Upload a document.

| Parameter | In | Required |
| --- | --- | --- |
| `library_id` | path | yes |

| Status | Meaning |
| --- | --- |
| `201` | Successful Response |
| `422` | Validation Error |

### `GET /api/v1/libraries/{library_id}/documents/{document_id}`

Read one document's status.

| Parameter | In | Required |
| --- | --- | --- |
| `library_id` | path | yes |
| `document_id` | path | yes |

| Status | Meaning |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

### `DELETE /api/v1/libraries/{library_id}/documents/{document_id}`

Delete a document.

| Parameter | In | Required |
| --- | --- | --- |
| `library_id` | path | yes |
| `document_id` | path | yes |

| Status | Meaning |
| --- | --- |
| `204` | Successful Response |
| `422` | Validation Error |

### `GET /api/v1/libraries/{library_id}/documents/{document_id}/content`

Download the current version's bytes.

| Parameter | In | Required |
| --- | --- | --- |
| `library_id` | path | yes |
| `document_id` | path | yes |

| Status | Meaning |
| --- | --- |
| `200` | Successful Response |
| `422` | Validation Error |

### `POST /api/v1/libraries/{library_id}/documents/{document_id}/versions`

Replace a document with a new version.

| Parameter | In | Required |
| --- | --- | --- |
| `library_id` | path | yes |
| `document_id` | path | yes |

| Status | Meaning |
| --- | --- |
| `201` | Successful Response |
| `422` | Validation Error |

### `GET /api/v1/me`

Describe the acting principal.

| Status | Meaning |
| --- | --- |
| `200` | Successful Response |

### `GET /health/live`

Liveness probe.

| Status | Meaning |
| --- | --- |
| `200` | Successful Response |

### `GET /health/ready`

Readiness probe.

| Status | Meaning |
| --- | --- |
| `200` | Successful Response |
