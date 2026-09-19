# Role Permission Boundary

```json
{
  "anonymous": [
    "public docs",
    "public health/status when safe"
  ],
  "user": [
    "own account",
    "own project results",
    "own tool calls",
    "confirmed write actions only"
  ],
  "reviewer": [
    "test-only app flow",
    "seeded test data"
  ],
  "owner_admin": [
    "masked admin reports",
    "ops dashboard",
    "configuration checklist"
  ]
}
```
