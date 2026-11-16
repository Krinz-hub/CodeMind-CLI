---
name: api-development
version: 1.0.0
description: REST and GraphQL API design, route conventions, payload validation, status code discipline, and error contracts.
category: api
triggers:
  manifests:
    - "openapi.yaml"
    - "openapi.json"
    - "schema.graphql"
    - "pyproject.toml"
    - "package.json"
  globs:
    - "*router*.py"
    - "*controller*.ts"
    - "*route*.ts"
  keywords:
    - "api"
    - "apis"
    - "endpoint"
    - "endpoints"
    - "rest"
    - "graphql"
    - "route"
    - "routes"
    - "controller"
    - "controllers"
    - "http"
    - "status code"
    - "payload"
    - "payloads"
required_tools:
  - read_file
  - create_file
  - apply_patch
  - run_command
dependencies: []
conflicts: []
workflow_steps:
  - "1. Inspect existing API routers to determine route naming conventions, authentication guards, and serialization formats."
  - "2. Define strongly-typed request schemas (Pydantic, Zod, or TypeScript interfaces) with boundary validation."
  - "3. Implement route handler with strict HTTP status code discipline (200 OK, 201 Created, 204 No Content, 400 Bad Request, 404 Not Found)."
  - "4. Establish uniform error envelope contracts matching existing API error standards."
  - "5. Add automated HTTP endpoint tests asserting status codes, headers, and payload structures."
constraints:
  - "Never return HTTP 200 OK with an error payload inside the body for REST APIs."
  - "Always validate incoming request query parameters and request bodies prior to business logic execution."
  - "Ensure all mutation endpoints (POST, PUT, DELETE) have idempotent handling or clear side-effect documentation."
verification:
  - "Execute automated API integration/unit tests and verify expected HTTP response codes and headers."
enabled: true
---

# API Engineering & Design Workflow

## 1. RESTful Standards
- **Resource Nouns:** Use plural nouns for resource collections (`/api/v1/orders`, `/api/v1/users`).
- **HTTP Verbs:**
  - `GET`: Safe, idempotent resource retrieval.
  - `POST`: Create a new resource; returns `201 Created` with resource location or payload.
  - `PUT`: Full idempotent resource replacement.
  - `PATCH`: Targeted partial update.
  - `DELETE`: Remove resource; returns `204 No Content`.

## 2. Standardized Error Response Envelope
```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested item 'item_123' does not exist.",
    "details": []
  }
}
```
