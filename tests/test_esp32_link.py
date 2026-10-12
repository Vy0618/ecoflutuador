from collections import deque
import itertools
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from esp32_link import Esp32Link


class FakeSerial:
    def __init__(self, ready=True, heartbeat=True):
        self.ready = ready
        self.heartbeat = heartbeat
        self.acknowledge = True
        self.replies = deque()
        self.messages = []
        self.closed = False

    def write(self, message):
        self.messages.append(message)
        if message == b"?\n":
            if self.ready:
                if self.heartbeat:
                    self.replies.append(b"CAPS:HEARTBEAT\n")
                self.replies.append(b"READY\n")
        elif self.acknowledge:
            self.replies.append(b"HB_OK\n" if message == b"h\n" else b"CMD_OK:" + message)
        return len(message)

    def readline(self):
        return self.replies.popleft() if self.replies else b""

    def close(self):
        self.closed = True


class Esp32LinkTests(unittest.TestCase):
    def test_handshake_commands_repeated_command_and_stop_on_close(self):
        device = FakeSerial()
        with patch("serial.Serial", return_value=device) as serial_class:
            link = Esp32Link("test-port")
            for command in ("a", "w", "w", "d", "s"):
                link.send(command)
            link.close()
        serial_class.assert_called_once_with("test-port", 115200, timeout=.1, write_timeout=.5)
        self.assertEqual(device.messages, [b"?\n", b"s\n", b"a\n", b"w\n", b"d\n", b"s\n", b"s\n"])
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
            self.assertEqual(device.messages, [b"?\n", b"s\n", b"w\n", b"h\n"])
            clock.return_value = 1.2
            self.assertTrue(link.send("s"))
            self.assertEqual(device.messages[-1], b"s\n")
            link.close()

    def test_old_firmware_uses_limited_renewal_of_existing_commands(self):
        device = FakeSerial(heartbeat=False)
        with patch("serial.Serial", return_value=device), \
             patch("esp32_link.time.monotonic", return_value=0) as clock:
            link = Esp32Link("test-port")
            link.send("w")
            clock.return_value = .9
            link.send("w")
            clock.return_value = 1.1
            link.send("w")
            self.assertEqual(device.messages, [b"?\n", b"s\n", b"w\n", b"w\n"])
            self.assertFalse(link.heartbeat_supported)
            link.close()

    def test_delayed_startup_ready_does_not_block_initial_stop(self):
        device = FakeSerial()
        original_write = device.write

        def write(message):
            if message == b"s\n":
                device.replies.append(b"READY\n")
            return original_write(message)

        device.write = write
        with patch("serial.Serial", return_value=device):
            link = Esp32Link("test-port")
            self.assertEqual(link.last_command, "s")
            device.write = original_write
            link.close()

    def test_reset_and_firmware_timeout_stop_and_abort_communication(self):
        for reply in (b"READY\n", b"ARMING\n", b"TIMEOUT:s\n", b"ERROR:PWM\n"):
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


if __name__ == "__main__":
    unittest.main()
