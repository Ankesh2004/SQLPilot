# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---
## 5. Coding Standards

**Style & formatting:**
- Python: follow PEP 8
- TypeScript: follow Google TypeScript style
- Markdown: treat as HTML (semantic tags, proper structure)
- SQL: uppercase keywords, snake_case identifiers, use CTEs for readability

**Testing:**
- Unit tests: pytest (Python), Vitest (TypeScript)
- Integration tests: use Docker Compose for external services
- End-to-end: Playwright for browser automation
- Tests MUST pass before code is considered complete

**Security:**
- Never commit secrets or API keys
- Use environment variables for sensitive config
- Always sanitize user inputs
- Enforce rate limiting and input validation
- Follow OWASP Top 10 for web applications

**Performance:**
- Cache expensive operations
- Use efficient algorithms (know Big-O)
- Index database tables appropriately
- Avoid N+1 queries

**Documentation:**
- Inline comments for complex logic
- Docstrings/JSDoc for all public APIs
- READMEs for new modules/services
- Keep docs updated with code changes

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.