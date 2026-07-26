"""Composable Canvas (chunk-12): natural-language → chart-spec → SQL → data.

The LLM composes a validated chart spec from a fixed grammar over a curated mart
schema; the spec resolves to a parameterized Snowflake query. See ADR-013.
"""
