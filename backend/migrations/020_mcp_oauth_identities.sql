-- Explicit OAuth identity mapping for MCP worker access.
-- Never map a production identity to an account solely by email.
create table if not exists mcp_oauth_identities (
  id uuid primary key,
  issuer text not null,
  subject text not null,
  account_id uuid not null references accounts(id) on delete cascade,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz,
  unique (issuer, subject)
);

create index if not exists idx_mcp_oauth_identities_account
  on mcp_oauth_identities(account_id);

-- Provider linkage is deliberately separate from accounts.email so an OAuth
-- subject remains stable even if a user changes their email address.
