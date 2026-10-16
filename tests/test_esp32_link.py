from collections import deque
import itertools
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from esp32_link import Esp32Link


def startup_messages(output="OLED", ultrasonic=False):
    return [b"?\n", b"s\n", f"CONFIG:{output}:{int(ultrasonic)}\n".encode("ascii"), b"s\n"]


class FakeSerial:
    def __init__(self, ready=True, heartbeat=True, iniciar=True):
        self.ready = ready
        self.heartbeat = heartbeat
        self.iniciar = iniciar
        self.sensor_active = iniciar
        self.configured = False
        self.configuration_reply = None
        self.configuration_ready = True
        self.acknowledge = True
        self.replies = deque()
        self.messages = []
        self.command = "s"
        self.closed = False

    def write(self, message):
        self.messages.append(message)
        if message == b"?\n" or message == b"s\n":
            self.command = "s"
        elif message in (b"a\n", b"w\n", b"d\n"):
            self.command = message[:1].decode("ascii") if self.iniciar else "s"
        if message == b"?\n":
            if self.ready:
                if self.heartbeat:
                    self.replies.append(b"CAPS:HEARTBEAT\n")
                if self.iniciar is not None:
                    self.replies.append(b"INICIAR:1\n" if self.iniciar else b"INICIAR:0\n")
                self.replies.append(b"READY\n" if self.configured or self.iniciar is None else b"CONFIG_REQUIRED\n")
        elif message.startswith(b"CONFIG:"):
            if self.sensor_active is None:
                self.replies.append(b"ERROR:COMANDO_INVALIDO\n")
            else:
                self.configured = True
                self.iniciar = self.sensor_active if message.endswith(b":1\n") else True
                self.replies.append(self.configuration_reply or b"CONFIG_OK:" + message[7:])
                self.replies.append(b"INICIAR:1\n" if self.iniciar else b"INICIAR:0\n")
                self.replies.append(b"ARMING\n")
                if self.configuration_ready:
                    self.replies.append(b"READY\n")
        elif self.acknowledge:
            if message in (b"a\n", b"w\n", b"d\n") and not self.iniciar:
                self.replies.append(b"INICIAR:0\n")
            else:
                self.replies.append(b"HB_OK\n" if message == b"h\n" else b"CMD_OK:" + message)
        return len(message)

    @property
    def in_waiting(self):
        return sum(map(len, self.replies))

    def readline(self, size=-1):
        reply = self.replies.popleft() if self.replies else b""
        if 0 <= size < len(reply):
            self.replies.appendleft(reply[size:])
            return reply[:size]
        return reply

    def close(self):
        self.closed = True


