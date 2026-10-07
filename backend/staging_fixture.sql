-- Staging-only deterministic challenge fixture.
-- Loaded only when SATOSHI_HUNT_ENV=staging.
-- Staging treasury: fund the deterministic reward rail with the same public
-- amount as the fixture reward so verified claims can exercise accounting.
insert into treasury_wallets(id,label,network,address,status)
values (
  '00000000-0000-0000-0000-000000000001',
  'Satoshi Hunt BTC Treasury',
  'bitcoin-mainnet',
  'bc1ptstlyntypqqf8s5qz3jwcsrxw2pxqj634c7pklj2mjlvqwl22l6qqq8csl',
  'ACTIVE'
)
on conflict (id) do update set funded_btc=excluded.id;

insert into treasury_accounting(id,funded_btc,reserved_btc,solver_liability_btc,owner_liability_btc)
values ('00000000-0000-0000-0000-000000000001',0.00100000,0,0,0)
on conflict (id) do update set funded_btc=0.00100000,reserved_btc=0;

insert into challenge_registry (
  id,title,challenge_type,reward_btc,balance_btc,status,rules,
  provenance,verification,payout,source_adapter,live_checked_at,live_verification,
  advertised_reward_btc,verified_balance_btc,funding_match,verification_stale,
  funding_snapshot,solve_evidence
) values (
  'satoshi-hunt-staging-001',
  'Satoshi Hunt Staging Known-Solution Challenge',
  'hash-commitment',
  0.00100000,
  0.00100000,
  'OPEN + FUNDED',
  'public-reward-challenge',
  '{"url":"https://staging.satoshi-hunt.invalid/challenge/001","source_id":"staging-001","checked_at":"2026-01-01T00:00:00Z"}'::jsonb,
  '{"method":"exact_candidate_hash","source_id":"staging-001","checked_at":"2026-01-01T00:00:00Z","fingerprint":"staging-known-solution-v1","expected_candidate_hash":"b54609333c7f5082f8e8eb408e40a59d73e9fbe9f546c2adf75347cd941bd22d","funding_match":true,"verification_stale":false}'::jsonb,
  '{"permissionless":true,"automatic_chain_claim":true}'::jsonb,
  'staging-hash-commitment',
  now(),
  '{"method":"staging-deterministic"}'::jsonb,
  0.00100000,
  0.00100000,
  true,
  false,
  '{"source":"staging-fixture","balance_btc":0.001}'::jsonb,
  '{}'::jsonb
)
on conflict (id) do update set
  title=excluded.title,
  challenge_type=excluded.challenge_type,
  reward_btc=excluded.reward_btc,
  balance_btc=excluded.balance_btc,
  status=excluded.status,
  rules=excluded.rules,
  provenance=excluded.provenance,
  verification=excluded.verification,
  payout=excluded.payout,
  source_adapter=excluded.source_adapter,
  live_checked_at=excluded.live_checked_at,
  live_verification=excluded.live_verification,
  advertised_reward_btc=excluded.advertised_reward_btc,
  verified_balance_btc=excluded.verified_balance_btc,
  funding_match=excluded.funding_match,
  verification_stale=excluded.verification_stale,
  funding_snapshot=excluded.funding_snapshot,
  solve_evidence=excluded.solve_evidence;
