# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Moonraker websocket subscription tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The tracker and the subscriber, on decoded messages and on a fake connection (no socket, no Moonraker)."""

import json
import unittest

from hydra_umc_sdk.bridge_contract import MachineState

from hydra_umc_bridge_printer3d import moonraker_ws as ws
from hydra_umc_bridge_printer3d.service import ConfigError, parse_config, subscriber_factory

MINIMAL = {"moonraker": {"url": "http://127.0.0.1:7125"}}


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def snapshot(webhooks="ready", print_state="standby", bed=21.0, **extra):
    status = {
        "webhooks": {"state": webhooks, "state_message": "Printer is ready"},
        "print_stats": {"state": print_state, "filename": "part.gcode", "print_duration": 12.5},
        "extruder": {"temperature": 200.04, "target": 200.0},
        "heater_bed": {"temperature": bed, "target": 60.0},
        "display_status": {"progress": 0.5},
    }
    status.update(extra)
    return {"jsonrpc": "2.0", "id": ws.SUBSCRIBE_ID, "result": {"eventtime": 1.0, "status": status}}


def update(**objects):
    return {"jsonrpc": "2.0", "method": "notify_status_update", "params": [objects, 2.0]}


def states(messages):
    return [json.loads(m.payload) for m in messages if m.topic == ws.STATE_TOPIC]


def telemetry(messages):
    return [json.loads(m.payload) for m in messages if m.topic == ws.TELEMETRY_TOPIC]


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.tracker = ws.PrinterObjectTracker(clock=self.clock, telemetry_interval_seconds=1.0)

    def test_it_is_offline_until_the_first_snapshot(self):
        self.assertIs(self.tracker.status().state, MachineState.OFFLINE)
        self.assertEqual(self.tracker.handle(update(print_stats={"state": "printing"})), [])
        self.assertFalse(self.tracker.have_snapshot)

    def test_the_snapshot_publishes_a_retained_state_and_a_telemetry_message(self):
        out = self.tracker.handle(snapshot())
        self.assertEqual(states(out)[0]["state"], "IDLE")
        self.assertTrue(next(m for m in out if m.topic == ws.STATE_TOPIC).retain)
        reading = telemetry(out)[0]
        self.assertEqual(reading["progress"], 0.5)
        self.assertEqual(reading["bed"], {"temperature": 21.0, "target": 60.0})
        self.assertEqual(reading["filename"], "part.gcode")
        self.assertFalse(next(m for m in out if m.topic == ws.TELEMETRY_TOPIC).retain)

    def test_the_state_follows_the_print_without_polling(self):
        self.tracker.handle(snapshot())
        self.clock.now += 2
        out = self.tracker.handle(update(print_stats={"state": "printing"}))
        self.assertEqual(states(out)[0]["state"], "RUNNING")
        self.clock.now += 2
        self.assertEqual(states(self.tracker.handle(update(print_stats={"state": "paused"})))[0]["state"], "HOLDING")
        self.clock.now += 2
        self.assertEqual(states(self.tracker.handle(update(print_stats={"state": "error"})))[0]["state"], "FAULT")

    def test_an_unchanged_state_is_not_published_again_and_telemetry_is_rate_limited(self):
        self.tracker.handle(snapshot())
        quick = self.tracker.handle(update(extruder={"temperature": 201.0}))
        self.assertEqual(quick, [])
        self.clock.now += 1.5
        later = self.tracker.handle(update(extruder={"temperature": 202.0}))
        self.assertEqual(states(later), [])
        self.assertEqual(telemetry(later)[0]["extruder"]["temperature"], 202.0)

    def test_klippy_shutdown_is_published_at_once_as_fault(self):
        self.tracker.handle(snapshot())
        out = self.tracker.handle({"jsonrpc": "2.0", "method": "notify_klippy_shutdown", "params": []})
        self.assertEqual(states(out)[0]["state"], "FAULT")
        self.assertIn("shutdown", states(out)[0]["message"])
        self.assertIs(self.tracker.status().state, MachineState.FAULT)

    def test_a_webhooks_state_of_shutdown_in_the_snapshot_is_a_fault(self):
        self.assertEqual(states(self.tracker.handle(snapshot(webhooks="shutdown")))[0]["state"], "FAULT")

    def test_klippy_disconnected_and_ready_fail_closed_until_a_new_snapshot(self):
        self.tracker.handle(snapshot())
        out = self.tracker.handle({"method": "notify_klippy_disconnected", "params": []})
        self.assertEqual(states(out)[0]["state"], "OFFLINE")
        self.clock.now += 2
        out = self.tracker.handle({"method": "notify_klippy_ready", "params": []})
        self.assertIs(self.tracker.status().state, MachineState.OFFLINE)
        self.assertEqual(states(self.tracker.handle(snapshot()))[0]["state"], "IDLE")

    def test_a_lost_socket_makes_the_state_offline_and_forgets_the_snapshot(self):
        self.tracker.handle(snapshot())
        out = self.tracker.lost("gone")
        self.assertEqual(states(out)[0]["state"], "OFFLINE")
        self.assertFalse(self.tracker.have_snapshot)

    def test_messages_of_an_unknown_shape_are_ignored(self):
        for message in (None, [], "x", {"method": "something_else"}, {"method": "notify_status_update", "params": "no"}, {"id": ws.SUBSCRIBE_ID, "result": "no"}):
            self.assertEqual(self.tracker.handle(message), [])

    def test_a_value_that_is_not_a_number_is_not_published_as_one(self):
        out = self.tracker.handle(snapshot(extruder={"temperature": "hot", "target": True}))
        self.assertEqual(telemetry(out)[0]["extruder"], {"temperature": None, "target": None})


