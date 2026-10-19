import unittest
from unittest import result

from main import WORKSPACE, execute_tool


class TestALFHAFileTools(unittest.TestCase):

    def test_unknown_tool_is_rejected(self):
        result = execute_tool("unknown_tool", {})
        self.assertIn("Unknown tool", result)

    def test_path_traversal_is_rejected(self):
        result = execute_tool(
            "read_workspace_file",
            {"filename": "../main.py"},
        )
        self.assertIn("outside the workspace", result)

    def test_disallowed_extension_is_rejected(self):
        result = execute_tool(
            "write_workspace_file",
            {
                "filename": "safety-test.exe",
                "content": "test",
            },
        )
        self.assertIn("file type is not allowed", result)

    def test_existing_file_is_not_overwritten(self):
        result = execute_tool(
            "write_workspace_file",
            {
                "filename": "agent-test.txt",
                "content": "SHOULD_NOT_OVERWRITE",
            },
        )
        self.assertIn("already exists", result)

    def test_edit_rejects_path_traversal(self):
        result = execute_tool(
        "edit_workspace_file",
        {
            "filename": "../main.py",
            "old_text": "something",
            "new_text": "replacement",
        },
        )
        self.assertIn("outside the workspace", result)


    def test_edit_rejects_missing_file(self):
        result = execute_tool(
        "edit_workspace_file",
        {
            "filename": "nonexistent-edit-test.txt",
            "old_text": "hello",
            "new_text": "world",
        },
        )
        self.assertIn("does not exist", result)


    def test_edit_rejects_empty_search(self):
        result = execute_tool(
        "edit_workspace_file",
        {
            "filename": "edit-test.txt",
            "old_text": "",
            "new_text": "replacement",
        },
        )
        self.assertIn("cannot be empty", result)


    def test_edit_rejects_multiple_matches(self):
        from pathlib import Path
        from main import WORKSPACE

        target = WORKSPACE / "edit-multiple-test.txt"

        self.assertEqual(target.name, "edit-multiple-test.txt")

        try:
            target.write_text("hello hello", encoding="utf-8")
            self.assertEqual(target.read_text(encoding="utf-8"), "hello hello")

            result = execute_tool(
                "edit_workspace_file",
                {
                    "filename": "edit-multiple-test.txt",
                    "old_text": "hello",
                    "new_text": "world",
                },
            )

            self.assertIn("Multiple matches", result)
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "hello hello",
            )
        finally:
            target.unlink(missing_ok=True)

    def test_python_file_creation(self):
        from main import WORKSPACE

        target = WORKSPACE / "alfha-python-test.py"

        try:
            result = execute_tool(
                "write_workspace_file",
                {
                    "filename": "alfha-python-test.py",
                    "content": "print('Hello from ALFHA')",
                },
            )

            self.assertIn("Successfully", result)
            self.assertTrue(target.is_file())

        finally:
            target.unlink(missing_ok=True)
    def test_syntax_tool_is_registered(self):
        result = execute_tool(
            "check_python_syntax",
            {"filename": "syntax-test.py"},
        )

        self.assertNotIn("Unknown tool", result)
        self.assertTrue(
            "Syntax OK" in result or "Syntax ERROR" in result
        )

if __name__ == "__main__":
    unittest.main()