class Esp32LinkTests(unittest.TestCase):
    def test_output_and_sensor_configuration_defaults_and_overrides(self):
        for output, requested, enabled in (("oled", None, False), ("motors", None, True),
                                            ("oled", True, True), ("motors", False, False)):
            device = FakeSerial(iniciar=False)
            with self.subTest(output=output, ultrasonic=requested), patch("serial.Serial", return_value=device):
                link = Esp32Link("test-port", output=output, ultrasonic=requested)
                self.assertEqual((link.output, link.ultrasonic), (output, enabled))
                self.assertIs(link.iniciar, not enabled)
                self.assertEqual(device.messages, startup_messages("OLED" if output == "oled" else "MOTORES", enabled))
                link.close()

    def test_wrong_configuration_or_missing_ready_aborts_before_movement(self):
        for mismatch in (True, False):
            device = FakeSerial()
            if mismatch:
                device.configuration_reply = b"CONFIG_OK:MOTORES:1\n"
            else:
                device.configuration_ready = False
            clock = itertools.count(step=.1)
            with self.subTest(mismatch=mismatch), patch("serial.Serial", return_value=device), \
                 patch("esp32_link.time.monotonic", side_effect=lambda: next(clock)):
                with self.assertRaises(RuntimeError if mismatch else TimeoutError):
                    Esp32Link("test-port")
            self.assertTrue(device.closed)
            self.assertEqual(device.command, "s")
            self.assertFalse(any(message in (b"a\n", b"w\n", b"d\n") for message in device.messages))

    def test_connection_to_already_configured_board_still_applies_requested_mode(self):
        device = FakeSerial(iniciar=False)
        device.configured = True
        with patch("serial.Serial", return_value=device):
            link = Esp32Link("test-port")
            self.assertTrue(link.iniciar)
            self.assertEqual(device.messages, startup_messages())
            link.close()

    def test_invalid_modes_are_rejected_before_opening_serial(self):
        for options in ({"output": "unknown"}, {"ultrasonic": "false"}):
            with self.subTest(options=options), patch("serial.Serial") as serial_class:
                with self.assertRaises(ValueError):
                    Esp32Link("test-port", **options)
                serial_class.assert_not_called()

    def test_handshake_consumes_initial_state_before_ready(self):
        for active in (False, True):
            with self.subTest(active=active), patch("serial.Serial", return_value=FakeSerial(iniciar=active)):
                link = Esp32Link("test-port", ultrasonic=True)
                self.assertIs(link.iniciar, active)
                self.assertFalse(link.activation_changed)
                self.assertTrue(link.heartbeat_supported)
                self.assertEqual(link.connection.messages, startup_messages(ultrasonic=True))
                link.close()

    def test_inactive_sensor_cannot_send_movement(self):
        with patch("serial.Serial", return_value=FakeSerial(iniciar=False)):
            link = Esp32Link("test-port", ultrasonic=True)
            self.assertFalse(link.iniciar)
            for command in ("a", "w", "d"):
                self.assertFalse(link.send(command, force=True))
            self.assertEqual(link.connection.messages, startup_messages(ultrasonic=True))
            link.close()

    def test_legacy_firmware_rejects_configuration_and_closes_without_movement(self):
        device = FakeSerial(iniciar=None)
        with patch("serial.Serial", return_value=device), self.assertRaises(RuntimeError):
            Esp32Link("test-port")
        self.assertTrue(device.closed)
        self.assertEqual(device.command, "s")
        self.assertEqual(device.messages, startup_messages())

    def test_poll_preserves_partial_state_frames_and_requires_cycle_reset(self):
        device = FakeSerial(iniciar=False)
        with patch("serial.Serial", return_value=device):
            link = Esp32Link("test-port", ultrasonic=True)
            device.iniciar = True
            device.replies.append(b"INIC")
            link.poll()
            self.assertFalse(link.iniciar)
            self.assertFalse(link.activation_changed)
            device.replies.append(b"IAR:1\n")
            link.poll()
            self.assertTrue(link.iniciar)
            self.assertTrue(link.activation_changed)
            self.assertFalse(link.send("w"))
            self.assertEqual(device.messages, startup_messages(ultrasonic=True))
            link.activation_changed = False
            self.assertTrue(link.send("w"))
            link.close()

    def test_poll_detects_expiry_and_reactivation_in_the_same_queue(self):
        device = FakeSerial()
        with patch("serial.Serial", return_value=device):
            link = Esp32Link("test-port")
            link.send("w")
            device.replies.extend((b"INICIAR:0\n", b"INICIAR:1\n"))
            link.poll()
            self.assertTrue(link.iniciar)
            self.assertTrue(link.activation_changed)
            count = len(device.messages)
            self.assertFalse(link.send("d"))
            self.assertEqual(len(device.messages), count)
            link.close()

    def test_expiry_during_movement_ack_is_a_normal_stop(self):
        device = FakeSerial()
        with patch("serial.Serial", return_value=device):
            link = Esp32Link("test-port")
            original_write = device.write

            def write(message):
                if message == b"w\n":
                    device.iniciar = False
                return original_write(message)

            device.write = write
            self.assertFalse(link.send("w"))
            self.assertFalse(link.iniciar)
            self.assertTrue(link.activation_changed)
            self.assertFalse(link.failed)
            self.assertEqual(link.last_command, "s")
            self.assertEqual(device.messages, startup_messages() + [b"w\n", b"s\n"])
            link.close()

    def test_cancelled_ack_stops_movement_accepted_after_a_new_window_started(self):
        device = FakeSerial()
        with patch("serial.Serial", return_value=device):
            link = Esp32Link("test-port")
            original_write = device.write

            def write(message):
                if message == b"w\n":
                    # A escrita antiga chegou apos a expiracao e nova ativacao.
                    device.replies.extend((b"INICIAR:0\n", b"INICIAR:1\n"))
                return original_write(message)

            device.write = write
            self.assertFalse(link.send("w"))
            self.assertEqual(device.messages, startup_messages() + [b"w\n", b"s\n"])
            self.assertEqual(device.command, "s")
            self.assertFalse(link.failed)
            link.poll()
            self.assertTrue(link.iniciar)
            self.assertTrue(link.activation_changed)
            self.assertFalse(link.send("d"))
            self.assertEqual(device.command, "s")
            link.close()

    def test_state_can_expire_while_waiting_for_heartbeat_ack(self):
        device = FakeSerial()
        with patch("serial.Serial", return_value=device), \
             patch("esp32_link.time.monotonic", return_value=0) as clock:
            link = Esp32Link("test-port")
            link.send("w")
            original_write = device.write

            def write(message):
                if message == b"h\n":
                    device.iniciar = False
                    device.replies.append(b"INICIAR:0\n")
                return original_write(message)

            device.write = write
            clock.return_value = 1.1
            self.assertFalse(link.send("w"))
            self.assertFalse(link.iniciar)
            self.assertFalse(link.failed)
            self.assertEqual(link.last_command, "s")
            self.assertTrue(link.activation_changed)
            link.close()

    def test_handshake_commands_repeated_command_and_stop_on_close(self):
        device = FakeSerial()
        with patch("serial.Serial", return_value=device) as serial_class:
            link = Esp32Link("test-port")
            for command in ("a", "w", "w", "d", "s"):
                link.send(command)
            link.close()
        serial_class.assert_called_once_with("test-port", 115200, timeout=.1, write_timeout=.5)
        self.assertEqual(device.messages, startup_messages() + [b"a\n", b"w\n", b"d\n", b"s\n", b"s\n"])
        self.assertTrue(device.closed)

    def test_ready_timeout_closes_port_without_movement(self):
        device = FakeSerial(ready=False)
        clock = itertools.count(step=.1)
        with patch("serial.Serial", return_value=device), \
             patch("esp32_link.time.monotonic", side_effect=lambda: next(clock)):
            with self.assertRaises(TimeoutError):
                Esp32Link("test-port")
        self.assertEqual(device.messages, [b"?\n", b"s\n"])
        self.assertTrue(device.closed)

    def test_missing_ack_is_reported_and_port_is_closed(self):
        device = FakeSerial()
        clock = itertools.count(step=.1)
        with patch("serial.Serial", return_value=device), \
             patch("esp32_link.time.monotonic", side_effect=lambda: next(clock)):
            link = Esp32Link("test-port")
            device.acknowledge = False
            with self.assertRaises(TimeoutError):
                link.send("a")
            self.assertEqual(device.messages[-1], b"s\n")
            with self.assertRaises(RuntimeError):
                link.send("w")
            with self.assertRaises(TimeoutError):
                link.close()
        self.assertEqual(device.messages[-1], b"s\n")
        self.assertTrue(device.closed)

    def test_heartbeat_refreshes_without_repeating_motor_command(self):
        device = FakeSerial()
        with patch("serial.Serial", return_value=device), \
             patch("esp32_link.time.monotonic", return_value=0) as clock:
            link = Esp32Link("test-port")
            self.assertTrue(link.send("w"))
            clock.return_value = .9
            self.assertFalse(link.send("w"))
            clock.return_value = 1.1
            self.assertFalse(link.send("w"))
            self.assertEqual(device.messages, startup_messages() + [b"w\n", b"h\n"])
            clock.return_value = 1.2
            self.assertTrue(link.send("s"))
            self.assertEqual(device.messages[-1], b"s\n")
            link.close()

    def test_firmware_without_heartbeat_uses_limited_command_renewal(self):
        device = FakeSerial(heartbeat=False)
        with patch("serial.Serial", return_value=device), \
             patch("esp32_link.time.monotonic", return_value=0) as clock:
            link = Esp32Link("test-port")
            link.send("w")
            clock.return_value = .9
            link.send("w")
            clock.return_value = 1.1
            link.send("w")
            self.assertEqual(device.messages, startup_messages() + [b"w\n", b"w\n"])
            self.assertFalse(link.heartbeat_supported)
            link.close()

    def test_delayed_startup_ready_does_not_block_initial_stop(self):
        device = FakeSerial()
        original_write = device.write

        def write(message):
            if message == b"s\n" and not device.configured:
                device.replies.append(b"READY\n")
            return original_write(message)

        device.write = write
        with patch("serial.Serial", return_value=device):
            link = Esp32Link("test-port")
            self.assertEqual(link.last_command, "s")
            device.write = original_write
            link.close()

    def test_reset_and_firmware_timeout_stop_and_abort_communication(self):
        for reply in (b"READY\n", b"ARMING\n", b"CONFIG_REQUIRED\n", b"TIMEOUT:s\n", b"ERROR:PWM\n"):
            with self.subTest(reply=reply), patch("serial.Serial", return_value=FakeSerial()) as serial_class:
                device = serial_class.return_value
                link = Esp32Link("test-port")
                link.send("w")
                device.replies.append(reply)
                with self.assertRaises(RuntimeError):
                    link.send("a")
                self.assertEqual(device.messages[-1], b"s\n")
                self.assertTrue(link.failed)
                link.close()

    def test_partial_write_requests_emergency_stop(self):
        device = FakeSerial()
        with patch("serial.Serial", return_value=device):
            link = Esp32Link("test-port")
            original_write = device.write

            def write(message):
                if message == b"w\n":
                    device.messages.append(message)
                    return 1
                return original_write(message)

            device.write = write
            with self.assertRaises(OSError):
                link.send("w")
            self.assertEqual(device.messages[-1], b"s\n")
            link.close()

    def test_invalid_command_is_rejected_before_write(self):
        device = FakeSerial()
        with patch("serial.Serial", return_value=device):
            link = Esp32Link("test-port")
            count = len(device.messages)
            with self.assertRaises(ValueError):
                link.send("x")
            self.assertEqual(len(device.messages), count)
            link.close()

    def test_overlong_reply_aborts_and_requests_stop(self):
        for chunks in ((b"x" * 5000,), (b"x" * 100, b"x" * 100)):
            device = FakeSerial()
            with self.subTest(chunks=len(chunks)), patch("serial.Serial", return_value=device):
                link = Esp32Link("test-port")
                link.send("w")
                device.replies.extend(chunks)
                with self.assertRaisesRegex(RuntimeError, "128 bytes"):
                    link.poll()
                self.assertTrue(link.failed)
                self.assertEqual(device.command, "s")
                self.assertLessEqual(len(link.reply_buffer), link.MAX_REPLY_BYTES)
                # A porta deve fechar mesmo que a entrada continue corrompida.
                with self.assertRaises(RuntimeError):
                    link.close()
                self.assertTrue(device.closed)


if __name__ == "__main__":
    unittest.main()
