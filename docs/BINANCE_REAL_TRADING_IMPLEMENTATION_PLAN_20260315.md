# Binance Real Trading Implementation Plan (2026-03-15)

## Purpose

This document describes how to evolve the current Binance live paper trading flow into real exchange trading with the smallest possible future rewrite.

The goal is not "send real orders quickly". The goal is:

1. keep current paper trading stable,
2. avoid unsafe shortcuts,
3. prepare the code so that real Binance execution becomes an additive feature instead of a second system.

---

## Current State

### What is already real

- Historical and warm-up market data comes from exchange data via `ccxt` in `engine/data_loader.py`.
- Live candle streaming for paper mode now comes from Binance public sockets via `python-binance` in `engine/live_ws_client.py`.
- The dashboard already requires `exchange`, and defaults live paper runs to `binance`.
- The dashboard can restore an active backtest/live session after page reload from `/api/runtime/state`, including buffered console output.
- The current live smoke template is `live_test_1m_frequent`, which now runs `fast_test_strategy` on a single `1m` feed for fast end-to-end checks.

### What is still paper-only

- Orders are still simulated by the Backtrader broker in `engine/base_engine.py`.
- Strategy order lifecycle is still tied to Backtrader methods such as `buy()`, `sell()`, `close()`, and `notify_order()` in:
  - `strategies/base_strategy.py`
  - `strategies/bt_price_action.py`
  - `strategies/fast_test_strategy.py`
- No real Binance order is sent.
- No Binance user-data stream is consumed for fills, positions, or balance changes.
- No real startup reconciliation is implemented.
- Live UI validation now intentionally allows single-timeframe paper runs, because the smoke/live-pipeline strategy does not require an HTF/LTF pair.

### Fees right now

- Paper mode uses an exchange-aware modeled fee schedule from `engine/execution_settings.py`.
- Current defaults are:
  - Binance spot: `10 bps maker / 10 bps taker`
  - Binance futures: `2 bps maker / 4 bps taker`
- Paper broker currently assumes taker-side charging.
- This is a realistic model for paper, but it is not the account's true charged commission.
- Account-specific fee lookup groundwork already exists in `engine/binance_account_client.py`.

---

## Direct Answers

### Do we need to "register" or "verify" a bot with Binance?

For a personal self-hosted trading app, the trading docs point to API-key based authentication and permissions. They do not describe a separate public "bot registration" flow for a private trading client.

Practical meaning:

- our application is the bot,
- Binance identifies it through your account API keys,
- what must be enabled is the account, the product permissions, and the API key permissions.

Inference from official docs:

- signed trading and account endpoints require API credentials and signatures,
- user-data streams also require authenticated setup,
- there is no separate trading-app marketplace registration step in the core trading docs we rely on.

What still may be required on your Binance account:

- account eligibility in your jurisdiction,
- whatever identity/KYC steps Binance requires for that account and product,
- futures product activation if we target USD-M futures,
- API Management enabled on the account.

### If I deposit $100 to my personal Binance account, how would real trading work later?

At a high level:

1. Fund the Binance account.
2. If we trade futures, move funds into the USD-M futures wallet.
3. Create a Binance API key for this app.
4. Give that key only the minimum required permissions.
5. Add the connection in the dashboard.
6. Backend validates the account, permissions, symbol filters, fees, and safety policy.
7. Start the strategy from the dashboard in `execution_mode=real`.
8. Strategy still consumes live market data, but execution happens on Binance and fill events come back through the Binance user-data stream.

### Do we need API keys for real mode?

Yes.

Paper mode does not need them because it only reads public market data.

Real trading does need them because:

- placing orders is a signed API action,
- reading account-specific commission rates is a signed API action,
- reading user execution updates requires authenticated stream setup.

### Is it safe for the real balance?

Only after the real-execution safety layer is finished.

Right now the system is safe for the real balance because it does not send real Binance orders. After real mode is added, safety depends on:

- no plaintext secret storage,
- permission-scoped API keys,
- no withdrawal permission,
- IP whitelist,
- startup reconciliation,
- reduce-only exits,
- max notional and max loss guards,
- emergency flatten and session kill switch.

Without those controls, "real mode" is not safe enough for real money.

---

## Product Decision

We should explicitly support two live modes:

1. `execution_mode=paper`
2. `execution_mode=real`

This separation already exists in config groundwork and must remain explicit in API, runtime, persistence, and UI.

For the first production real version, the minimal-change path is:

- `exchange=binance`
- `exchange_type=future`
- one-way mode only
- isolated margin only
- one live symbol per session

