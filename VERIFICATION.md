# Verification report — 19 September 2026

- 52 integration and alert-explanation tests passed.
- 9 supplied ANN inference tests passed.
- Python compilation completed for integration, controller utilities, alert explanations and all four layer packages.
- Dependency consistency check passed.
- Real HTTP and WebSocket server started successfully on localhost:8002.
- Edge/Playwright browser checks passed: live snapshots, preserved what-if form inputs during updates, simulation output, fault injection, eight explanation questions, timer-expiry reallocation, and mobile layout with no horizontal overflow.
- No JavaScript exceptions occurred during the browser checks.
- Full-buffer transfer regression verifies board conservation and queue limits.
- Original ANN artifacts load with their matching scikit-learn 1.8.0 version.

Default operating mode is simulated. No physical factory, controller actuation, external MQTT broker, or validated future-failure model was tested. The controller-only API was tested with generated request fixtures. Demo model profiles are synthetic and not independent factory validation data.

A Starlette warning notes that its test client prefers httpx2; all HTTP tests pass with the pinned httpx version. This does not affect the running dashboard.

Detailed test output is captured locally in data/test-results.txt and data/ann-test-results.txt. The ZIP intentionally omits runtime data and the virtual environment.

3D upgrade: WebGL browser checks passed for animation, fault/blockage and stale-data pauses, queues, standby routes, counter-driven transfers, selection, orbit/focus, disposal/remount and mobile overflow. Backend logic was unchanged.
