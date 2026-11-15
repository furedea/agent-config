# ADR-0024: Merge the issue, Git, and setup workflows into one development-cycle skill

- Status: Accepted
- Date: 2026-11-15

In the context of #169 item D, where `issue-workflow`, `git-workflow`, and `project-setup` each described one stage of
the same development cycle and handed off to each other by prose, facing a choice between keeping them separate,
merging them into one skill, and merging `tsdd` in as well, we decided for merging the three into one skill
`development-cycle` whose `SKILL.md` is the map (the stages in order, a routing table, and the authorization rules
stated once) and whose references hold the former content (`start.md`, `repository_setup.md`, `dev_environment.md`,
`issue_plan.md`, `branches.md`, `commits.md`, `delivery.md`, `stacked_prs.md`), for keeping `tsdd` and
`herdr-delegation` as separate skills, and against keeping all skills separate and against merging `tsdd` too, to
achieve one trigger for the whole cycle (a request such as "start a new project" enters the cycle at its start stage
without the user naming a skill), one statement of what each kind of request authorizes, and no handoff prose between
stages, accepting that the description of `development-cycle` is broad, that its content is thinned only by the later
phases of #169, and that references load only when the routing table sends the agent to them.

`tsdd` stays separate because its content is permanent judgement that #181 keeps at the skill tier, because it is used
outside the cycle (test design, lanes, the style skills, local work without GitHub), and because it couples to the
cycle only at "verify before delivery". The issue and Git parts are interim and shrink as #181 lands; mixing the two
lifetimes in one skill would blur which part to remove. `herdr-delegation` stays separate because it triggers only
when Herdr is used.

Rejected alternatives:

- Keep all skills separate: the authorization rules and the handoffs are stated in several skills, and a request that
    spans stages loads only some of them.
- Merge `tsdd` too: it mixes a permanent methodology with interim delivery procedures, and it serves requests that
    are not a cycle.

The content moved without a change of rules; only the duplicated authorization statements were merged, and the
language-to-template table of `project-setup` was replaced by the `--lang` option of `repo create` (ADR-0023).
