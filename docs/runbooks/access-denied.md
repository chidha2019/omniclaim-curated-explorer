# Authentication or authorization failures

1. Distinguish 401 (missing/invalid/expired access token) from 403 (valid identity without tenant, scope or capability).
2. Verify issuer, API audience, RS256 key rotation and JWKS availability. ID tokens for the SPA audience are not API credentials.
3. Compare the IdP-issued tenant_id/groups/scope to the reviewed access policy. Grant only the required capability through the IdP and tenant-specific Snowflake role.
4. Reauthenticate after changes; restart workloads only when mounted policy/configuration changed.
5. For a denial burst, correlate server request IDs and the IdP's security logs through approved tooling. Never paste access tokens into tickets, traces or graph evidence.
