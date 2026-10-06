-- Bind every payout PSBT to the exact approved amount, destination, and unsigned transaction.
alter table payout_settlements
  add column if not exists payout_digest text;
create index if not exists idx_payout_settlements_digest
  on payout_settlements(payout_digest);