Why futures first:

- current live config already defaults to futures,
- the strategy stack assumes both long and short capability,
- futures gives us `reduceOnly`, which simplifies safe protective exits,
- spot would require a different shorting model and different position assumptions.

---

## Architecture Target

### Core principle

Keep market data and execution as separate concerns.

We should keep using:

- `DataLoader` for warm-up and historical data,
- public market-data streams for live candles.

We should add a separate real execution stack for:

- account connectivity,
- order placement,
- fill handling,
- position sync,
- reconciliation,
- risk controls.

### Domain objects to introduce

Add explicit models for:

- `ExchangeConnection`
  - exchange
  - exchange_type
  - api_key_id
  - masked key label
  - testnet flag
  - allowed capabilities
  - last validation result
- `ExecutionSession`
  - session id
  - strategy
  - symbol
  - exchange
  - exchange_type
  - execution_mode
  - connection id
  - start time
  - current safety status
- `OrderIntent`
  - internal id
  - session id
  - side
  - quantity
  - entry type
  - intended stop
  - intended take profit
  - reduce-only policy
  - created at
- `ExecutionOrder`
  - Binance order id
  - clientOrderId
  - intent id
  - status
  - filled quantity
  - average fill price
  - reduceOnly
- `PositionSnapshot`
  - symbol
  - side
  - size
  - entry price
  - unrealized pnl
  - margin mode
  - leverage
- `ExecutionEvent`
  - event type
  - source
  - event time
  - raw payload
  - normalized payload

These should become the source of truth for real mode, not the Backtrader broker state.

---

## Critical Architectural Constraint

Current strategies are still tightly coupled to Backtrader execution.

Examples:

- market entries are placed by `self.buy()` / `self.sell()` in `strategies/bt_price_action.py`,
- protective orders are created in `notify_order()` in `strategies/base_strategy.py`,
- closing logic relies on `self.close()`,
- position state relies on `self.position`.

That means real Binance execution is not a simple "swap a client" patch.

If we send real orders while the strategy still believes the Backtrader broker is the real source of fills, state divergence is very likely.

So the safe plan is:

1. preserve the current Backtrader paper path,
2. introduce an execution boundary,
3. refactor strategies from "place orders directly" toward "emit intents, then execution service handles them".

This is the single most important preparatory change.

---

## Recommended Backend Design

### 1. Add an execution service boundary

Create a runtime interface that hides paper vs real execution:

```python
class ExecutionService(Protocol):
    def preflight_check(self, session_config: dict) -> PreflightResult: ...
    def sync_startup_state(self, session_config: dict) -> StartupSyncResult: ...
    def submit_entry_intent(self, intent: OrderIntent) -> ExecutionOrder: ...
    def submit_protective_orders(self, position: PositionSnapshot, intent: OrderIntent) -> ProtectiveOrderGroup: ...
    def replace_protective_orders(self, group_id: str, stop_price: Decimal, tp_price: Decimal) -> ProtectiveOrderGroup: ...
    def cancel_order(self, order_id: str) -> None: ...
    def cancel_group(self, group_id: str) -> None: ...
    def flatten_position(self, symbol: str, reason: str) -> FlattenResult: ...
    def get_session_state(self) -> SessionExecutionState: ...
    def shutdown(self) -> None: ...
```

Implementations:

- `BacktraderPaperExecutionService`
- `BinanceRealExecutionService`

### 2. Keep market-data transport separate

Keep:

- `engine/live_ws_client.py` for public kline feeds
- `engine/data_loader.py` for warm-up

Add:

- `engine/binance_user_stream.py`
  - authenticated Binance user-data stream
  - reconnect logic
  - keepalive refresh for listen key
- `engine/binance_order_client.py`
  - signed REST order/account calls
- `engine/execution/` package
  - execution models
  - service interface
  - reconciliation logic
  - persistence helpers

### 3. Make user-data stream the real source of fills

For `execution_mode=real`, order state must advance from Binance execution events, not from local assumptions.

Important consequences:

- actual fee charged must come from fill/update events,
- startup fee lookup is only a pre-session estimate and validation aid,
- maker/taker attribution must come from exchange events where available,
- partial fills must resize protective orders,
- restart recovery must rebuild state from Binance plus persisted local intents.

### 4. Add startup reconciliation before live start

Before a real session starts, backend must:

1. validate API credentials,
2. check server time and signed-call health,
3. fetch account-specific commission rates,
4. fetch open orders,
5. fetch open positions,
6. fetch symbol filters and minimum quantity/notional rules,
7. verify margin mode and allowed leverage policy,
8. compare exchange state with local persisted state,
9. either resume safely or refuse to start.

