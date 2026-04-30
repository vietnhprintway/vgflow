# Resources

```json
{
  "resources": [
    {
      "name": "topup_requests",
      "kit": "crud-roundtrip",
      "scope": "admin",
      "base": {
        "roles": ["admin"],
        "business_flow": {
          "lifecycle_states": ["pending", "approved", "rejected"]
        }
      },
      "expected_behavior": {
        "admin": {
          "list": "all topup requests visible",
          "approve": "transitions pending → approved",
          "reject": "transitions pending → rejected",
          "delete": "removes record"
        }
      },
      "forbidden_side_effects": [
        "user role cannot approve/reject",
        "anon cannot view"
      ]
    }
  ]
}
```
