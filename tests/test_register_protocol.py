import json
import tempfile
import unittest
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import register_protocol as protocol


EXPECTED = r'"C:\Python\pythonw.exe" "D:\NewProject\launch_local.py" --uri "%1"'
OLD = r'"C:\Python\pythonw.exe" "D:\OldProject\launch_local.py" --uri "%1"'


class ProtocolRegistrationTests(unittest.TestCase):
    @contextmanager
    def registry(self, folder):
        handle = MagicMock()
        handle.__enter__.return_value = handle
        with ExitStack() as stack:
            stack.enter_context(patch.object(protocol.winreg, "OpenKey", return_value=handle))
            stack.enter_context(patch.object(protocol.winreg, "QueryValue", return_value=OLD))
            create = stack.enter_context(patch.object(protocol.winreg, "CreateKey", return_value=handle))
            write = stack.enter_context(patch.object(protocol.winreg, "SetValueEx"))
            delete = stack.enter_context(patch.object(protocol.winreg, "DeleteKey"))
            command = stack.enter_context(patch.object(protocol, "protocol_command", return_value=EXPECTED))
            stack.enter_context(patch.object(protocol, "CONFIG", folder / "config.json"))
            stack.enter_context(patch.object(protocol, "load_config",
                                             return_value={"download_directory": str(folder)}))
            yield create, write, delete, command

    def test_moved_registration_requires_explicit_force(self):
        with tempfile.TemporaryDirectory() as folder, self.registry(Path(folder)) as (create, write, delete, command):
            with self.assertRaisesRegex(RuntimeError, "--force"):
                protocol.main([])
            create.assert_not_called()
            write.assert_not_called()
            delete.assert_not_called()
            self.assertFalse((Path(folder) / "config.json").exists())

    def test_force_updates_command_and_preserves_download_directory(self):
        with tempfile.TemporaryDirectory() as folder, self.registry(Path(folder)) as (create, write, delete, command):
            with patch.object(protocol, "default_download_directory",
                              side_effect=AssertionError("Existing download directory must be preserved")):
                self.assertEqual(protocol.main(["--force"]), 0)
            self.assertEqual(write.call_args_list[-1].args[-1], EXPECTED)
            config = json.loads((Path(folder) / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["download_directory"], str(Path(folder).resolve()))
            delete.assert_not_called()

    def test_unregister_from_new_location_does_not_require_pythonw(self):
        with tempfile.TemporaryDirectory() as folder, self.registry(Path(folder)) as (create, write, delete, command):
            command.side_effect = AssertionError("Unregister must not require Python")
            self.assertEqual(protocol.main(["--unregister"]), 0)
            self.assertEqual(delete.call_count, 4)
            create.assert_not_called()
            write.assert_not_called()

    def test_check_still_rejects_old_path_with_force(self):
        with tempfile.TemporaryDirectory() as folder, self.registry(Path(folder)) as (create, write, delete, command):
            with self.assertRaisesRegex(RuntimeError, "not registered"):
                protocol.main(["--check", "--force"])
            create.assert_not_called()
            write.assert_not_called()
            delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
