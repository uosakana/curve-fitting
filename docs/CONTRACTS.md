# Contracts

The application contract is the stable boundary between UI surfaces and Python
business logic.

## Runtime Contract

`contracts/app_contract.py` exposes `app_contract_payload()`. FastAPI publishes
the same payload at:

```text
GET /api/app-contract
```

The contract names:

- product workspace areas;
- supported product fit modes;
- evaluator kinds;
- required `FitResult` top-level fields;
- required and optional fit series keys;
- ranked candidate core fields and sources;
- manual-evaluate authority field;
- service methods with HTTP paths and future desktop bridge method names.

## Fit Result Rule

Every displayed fit result should keep these top-level fields stable:

```text
dataset
fit
series
diagnostics
model_context
parameter_schema
manual_capability
evaluator_kind
candidates
```

`result.series` and `result.fit.series` should both be populated when a fit is
renderable. Frontends should normalize both locations before charting, saving,
or exporting.

## Manual Evaluate Rule

Manual live evaluation is allowed only when:

```text
manual_capability.can_evaluate === true
```

The current base evaluator is `base_j0_rs_rsh_k`. Post-fit and custom displays
must not be sent through the base manual evaluator unless a future contract
explicitly exposes a compatible evaluator.

## Frontend Consumption

The runtime frontend consumes the contract from `app/static/app.js` through the
existing FastAPI endpoints. Keep contract assumptions near the request and render
helpers that use them, and cover payload changes with backend tests.