class FakeConnection:
    def __init__(self, messages, error=None):
        self.sent = []
        self.closed = False
        self._messages = list(messages)
        self._error = error

    def send(self, text):
        self.sent.append(json.loads(text))

    def recv(self):
        if self._messages:
            item = self._messages.pop(0)
            return item if item is None or isinstance(item, str) else json.dumps(item)
        raise self._error or OSError("closed")

    def close(self):
        self.closed = True


class SubscriberTests(unittest.TestCase):
    def make(self, connection=None, *, fail=None):
        published = []
        calls = []

        def connect(url, headers, timeout):
            calls.append((url, headers))
            if fail is not None:
                raise fail
            return connection

        subscriber = ws.MoonrakerSubscriber("ws://printer/websocket", published.append, api_key="K", connect=connect)
        return subscriber, published, calls

    def test_it_subscribes_reads_and_publishes_then_reports_the_loss(self):
        connection = FakeConnection([None, snapshot(), "not json", update(print_stats={"state": "printing"})])
        subscriber, published, calls = self.make(connection)
        subscriber.run_once()
        self.assertEqual(calls[0], ("ws://printer/websocket", {"X-Api-Key": "K"}))
        sent = connection.sent[0]
        self.assertEqual(sent["method"], "printer.objects.subscribe")
        self.assertEqual(set(sent["params"]["objects"]), set(ws.SUBSCRIBED_OBJECTS))
        seen = [s["state"] for s in states(published)]
        self.assertEqual(seen, ["IDLE", "RUNNING", "OFFLINE"])
        self.assertTrue(connection.closed)
        self.assertFalse(subscriber.healthy)

    def test_it_is_healthy_only_while_connected_with_a_snapshot(self):
        flags = []

        class Probe(FakeConnection):
            def recv(inner):
                flags.append(subscriber.healthy)
                return super().recv()

        connection = Probe([snapshot()])
        subscriber, _, _ = self.make(connection)
        subscriber.run_once()
        self.assertEqual(flags, [False, True])

    def test_it_subscribes_again_when_klippy_is_ready_again(self):
        connection = FakeConnection([snapshot(), {"method": "notify_klippy_ready", "params": []}])
        subscriber, _, _ = self.make(connection)
        subscriber.run_once()
        self.assertEqual([m["method"] for m in connection.sent], ["printer.objects.subscribe"] * 2)

    def test_a_socket_that_cannot_be_opened_publishes_offline_and_never_raises(self):
        subscriber, published, _ = self.make(fail=OSError("refused"))
        subscriber.run_once()
        self.assertEqual(states(published)[0]["state"], "OFFLINE")
        self.assertFalse(subscriber.healthy)

    def test_an_oversized_message_is_ignored(self):
        connection = FakeConnection(["x" * (ws.MAX_MESSAGE_BYTES + 1), snapshot()])
        subscriber, published, _ = self.make(connection)
        subscriber.run_once()
        self.assertEqual(states(published)[0]["state"], "IDLE")

    def test_stop_ends_the_loop(self):
        connection = FakeConnection([None, None], error=OSError("closed"))
        subscriber, _, _ = self.make(connection)
        subscriber.stop()
        subscriber.run_forever()
        self.assertEqual(connection.sent, [])


