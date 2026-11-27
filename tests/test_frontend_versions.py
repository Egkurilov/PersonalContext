import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("check_frontend", Path(__file__).resolve().parent.parent / "scripts/check_frontend.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FrontendVersionTests(unittest.TestCase):
    def test_requires_exact_node_and_npm_versions(self):
        module.require_versions("24.22.3", "11.19.1", "v24.22.3", "11.19.1")
        for node, npm in (("v24.22.2", "11.19.1"), ("v24.22.3", "11.16.0"), ("24.22.3", "11.19.1")):
            with self.subTest(node=node, npm=npm), self.assertRaises(ValueError):
                module.require_versions("24.22.3", "11.19.1", node, npm)
