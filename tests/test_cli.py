from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from projectlens_ai.cli import build_parser


class CliTests(unittest.TestCase):
    def test_parser_accepts_ask_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["ask", "where is configuration handled?", ".", "--limit", "2"])

        self.assertEqual(args.command, "ask")
        self.assertEqual(args.limit, 2)
        self.assertEqual(args.handler.__name__, "handle_ask")


    def test_parser_accepts_checks_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["checks", ".", "--json"])

        self.assertEqual(args.command, "checks")
        self.assertTrue(args.json)
        self.assertEqual(args.handler.__name__, "handle_checks")
    def test_parser_accepts_hybrid_search_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["search", "database connection", ".", "--hybrid"])

        self.assertEqual(args.command, "search")
        self.assertTrue(args.hybrid)
        self.assertFalse(args.semantic)



    def test_parser_accepts_capabilities_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["capabilities", ".", "--json"])

        self.assertEqual(args.command, "capabilities")
        self.assertTrue(args.json)
        self.assertEqual(args.handler.__name__, "handle_capabilities")

    def test_parser_accepts_doctor_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["doctor", "."])

        self.assertEqual(args.command, "doctor")
        self.assertEqual(args.path, ".")
        self.assertEqual(args.handler.__name__, "handle_doctor")


    def test_parser_accepts_eval_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["eval", ".", "--cases", "docs/eval/projectlens-self.json", "--json"])

        self.assertEqual(args.command, "eval")
        self.assertEqual(args.cases, "docs/eval/projectlens-self.json")
        self.assertTrue(args.json)
        self.assertEqual(args.handler.__name__, "handle_eval")

if __name__ == "__main__":
    unittest.main()
