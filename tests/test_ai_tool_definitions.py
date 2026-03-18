# -*- coding: utf-8 -*-
"""Unit tests for ai_tool_definitions.py"""
import re
import unittest

from mes_dashboard.services.ai_tool_definitions import (
    TIER_1_TOOLS,
    build_single_tool_description,
    build_tool_prompt_block,
)
from mes_dashboard.services.ai_function_registry import REGISTRY, build_agent_system_prompt


def _estimate_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English text.

    Chinese characters ≈ 1.5 tokens each; ASCII ≈ 4 chars per token.
    This is a rough approximation for gpt-oss:120b tokenizer.
    """
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
    ascii_chars = len(text) - cjk
    return int(cjk * 1.5 + ascii_chars / 4)


class TestBuildSingleToolDescription(unittest.TestCase):
    def test_required_and_optional_params_indicated(self):
        """Tier 1 tool with required/optional params must label them correctly."""
        name = "reject_trend"
        entry = REGISTRY.get(name)
        if entry is None:
            self.skipTest(f"{name} not in REGISTRY")
        desc = build_single_tool_description(name, entry)
        self.assertIn(name, desc)
        self.assertIn("必填", desc)
        self.assertIn("選填", desc)

    def test_tool_name_and_description_present(self):
        name = "reject_summary"
        entry = REGISTRY.get(name)
        if entry is None:
            self.skipTest(f"{name} not in REGISTRY")
        desc = build_single_tool_description(name, entry)
        self.assertIn(name, desc)
        self.assertIn(entry["description"], desc)

    def test_no_params_tool(self):
        """Tools with no params should say so."""
        fake_entry = {"description": "測試工具", "params": {}}
        desc = build_single_tool_description("test_tool", fake_entry)
        self.assertIn("無", desc)


class TestBuildToolPromptBlock(unittest.TestCase):
    def test_tier1_tools_present(self):
        """Prompt block must include all Tier 1 tools that exist in REGISTRY."""
        block = build_tool_prompt_block()
        for name in TIER_1_TOOLS:
            if name in REGISTRY:
                self.assertIn(name, block, f"Tier 1 tool {name} missing from prompt block")

    def test_special_tools_present(self):
        """Prompt block must include query_database and search_tools special tools."""
        block = build_tool_prompt_block()
        self.assertIn("query_database", block)
        self.assertIn("search_tools", block)

    def test_token_length_reasonable(self):
        """Token estimate for mixed CJK/ASCII content ≤ 1500 tokens."""
        block = build_tool_prompt_block()
        approx_tokens = _estimate_tokens(block)
        self.assertLessEqual(
            approx_tokens, 1500,
            f"Tool prompt block too long: ~{approx_tokens} tokens (max 1500)"
        )


class TestBuildAgentSystemPrompt(unittest.TestCase):
    def test_contains_required_sections(self):
        prompt = build_agent_system_prompt()
        required = ["MES", "tool_call", "search_tools", "query_database"]
        for section in required:
            self.assertIn(section, prompt, f"System prompt missing section: {section}")

    def test_contains_business_context(self):
        """System prompt must include SYSTEM_OVERVIEW and BUSINESS_TERMINOLOGY content."""
        prompt = build_agent_system_prompt()
        # SYSTEM_OVERVIEW references the MES system name
        self.assertIn("系統背景", prompt)
        # BUSINESS_TERMINOLOGY references factory terms
        self.assertIn("業務術語", prompt)

    def test_token_length_within_4k(self):
        """Token estimate for mixed CJK/ASCII content ≤ 4000 tokens."""
        prompt = build_agent_system_prompt()
        approx_tokens = _estimate_tokens(prompt)
        self.assertLessEqual(
            approx_tokens, 4000,
            f"Agent system prompt too long: ~{approx_tokens} tokens (max 4000)"
        )

    def test_contains_date(self):
        from datetime import date
        prompt = build_agent_system_prompt()
        today = date.today().isoformat()
        self.assertIn(today, prompt)


if __name__ == "__main__":
    unittest.main()