If unknown live positions or orphan orders exist, start should fail closed by default.

### 5. Persist intents and exchange events

Real mode needs durable persistence for:

- order intents,
- placed order ids,
- client order ids,
- order-group linkage,
- fill events,
- startup reconciliation snapshots,
- session kill-switch status.

Without this, restart safety is not good enough.

---

## Recommended Frontend Design

### New dashboard pieces

Add a dedicated real-trading connection flow:

- `Exchange Connection`
  - exchange
  - market type
  - label
  - API key input
  - API secret input
  - testnet toggle
  - validate button
- `Execution Mode`
  - `paper`
  - `real`
- `Connected Account Status`
  - connection health
  - futures enabled or not
  - wallet balance
  - current leverage mode
  - last validation time
- `Live Safety Policy`
  - max position notional
  - max daily loss
  - max concurrent positions
  - allowed leverage
  - dry-run confirmation text
- `Manual Controls`
  - flatten position
  - cancel all open orders
  - stop session

### UX rule

The `Start Live Run` button for real mode must stay disabled until:

- account connection validates,
- required permissions are present,
- symbol filters pass,
- safety policy is complete,
- startup reconciliation is clean.

---

## Concrete Code Changes

### Files to keep and extend

- `engine/execution_settings.py`
  - keep as the central place for `exchange`, `exchange_type`, `execution_mode`, and fee normalization
  - extend to support real-mode fee refresh at session start
- `engine/binance_account_client.py`
  - evolve into broader signed account adapter or split into:
    - commission
    - account info
    - open orders
    - position snapshot
- `engine/live_ws_client.py`
  - keep for public candle streams
  - do not mix user-data execution logic into it
- `engine/bt_live_engine.py`
  - stop hard-wiring strategy runtime directly to broker-only assumptions
  - make it call an execution service
- `web-dashboard/server.py`
  - add secure exchange-connection endpoints
  - add real-mode start/stop endpoints
  - add preflight and reconciliation APIs
- `web-dashboard/src/shared/model/types.ts`
  - add connection models, real-mode status, safety policy types
- `web-dashboard/src/app/providers/config/ConfigProvider.tsx`
  - send connection id, execution mode, and safety config
- `web-dashboard/src/widgets/config-panel/ui/ConfigPanel.tsx`
  - add account selector, execution mode, validation status, safety controls

### New backend files to add

- `engine/execution/models.py`
- `engine/execution/service.py`
- `engine/execution/paper_service.py`
- `engine/execution/binance_real_service.py`
- `engine/execution/reconciliation.py`
- `engine/execution/idempotency.py`
- `engine/execution/store.py`
- `engine/binance_user_stream.py`
- `engine/binance_order_client.py`
- `web-dashboard/services/exchange_connections.py`
- `web-dashboard/services/secret_store.py`

### Strategy-layer refactor needed

Current strategy code is the biggest blocker.

We need to move from:

- strategy directly placing broker orders

to:

- strategy generating a normalized execution intent.

Recommended incremental shape:

1. Keep strategy signal logic unchanged.
2. Extract "entry decision" into a pure intent object.
3. Extract protective order decision into a pure order-plan object.
4. Let the execution service decide how to translate that plan into:
   - Backtrader paper orders
   - Binance real orders

This is how we avoid rewriting strategy logic twice.

---

## Detailed Step-by-Step Delivery Plan

### Phase 0. Freeze the target contract

Goal:

- define the real-trading contract once before implementation spreads across backend and frontend.

Changes:

- formalize `paper` vs `real` API payload contract,
- define supported scope for first real release,
- define fail-closed startup behavior,
- define session persistence schema.

Decision for v1 real:

- Binance only
- USD-M futures only
- one-way mode only
- isolated margin only
- market entry only
- reduce-only protective exits only
- one symbol per session

### Phase 1. Secure account connection management

Goal:

- connect a Binance account safely without leaking secrets.

Changes:

- add backend storage for exchange connections,
- store API key and secret outside the current plain config flow,
- encrypt secrets at rest,
- never send stored secret back to frontend,
- add connection validation endpoint.

Important:

- do not reuse the current live config persistence for secrets,
- do not store API secret in result history,
- do not log request bodies containing secrets.

### Phase 2. Signed account adapter and preflight

Goal:

- make backend capable of validating a real Binance account before any session starts.

Changes:

