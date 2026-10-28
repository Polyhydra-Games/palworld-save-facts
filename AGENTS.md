# AGENTS.md

## Purpose

This file is the repo-local guide for coding agents working in this repository. Preserve repository-specific instructions below this section.


## Global DevOps GitHub–Kanban Contract

For DevOps, infrastructure, deployment, security, GitOps, and service work:

1. GitHub is authoritative for Issues, PRs, CI, reviews, merges, releases, and delivery state, and is the execution queue.
2. One GitHub Issue should normally produce one PR directly to `main`.
3. Before branch work or a PR, fetch `origin/main` and reconcile against the current remote default branch. Do not build branch-on-branch PR stacks unless an explicit integration owner and final target are stated.
4. Do not merge, deploy, close issues, rotate secrets, or claim production success unless the task explicitly authorizes it and verification evidence exists.
5. If branches diverge, stop merging the stack. Create one integration branch from current `origin/main`, resolve semantic conflicts deliberately, run tests, and open one replacement PR to `main`.
6. For security or infrastructure work, provide exact build, test, and diff evidence and require fresh independent review before merge. Never put secrets in code, logs, PRs, or comments.
7. A task is not complete because a local test passes or a Kanban card says done. Completion requires the requested GitHub state and, when applicable, verified live behavior.
8. When creating a PR, state its target branch, linked issue, validation output, and whether it supersedes prior PRs. Do not leave divergent worker PRs ambiguous.

<!-- dev-forge:low-interruption:start version=5 -->
## Low-Interruption Execution

- Treat explicit outcome requests such as "fix," "build," "complete," and
  "finish" as continuing authorization for bounded work toward that outcome.
- Continue through diagnosis, implementation, tests, commits, pushes, review
  feedback, and CI repair without renewed confirmation.
- New defects discovered within the same task or pull request remain in scope
  only when they are P0/P1 or release-blocking, or while the accepted outcome
  is not yet complete. After acceptance criteria pass, P2-and-lower
  non-blocking findings become linked follow-ups unless the owner explicitly
  keeps them in the active slice.
- Progress updates are informational and do not pause execution.
- Do not request confirmation when the only realistic alternatives are the
  clearly supported action and inaction.
- Use MAID (Multiple-Choice Agentic Interface Development) only for a real
  operator fork. Lead with the recommended option, label it, make choices
  mutually exclusive, and describe what each choice causes.
- Use the current host's native picker when it is available in the current
  mode. Never invoke a picker that the current host or mode does not expose.
  A missing picker is not a blocker: at a genuine impasse, present two or three
  concise, lettered **A**/**B**/**C** choices instead and request the letter.
- Scale a checkpoint to what it costs the operator, not to how important the
  decision feels. A native picker is cheap enough for any real fork; a typed
  fallback remains reserved for a genuine impasse. Neither is a reason to ask
  for reassurance, re-ask a settled decision, or ask what the repository can
  answer.
- Do not offer a picker whose options are an action and its absence. Do not use
  "Done — continue" as a generic permission gate.
- A picker selects a path; it never authorizes merge, deploy, destructive work,
  secret or access changes, material cost, external communication, or credible
  downtime or data-loss risk. Use the applicable approval control for those
  protected actions.
- End every handback with selectable, genuine next steps when a real next-step
  fork remains. Use the native picker when available; otherwise use lettered
  choices. If no second genuine option exists, state the actual status plainly
  and stop rather than inventing a placeholder choice.
- This governs the form of a handback, not the frequency of checkpoints. Do not
  interrupt bounded work more often because of it. Do not add selectable
  options to a machine-readable output constrained by an external schema.
<!-- dev-forge:low-interruption:end -->
