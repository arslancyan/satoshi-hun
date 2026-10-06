-- Satoshi Hunt account security and payout validation
-- Passwords are stored only as salted PBKDF2-HMAC-SHA256 hashes.
alter table accounts add column if not exists password_hash text;

create index if not exists idx_withdrawals_status_created
  on withdrawal_requests(status,created_at);