- extend Binance signed adapter to fetch:
  - commission rates
  - open orders
  - account status
  - position state
  - symbol trading filters
- implement preflight result object,
- surface preflight status in dashboard.

Preflight should fail if:

- API key is invalid,
- permissions are missing,
- symbol filters make requested quantity invalid,
- account has unknown open orders,
- account has unknown open positions,
- leverage or margin mode violates policy,
- account wallet balance is below configured safety threshold.

### Phase 3. Execution boundary and paper parity

Goal:

- make paper and real execution share the same intent flow.

Changes:

- introduce `ExecutionService`,
- route current paper mode through `BacktraderPaperExecutionService`,
- refactor strategy runtime so it emits intents instead of calling broker methods directly.

Acceptance:

- paper results remain unchanged or deviations are understood and tested,
- live paper still works,
- no regression in current strategy behavior.

### Phase 4. Real order routing

Goal:

- place real Binance entry orders safely.

Changes:

- translate `OrderIntent` into signed Binance order request,
- use deterministic `newClientOrderId`,
- validate price and quantity against exchange filters,
- persist submitted order before sending request,
- handle retry rules without duplicate orders.

For futures we should use:

- market entry for v1,
- reduce-only stop and take-profit exits,
- deterministic order-group id linking all three legs.

### Phase 5. User-data stream and fill-driven lifecycle

Goal:

- make exchange events the source of truth.

Changes:

- start authenticated user-data stream for the connected account,
- refresh listen key before expiry,
- normalize order and account update events,
- persist raw and normalized execution events,
- update local session state only from normalized exchange events.

Required behaviors:

- partial fill support,
- duplicate event tolerance,
- sibling exit cancel on first protective fill,
- fee capture from actual execution update,
- realized pnl capture from exchange-driven lifecycle.

### Phase 6. Startup reconciliation and restart safety

Goal:

- survive restart without losing control of open exposure.

Changes:

- on real start or process restart, fetch exchange state,
- reconstruct position and order groups,
- compare with local session store,
- block or flatten if state is unsafe.

Policies:

- if local state is missing but exchange has open exposure, do not auto-start blindly,
- require explicit operator action or an approved flatten policy,
- session startup should be idempotent.

### Phase 7. Real-mode dashboard flow

Goal:

- make real trading operable from the same dashboard pattern as paper mode.

Changes:

- add execution mode selector,
- add account connection selector,
- add safety policy fields,
- add preflight summary modal,
- add stronger confirmation before first real run,
- show live orders, live position, live fills, and connection health.

The button flow should become:

1. select strategy,
2. select exchange,
3. select execution mode,
4. select Binance connection,
5. review preflight,
6. confirm real run,
7. session starts only if preflight is green.

### Phase 8. Hardening before first real money run

Goal:

- reduce operational risk before mainnet exposure.

Changes:

- IP whitelist support in operator setup,
- kill switch endpoint and UI button,
- flatten-all endpoint and UI button,
- better metrics and alerting,
- audit log for order intents and exchange responses.

---

## Practical User Flow For "$100 On My Personal Binance"

This is the future operator flow we should support from the dashboard.

### Step 1. Prepare the Binance account

- Fund the Binance account.
- If using futures, transfer part of the balance into the USD-M futures wallet.
- If futures are not enabled on the account yet, enable the futures product on Binance first.

Operational recommendation for a first real run:

- use isolated margin,
- use one-way mode,
- use very small notional,
- do not start with the full $100,
- keep one position max.

Conservative first-run policy for a $100 account:

- `max_position_notional = 10 to 20 USDT`
- `max_daily_loss = 3 to 5 USDT`
- `max_open_positions = 1`
- `initial leverage = 1x`

### Step 2. Create API credentials

Create a dedicated Binance API key for this app.

Recommended permissions:

- enable read/account access needed for validation and reconciliation,
- enable futures trading only if we actually run futures real mode,
- do not enable withdrawal permission.

Recommended operational setup:

- one dedicated API key per environment,
- use IP restriction,
- if your home IP is unstable, use a small VPS or stable egress host.

### Step 3. Connect the account in our dashboard

Future dashboard flow:

- open `Exchange Connection`,
- choose `Binance`,
- choose `USD-M Futures`,
- paste API key and secret,
- optionally mark as testnet/demo,
- click `Validate Connection`.

Validation should perform:

- signed request health check,
- account permission check,
- symbol availability check,
- fee fetch,
- wallet balance fetch,
- open order and open position scan.

If validation passes, save only the masked metadata to UI state and keep the secret server-side only.

