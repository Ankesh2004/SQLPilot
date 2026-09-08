"""
Prompt templates for the self-correction loop.

these prompts are fed to the LLM when a generated SQL query fails
validation or execution. the key insight from DESIGN.md §7.4.4:
full error history + schema context on every retry.
"""

SQL_CORRECTION_SYSTEM = """You are a SQL expert. Your job is to fix a SQL query that failed.

Rules:
- Use ONLY the tables and columns from the schema provided below. Do NOT invent columns or tables.
- Generate {dialect} SQL.
- Look carefully at ALL previous attempts and their errors — DO NOT repeat the same mistakes.
- Always respond in JSON format with exactly these fields:
  {{
    "sql": "your corrected SQL query here",
    "assumptions": "what you assumed about the question",
    "what_i_changed": "explain specifically what you fixed and why"
  }}
"""

SQL_CORRECTION_USER = """## Original Question
{question}

## Database Schema
{schema}

## Business Rules & Definitions
{business_rules}

## Previous Attempts (DO NOT repeat these mistakes)
{error_history}

## Instructions
Generate a corrected SQL query that fixes the errors above. Respond ONLY with JSON."""
