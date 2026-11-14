# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Execution state for MTConnect and OPC UA
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A stable topic with the execution state of the printer, in the words of MTConnect, for the adapters that show it as one more asset.

``hydra/bridges/printer3d/execution`` (retained) carries ``{"execution": "ACTIVE", "state": "RUNNING", "observed_at": ...}`` and is published every
time the bridge publishes its ``state`` (a ``cmd/status`` answer, the heartbeat, the websocket), so it never says more than the state it comes from.
Off by default (``[execution]`` in the configuration file). Read-only: it only restates what the bridge already published.

The mapping (the ``Execution`` values of MTConnect):

=========  ===========  =====================================================
state      execution    meaning
=========  ===========  =====================================================
IDLE       READY        Klipper is ready and no print is going on
RUNNING    ACTIVE       a print is in progress
HOLDING    INTERRUPTED  the print is paused
FAULT      STOPPED      Klipper shut down or the print ended in an error
other      UNAVAILABLE  offline, unreachable or not known (fail-closed)
=========  ===========  =====================================================

The same message also goes, in the format of the fleet of HYDRA-UMC-OPCUA-SERVER, to ``hydra/bridges/printer3d/opcua`` (not retained): an OPC UA server that
follows the broker (``HYDRA_UMC_OPCUA_MQTT=1``) then shows ``Fleet/printer3d/execution`` and ``Fleet/printer3d/state`` as read-only nodes, with no change on its side.
"""

from __future__ import annotations

import json

from hydra_umc_sdk.bridge_transport import MqttPublish

TOPIC_PREFIX = "hydra/bridges/printer3d/"
STATE_TOPIC = f"{TOPIC_PREFIX}state"
EXECUTION_TOPIC = f"{TOPIC_PREFIX}execution"
OPCUA_TOPIC = f"{TOPIC_PREFIX}opcua"
OPCUA_VEHICLE = "printer3d"

_EXECUTION = {"IDLE": "READY", "RUNNING": "ACTIVE", "HOLDING": "INTERRUPTED", "FAULT": "STOPPED"}
UNAVAILABLE = "UNAVAILABLE"


def execution_state(state: object) -> str:
    """The MTConnect execution value of a machine state (its name or its enum); anything not known is ``UNAVAILABLE``."""
    name = getattr(state, "value", state)
    return _EXECUTION.get(name, UNAVAILABLE) if isinstance(name, str) else UNAVAILABLE


def execution_publish(state: MqttPublish) -> MqttPublish | None:
    """The execution message that goes with a published ``state`` message; ``None`` for any other message or a state that cannot be read."""
    if state.topic != STATE_TOPIC:
        return None
    try:
        body = json.loads(state.payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    payload = {"execution": execution_state(body.get("state")), "state": body.get("state"), "observed_at": body.get("observed_at")}
    return MqttPublish(EXECUTION_TOPIC, json.dumps(payload), retain=True)


def opcua_publish(execution: MqttPublish) -> MqttPublish | None:
    """The fleet message of an ``execution`` message: two String nodes, ``execution`` and ``state``. ``None`` when it cannot be read or has no time."""
    try:
        body = json.loads(execution.payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(body, dict) or not isinstance(body.get("execution"), str) or not isinstance(body.get("state"), str):
        return None
    observed = body.get("observed_at")
    if isinstance(observed, bool) or not isinstance(observed, int):
        return None
    nodes = [
        {"path": f"Fleet/{OPCUA_VEHICLE}/execution", "type": "String", "value": body["execution"]},
        {"path": f"Fleet/{OPCUA_VEHICLE}/state", "type": "String", "value": body["state"]},
    ]
    return MqttPublish(OPCUA_TOPIC, json.dumps({"observed_at": observed, "vehicle": OPCUA_VEHICLE, "nodes": nodes}))


def with_execution(messages: list[MqttPublish]) -> list[MqttPublish]:
    """The messages, each ``state`` followed by its ``execution`` and by the same thing in the fleet format of the OPC UA server."""
    out: list[MqttPublish] = []
    for message in messages:
        out.append(message)
        extra = execution_publish(message)
        if extra is not None:
            out.append(extra)
            fleet = opcua_publish(extra)
            if fleet is not None:
                out.append(fleet)
    return out
