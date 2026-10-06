-- Satoshi Hunt owner platform-fee destination lock.
-- No private key or signing material is stored.

alter table reward_ledger
  add column if not exists destination_btc_address text;

update reward_ledger
set destination_btc_address = 'bc1psfusgszcfvtw243uu9hq0fvdhta7s2lc8ufmr2n0f9eaw6qezxusa4pa8m'
where entry_type = 'PLATFORM_FEE' and destination_btc_address is null;

alter table reward_ledger
  drop constraint if exists reward_ledger_platform_fee_destination_check;

alter table reward_ledger
  add constraint reward_ledger_platform_fee_destination_check
  check (
    entry_type <> 'PLATFORM_FEE'
    or destination_btc_address = 'bc1psfusgszcfvtw243uu9hq0fvdhta7s2lc8ufmr2n0f9eaw6qezxusa4pa8m'
  );

create index if not exists idx_reward_ledger_destination
  on reward_ledger(destination_btc_address)
  where entry_type = 'PLATFORM_FEE';
