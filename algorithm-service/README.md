# Algorithm Service Adapter Layer

This directory contains the first-stage pure Python adapter layer for the two
legacy algorithms in `algorithm-service/legacy`.

This stage does not provide HTTP endpoints and is not connected to Spring Boot,
the frontend, Unity, ROS, or the database.

## Files

- `adapters/models.py`: shared dataclass input and output models.
- `adapters/escort_adapter.py`: one-step adapter for `EscortGuardSimulator`.
- `adapters/capture_adapter.py`: import/core-step probe for `SwarmEnv3D` and
  `GBSFLACSAlgorithm`, plus an explicit unsupported response for external
  3 UAV + 3 USV + 1 target input.
- `tests/`: unittest coverage for the adapters.

## Escort Mapping

The escort adapter creates `EscortGuardSimulator` with the input UAV and USV
counts, maps each input `vehicleId` to one legacy `Platform`, applies input
vehicle positions, applies the optional target and threat positions, executes
one `step()`, and returns assignments from each platform's `goal` when present
or `position` otherwise.

Legacy roles are mapped as follows:

- `core` -> `DEFEND`
- `wing` -> `INTERCEPT`
- `escort` -> `ESCORT`

The adapter does not instantiate `EscortGuardVisualizer` and does not call
`show()`.

## Capture Mapping

The capture adapter imports `SwarmEnv3D` and `GBSFLACSAlgorithm` with a headless
Matplotlib backend and runs one core step using the legacy default state.

The legacy capture file currently constructs its state from fixed module-level
constants:

- `UAV_COUNT = 40`
- `USV_COUNT = 40`
- `TARGET_COUNT = 20`

Because `SwarmEnv3D.reset()` constructs `env.agents` and `env.targets` from
those constants and the algorithm indexes those arrays by internal IDs, the
adapter does not claim support for external 3 UAV + 3 USV + 1 target input in
this stage. It returns `UNSUPPORTED_CONFIGURATION` with no assignments instead
of fabricating coordinates.

## Tests

Run:

```bash
python -B -m unittest discover algorithm-service/tests
```
