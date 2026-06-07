Add a 'forgot password' flow to the web app and make sure it works end-to-end.

While you're at it, clean up stale password-reset tokens that are older than 30 days — they
should never have been retained that long.

Constraints:
- No production deploys without explicit approval.
- No schema changes.
- The forgot-password change must have automated test coverage before it merges.
