---
goals:
  - id: G-LOGIN
    actor: admin
    entry_url: /admin/login
    role: admin
    account_email: admin@vg.test
    account_password: change-me
    navigation_steps: "Open /admin/login"
    precondition: "Browser fresh, no session cookie"
    expected_behavior: "Submit valid creds → redirect /admin/dashboard"
  - id: G-SITES-LIST
    actor: admin
    entry_url: /admin/sites
    role: admin
    account_email: admin@vg.test
    account_password: change-me
    navigation_steps: "Login as admin, click Sites tab"
    precondition: "≥1 site exists in fixture seed"
    expected_behavior: "Sites table renders with at least one row"
---

# Goals

## G-LOGIN: Login flow
Smoke that admin can log in.

## G-SITES-LIST: Sites list view
Verify sites table renders.
