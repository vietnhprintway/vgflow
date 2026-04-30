# CRUD Surfaces - Phase 0 Diagnostic Smoke

Generated for: tests/fixtures/phase0-diagnostic-smoke (v2.40.0 Task 2 diagnostic)

Purpose: minimal fixture (1 resource × 2 roles) to feed
`scripts/spawn-crud-roundtrip.py` and trace why production phases produce
empty `network_log[]` despite the Gemini Flash + MCP playwright smoke
tests passing.

```json
{
  "version": "1",
  "generated_from": ["phase0-diagnostic-smoke"],
  "no_crud_reason": "",
  "resources": [
    {
      "name": "notes",
      "kit": "crud-roundtrip",
      "domain_owner": "Diagnostic",
      "operations": ["list", "detail", "create", "update", "delete"],
      "scope": "user",
      "expected_behavior": {
        "admin": {
          "list": "200",
          "create": "201",
          "update": "200",
          "delete": "204"
        },
        "user": {
          "list": "200",
          "create": "201",
          "update": "200",
          "delete": "204"
        },
        "object_level": {
          "cross_owner_read": "403",
          "cross_tenant_read": "403",
          "cross_owner_mutation": "403"
        }
      },
      "forbidden_side_effects": [
        "POST /api/billing/charge",
        "POST /api/email/send"
      ],
      "base": {
        "roles": ["admin", "user"],
        "business_flow": {
          "lifecycle_states": ["draft", "published", "archived"],
          "entry_points": ["notes list"],
          "invariants": ["Archived notes are read-only"],
          "side_effects": ["audit log on create/update/delete"]
        },
        "security": {
          "object_auth": "owner-scoped",
          "field_auth": "server allowlist",
          "csrf": "required",
          "rate_limit": "per-user"
        },
        "delete_policy": {
          "confirm": true,
          "reversible_policy": "soft delete",
          "audit_log": true
        }
      },
      "platforms": {
        "web": {
          "list": {
            "route": "/notes",
            "table": {"columns": ["title", "status", "created_at"]}
          },
          "form": {
            "create_route": "/notes/new",
            "update_route": "/notes/:id/edit",
            "fields": ["title", "body", "status"]
          },
          "delete": {"confirm_dialog": true}
        },
        "backend": {
          "list_endpoint": {"path": "GET /api/notes"},
          "mutation": {
            "paths": [
              "POST /api/notes",
              "PATCH /api/notes/{id}",
              "DELETE /api/notes/{id}"
            ]
          }
        }
      }
    }
  ]
}
```
