# duo benchmark results

## SWE-bench Verified, hard subset (2026-11-10)

Six of the 45 issues that SWE-bench Verified rates "1-4 hours" for a human, from Django, SymPy and pytest. Each
contestant got a fresh checkout at the issue's commit and the issue text. Fixes were graded by the official
`swebench` harness (v5.0.2) in its Docker images; the harness resolved all six official fixes first, as a check.
Models: Claude Code on Sonnet, Codex on its default model, duo on both. One run per task and contestant.

| Task | Claude alone | Codex alone | duo |
|---|---|---|---|
| django__django-13128 | resolved | no | resolved |
| django__django-13212 | no | no | no |
| django__django-13449 | resolved | resolved | resolved |
| sympy__sympy-13852 | no | no | no |
| sympy__sympy-14248 | no | resolved | resolved |
| pytest-dev__pytest-10356 | no | no | no |
| **Resolved** | **2/6** | **2/6** | **3/6** |
| Average time per task | 0.7 min | 1.6 min | 5.5 min |

duo across the six runs: 221 messages, 3 objections raised, 52 cross-checks, 58 approval cards (auto-approved in
benchmark mode). Claude Code alone cost $1.17 for all six; Codex alone used about 2.6M tokens.

**Reading it honestly.** duo solved every task that either agent solved alone, and neither alone solved all of
those. It solved nothing that both agents missed. It took about 4 to 8 times longer. Six tasks with one run each is
a small sample: treat this as a first signal, not a result. Rerun it with `bench/duo/swe.py` (see the docstring).

## Small tasks (2026-11-10)

Three single-file tasks with hidden tests (`bench/duo/tasks/`). Every contestant scored 100% on all three, so they
show nothing about quality; on small tasks duo is only overhead.