### Step 4. Configure the live run

In the same dashboard area where we currently run paper live:

- choose strategy,
- symbol,
- timeframe,
- `exchange=binance`,
- `execution_mode=real`,
- linked Binance connection,
- safety limits.

### Step 5. Start the real session

When operator clicks `Start Live Run`:

1. backend runs preflight,
2. backend runs reconciliation,
3. backend starts market-data stream,
4. backend starts authenticated user-data stream,
5. backend starts session runtime,
6. strategy emits intents,
7. execution service sends orders to Binance,
8. exchange updates drive local order/position state.

### Step 6. Monitor and stop

Dashboard should show:

- current position
- active stop and take-profit orders
- live fills
- fees paid
- realized pnl
- unrealized pnl
- connection health
- last exchange event time

Stopping the session should:

- stop new entries,
- optionally keep protective exits active for existing position,
- or flatten immediately if operator chooses emergency stop.

---

## Security Requirements

These are mandatory before real trading.

### Secret handling

- never store API secrets in plain config documents,
- never return stored secret to frontend,
- never include secrets in logs or result snapshots,
- encrypt secrets at rest using a server-side master key,
- keep the master key outside the repo and outside image layers.

### Exchange permissions

- no withdrawal permission,
- minimum required read permissions,
- trading permission only for the product we use,
- separate paper/testnet and mainnet connections.

### Runtime controls

- kill switch,
- cancel all open orders,
- flatten position,
- max notional,
- max loss,
- duplicate order protection via deterministic client order ids,
- fail-closed startup if reconciliation is unsafe.

---

## Testing Plan

### Unit tests

- order intent normalization
- quantity and price rounding to exchange filters
- deterministic `clientOrderId` generation
- reduce-only enforcement
- fee normalization from actual exchange payloads
- duplicate execution event handling
- partial fill sibling-resize logic

### Integration tests

- signed Binance adapter with mocked responses
- startup reconciliation with:
  - clean account
  - orphan order
  - unknown position
  - partial fill in progress
- user-data stream reconnect and listen-key refresh
- API contract tests for real-mode endpoints

### End-to-end tests

- dashboard connection validation flow
- dashboard real preflight flow
- dashboard start/stop real session flow with mocked Binance
- emergency flatten flow

### Rollout tests before mainnet

- use Binance testnet/demo where supported,
- run shadow mode without order placement first,
- then run very small mainnet notional,
- only then raise limits.

---

## Acceptance Criteria For "Ready For First Real Money"

The system is not ready until all of these are true:

1. Secrets are not stored in plain config.
2. Dashboard can validate and save a Binance connection safely.
3. Real session start fails closed on reconciliation mismatch.
4. Entry order placement is idempotent.
5. Protective exits are reduce-only and linked.
6. First protective fill cancels sibling reliably.
7. Restart with open exposure is handled safely.
8. Manual flatten works.
9. Paper live still works.
10. Strategy behavior in paper mode is not regressed by the refactor.

---

## Recommended Implementation Order

Use this order to minimize rewrite:

1. Secure connection management
2. Signed account adapter and preflight
3. Execution service boundary
4. Strategy intent refactor
5. Real order client
6. User-data stream
7. Reconciliation
8. Real dashboard flow
9. Hardening and small-size rollout

If we skip step 3 or step 4, we will likely build a brittle real-execution side path that diverges from paper and is hard to trust.

---

## Official Sources Checked On 2026-03-15

- Binance Spot request security:
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/request-security
- Binance Spot trading endpoints:
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints
- Binance Spot user-data stream:
  - https://developers.binance.com/docs/binance-spot-api-docs/user-data-stream
- Binance Spot commission endpoint:
  - https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints#query-commission-rates-user_data
- Binance USD-M Futures new order:
  - https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order
- Binance USD-M Futures user-data streams:
  - https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams
- Binance USD-M Futures order update event:
  - https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update
- Binance USD-M Futures balance and position update event:
  - https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Balance-and-Position-Update
- Binance USD-M Futures commission endpoint:
  - https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate
- Binance USD-M Futures open orders endpoint:
  - https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders
- Binance spot fee page:
  - https://www.binance.com/en/fee/trading
- Binance Academy API security best practices:
  - https://academy.binance.com/en/articles/how-to-secure-your-binance-api-key

Notes:

- The statement "no separate bot registration is required for a personal self-hosted client" is an inference from the official authentication and trading docs above.
- Account verification, product eligibility, and regulatory availability depend on the account and jurisdiction and should be checked directly inside your Binance account.
