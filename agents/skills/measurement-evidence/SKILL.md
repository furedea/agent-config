---
name: measurement-evidence
description: >
    Use when reporting or comparing a performance number, benchmark, or evaluation result, or when
    improving performance. Requires a predefined claim, a named bottleneck, recorded conditions,
    counted errors and exclusions, repeated runs with spread, and a reproducible report.
---

# Measurement Evidence

Use this before trusting, reporting, or acting on a measured number: a speedup, regression,
throughput, latency, or evaluation score. Support each answer with evidence from a run, not a guess
from reading the code. Adapted from the MIT-licensed `pstack` skills by Lauren Tan.

A quick ballpark the user asked for may be one run: say it is one run and still check errors and
whether the work happened. A choice between options is never a ballpark.

## Before Running

- Write the claim in the words you would ship ("export is 30% faster at p50 on the 60k-row
  dataset") and the result that would change a decision. The checks below test that sentence.
- Read the measurement script. Note what it times, counts, and ignores.
- Check machine load. If it is busy, stop the cause or interleave the compared sides and say so.
- Stop when run-to-run spread exceeds the effect you expect.

## Checks

1. **Bottleneck.** Name what bounds the result (a core, lock, disk, network, or the load generator)
   from a profile or system counters, then map it to source. Profile in a run you do not report.
   If you cannot say why the number is not twice as good, you do not know what you measured.
2. **Conditions.** Run every side as production runs it: release build, production flags, warm or
   cold caches as in production, and the same data. A side left on defaults compares settings, not
   implementations. Record versions, hardware, OS, seed, model version, parameters, and data
   version.
3. **Limits.** Do the arithmetic: throughput against bandwidth, time saved against the time the
   changed piece took. Removing a piece that takes 10% of the run makes it at most about 11%
   faster. A result past a limit measured something other than the work.
4. **Errors and exclusions.** Count failures, timeouts, retries, and excluded samples, and check
   that outputs are correct, not merely present. Report every exclusion with its reason.
5. **Repetition.** Run each side at least 5 times, alternating (A, B, A, B) so warmup and drift
   favor neither. Report the median and range. A gap inside the run-to-run variation is no
   measurable difference.
6. **Relevance.** Relate a micro result to the end-to-end path a user waits on, with realistic data
   size and concurrency, and report it as a share of the whole.
7. **Did it happen.** Confirm the work ran inside the timed region: the request arrived, rows were
   written, results were used. Lazy code, discarded results, and timeouts yield numbers for work
   that never happened. A number that looks too good or too bad is a reason to suspect what was
   measured.

For an evaluation result, ask the same of the trials: every run did the task, the gap holds across
trials and models, and the scenario matters.

## Report

- Lead with the verdict: faster, slower, no measurable difference, or inconclusive.
- Give the number with its unit, conditions, run count, median and range, bottleneck, errors and
  exclusions, and the command that reproduces it. Example: "p50 41 ms → 33 ms, median of 7 runs
  per side, range 32–35 ms after, bound by JSON parsing on one core, 0 errors, 0 exclusions."
- Call the verdict inconclusive when the bottleneck is unnamed, a side ran untuned, or errors and
  whether the work happened were not checked. Name the gap.
- Keep a PR body to one primary number; put runs, range, and bottleneck evidence in the PR notes or
  a linked file.
