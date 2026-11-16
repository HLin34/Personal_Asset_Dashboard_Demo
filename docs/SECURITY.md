# Security Notes

## Public-release boundary

This portfolio repository deliberately excludes:

- Streamlit runtime secrets
- Supabase project-specific configuration
- Database schema migrations and production policy definitions
- Financial records, CSV/XLSX exports, and database backups
- One-time import batches containing real account data
- Production deployment identifiers and private URLs

## Credential model

The Streamlit application must use only a Supabase publishable key (or legacy anon key). A service-role or secret key bypasses Row Level Security and must never be exposed to a client-facing application.

Create `.streamlit/secrets.toml` locally from the example file:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-publishable-or-anon-key"
```

## Authorization model

Authentication identifies the signed-in user. Application queries include the user identifier, while PostgreSQL Row Level Security remains the authoritative access-control layer. This defense-in-depth approach prevents one authenticated user from accessing another user's records even if UI filtering is bypassed.

The production audit snapshot verified:

- 17 public tables with RLS enabled
- 17 public tables with policies present
- 40 policies with identity checks
- No broad `USING (true)` policy

## Reporting

If you discover a security issue, do not open a public issue containing credentials or private financial data. Contact the repository owner privately through the profile information on GitHub.
