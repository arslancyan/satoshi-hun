-- Direct public escrow settlement metadata.
alter table work_claims add column if not exists candidate_nonce bigint;

alter table withdrawal_requests add column if not exists payout_mode text not null default 'PLATFORM_TREASURY';
alter table withdrawal_requests add column if not exists puzzle_id text;
alter table withdrawal_requests add column if not exists claim_id uuid references work_claims(id);
alter table withdrawal_requests add column if not exists claim_nonce bigint;
alter table withdrawal_requests add column if not exists claim_hash text;
alter table withdrawal_requests add column if not exists escrow_address text;
alter table withdrawal_requests add column if not exists witness_script_hex text;

create index if not exists idx_withdrawals_payout_mode
  on withdrawal_requests(status,payout_mode,created_at);
