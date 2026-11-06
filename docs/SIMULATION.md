# Simulation bench

The printer bridge talks to Moonraker over its REST API. The tests start a local HTTP server that answers with Moonraker-shaped envelopes, so readiness, print statistics and the job commands (start, pause, resume, cancel, emergency stop) run without a printer.

The simulation bench replaces the hardware with a fixture HTTP server that answers like Moonraker (`tests/test_moonraker.py`), sliced-job artifacts and print profiles. It proves the parsing, the gating, the transports and the failure paths of the bridge; it says nothing about
a real machine, real timing or real safety functions.

## Run it

```
python -m unittest -v <modules>
```

from the `tests` folder, with `src` of this repository and `clients/python/src` of the SDK on `PYTHONPATH` (the same layout `python tools/build_test.py` uses). The
workflow named "Simulation bench" does exactly this on a clean Linux runner on every push and pull request, by hand and once a week, with nothing but Python.

## What it runs

| File | What it exercises |
|------|-------------------|
| `tests/test_moonraker.py` | readiness, print statistics and the job commands against the fixture server |
| `tests/test_artifacts.py` | slicer artifacts read read-only |
| `tests/test_profiles.py` | print profile matching against the evidence of the artifact |
| `tests/test_mqtt_transport.py` | the topic dispatch, QoS, idempotency and limits without a broker |
| `tests/test_broker_integration.py` | the same dispatch against a real MQTT broker; skipped unless the broker checkout is present |
| `tests/test_global_stop_broker.py` | the global stop over a real broker; skipped unless the broker checkout is present |

The broker scenarios start a real MQTT broker from a checkout of HYDRA-UMC-MQTT-BROKER (`HYDRA_UMC_TEST_BROKER_DIR`); the simulation job does not install it, so
those cases skip themselves there and run in the normal test run on a machine that has the broker.

## What it cannot show

A real Moonraker and Klipper installation, a real printer with heaters and motion, and the behaviour of a real emergency stop. The hardware row of the status table therefore stays at "simulated" until a person has run the bridge on a real setup.
