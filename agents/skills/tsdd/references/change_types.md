# Change-Type Evidence

Each change type states what evidence proves it. These are concrete cases of Red eligibility in
[TSDD](../SKILL.md#red-eligibility); the requirement source stays independent of the planned fix.

## Bug fix

A bug is a gap between required and actual behavior, so Red applies.

1. Reproduce it in the real environment, not only in a unit test. If it does not reproduce,
   synthesize the trigger or instrument until it does.
2. Narrow the cause by ruling out hypotheses with runtime evidence. A guard that "might help" is a
   hypothesis, not a fix; ship the smallest change the evidence justifies.
3. Write a failing automated reproduction test and watch it fail for the expected reason. Skip it
   only when an automated reproduction cannot be built at all; then record the manual reproduction
   steps and observed results in the PR. Commit structure follows
   [Stacked pull requests](../../git-workflow/references/stacked_prs.md).
4. Fix, then run the same reproduction: the original reproduction and the test now pass.
5. Put the failing output (before the fix) and the passing output (after) in the PR body, verbatim.

## Refactoring

Behavior stays; structure changes. There is no contract gap, so use the Green-baseline path.

1. Pin current behavior first with a characterization, snapshot, or golden test. Type checks and
   lint are not a pin. Without coverage, write the pin before moving structure.
2. Name the target shape: the layout, types, and call graph you would build today.
3. Move in small behavior-preserving steps, each keeping the pin green. Delete dead code before
   adding the new shape.
4. Migrate every caller, then delete the old API in the same change. Leave no compatibility shim or
   parallel old and new path. Check renames against strings, prose, and back-references.
5. Show behavior is unchanged on the real artifact, such as diffed old and new outputs or a replayed
   baseline. A bug or missing feature found on the way is split out, not folded in.

## Performance

1. Capture a baseline and vet it with `measurement-evidence`.
2. Plan the fix from the profile and bottleneck, not from reading the source.
3. Apply the fix.
4. Re-measure under the same conditions and vet the result with `measurement-evidence`.
5. Put before and after numbers, with conditions, in the PR.
