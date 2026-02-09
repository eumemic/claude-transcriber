# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## TDD Discipline

- Always write failing tests BEFORE implementing fixes. Do not implement code changes first and then write tests after.
- When given a bug fix plan, the workflow is: 1) Write failing test, 2) Run it to confirm it fails, 3) Implement the fix, 4) Run test to confirm it passes, 5) Run the full test suite.

## Change Scope

- Only change what is explicitly requested. Do NOT change unrelated configs, dependency versions, or other tangential settings when asked to update a single package or feature.
- If you think adjacent changes are needed, ASK first before making them.

## Architecture Decisions

- Prefer proper architectural solutions over band-aids, hacks, or polling-based workarounds.
- When an existing abstraction can serve a new need, USE it rather than creating a parallel one. Ask if unsure.

## Testing After Refactors

- After ANY rename, move, or refactor, immediately grep for ALL references to the old name across the entire codebase (including test files) and update them.
- Never dismiss a failing test as "pre-existing" without verifying it passed before your changes.