class SettingsTests(unittest.TestCase):
    def test_the_url_comes_from_the_moonraker_url_unless_given(self):
        self.assertEqual(ws.websocket_url("http://printer:7125"), "ws://printer:7125/websocket")
        self.assertEqual(ws.websocket_url("https://printer"), "wss://printer/websocket")
        self.assertEqual(ws.websocket_url("http://printer", "ws://other/websocket"), "ws://other/websocket")

    def test_it_is_off_by_default_and_the_table_is_checked(self):
        config = parse_config(MINIMAL)
        self.assertFalse(config.websocket.enabled)
        self.assertIsNone(subscriber_factory(config))
        on = parse_config({**MINIMAL, "websocket": {"enabled": True, "reconnect_seconds": 2}})
        self.assertIsNotNone(subscriber_factory(on))
        with self.assertRaisesRegex(ConfigError, "unknown key in websocket"):
            parse_config({**MINIMAL, "websocket": {"enable": True}})
        with self.assertRaisesRegex(ConfigError, "reconnect_seconds"):
            parse_config({**MINIMAL, "websocket": {"reconnect_seconds": 0}})
        with self.assertRaisesRegex(ConfigError, "ws"):
            parse_config({**MINIMAL, "websocket": {"url": "http://x"}})

    def test_the_factory_builds_a_subscriber_on_the_derived_url(self):
        config = parse_config({**MINIMAL, "websocket": {"enabled": True}})
        subscriber = subscriber_factory(config)(lambda message: None)
        self.assertEqual(subscriber._url, "ws://127.0.0.1:7125/websocket")

    def test_the_real_connection_needs_the_optional_package(self):
        import sys
        from unittest import mock

        with mock.patch.dict(sys.modules, {"websocket": None}):
            with self.assertRaisesRegex(RuntimeError, "websocket-client"):
                ws.connect_with_websocket_client("ws://x/websocket", {}, 1.0)


class RunForeverWiringTests(unittest.TestCase):
    """run_forever starts the subscriber with a publish function of the client, stops it, and polls only while it is not healthy."""

    def _run(self, healthy):
        import threading
        from unittest import mock

        from hydra_umc_bridge_printer3d import mqtt_transport

        class Fake:
            def __init__(self, publish):
                self.publish = publish
                self.started = self.stopped = False
                self.healthy = healthy

            def start(self):
                self.started = True
                self.publish(ws.MqttPublish(ws.STATE_TOPIC, "{}", retain=True))

            def stop(self):
                self.stopped = True

        made = []
        bridge = mock.MagicMock()
        bridge.global_stop = None
        bridge.handle_message.return_value = [ws.MqttPublish(ws.STATE_TOPIC, "{}", retain=True)]
        client = mock.MagicMock()
        client.loop_forever.side_effect = lambda: threading.Event().wait(0.3)

        def factory(publish):
            made.append(Fake(publish))
            return made[0]

        with mock.patch.object(mqtt_transport, "open_bridge_client", return_value=client):
            mqtt_transport.run_forever(bridge, "127.0.0.1", heartbeat_interval_s=0.01, subscriber_factory=factory)
        return made[0], bridge, client

    def test_a_healthy_subscriber_replaces_the_polling(self):
        subscriber, bridge, client = self._run(healthy=True)
        self.assertTrue(subscriber.started and subscriber.stopped)
        client.publish.assert_any_call(ws.STATE_TOPIC, "{}", qos=0, retain=True)
        bridge.handle_message.assert_not_called()

    def test_an_unhealthy_subscriber_falls_back_to_the_polling(self):
        _, bridge, _ = self._run(healthy=False)
        bridge.handle_message.assert_any_call("hydra/bridges/printer3d/cmd/status", b"")


if __name__ == "__main__":
    unittest.main()
