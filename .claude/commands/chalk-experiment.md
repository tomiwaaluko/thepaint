---
description: Exploratory experiment workflow — branch off railway, hypothesis, spike, evaluate, then decide to graduate/park/discard. Compound is mandatory. Loops back on failure.
argument-hint: "<hypothesis or idea>"   (optional)
---

# chalk-experiment

> Explore an idea to a decision — throwaway is allowed, but the **learning is always
> captured**.

Branch off `railway`, never `main`. Unlike the other workflows, this one may **stop
before shipping** — the deliverable is a decision, not necessarily merged code. The one
non-optional phase here is **compound**.

## MCP Integration
Prefer connected MCP servers (GitHub MCP + CodeRabbit always available).
- **Trackers:** link a spike ticket if one exists.
- **MLflow / experiment-tracking MCP (if connected):** log runs, params, and metrics so
  the experiment is reproducible.
- **Git hosting:** only open a PR if the experiment graduates.
Only use connected servers; else `git` + GitHub MCP.

## Resuming
- **Branch cut from `railway`?** → skip step 1.
- **Hypothesis + eval plan in `planning-spec.md`?** → resume at step 3 (spike).
- **Spike done, results recorded?** → resume at step 4 (evaluate + decide).

## Steps

1. **Create an experiment branch**
   - `git fetch origin railway` → `git switch --create experiment/<name> origin/railway`.
   - Scaffold `specs/experiment-<name>/`.

2. **Frame the hypothesis** (`chalk-brainstorm` skill)
   - Invoke `chalk-brainstorm`: the hypothesis, how you'll **evaluate** it (metric +
     threshold that means success/failure), and the time/scope box → `planning-spec.md`.
     Use walk-forward validation for any modeling claim; never k-fold.

3. **Spike it** (`chalk-work` skill, relaxed)
   - Sketch a minimal design in `design-spec.md`, then invoke `chalk-work` in
     exploratory mode: quick to build, but **still gate any feature code behind
     `as_of_date`** (a leaky experiment produces false results). Record results in
     `testing-spec.md` / MLflow.
   - **Loop-back:** the spike can't test the hypothesis as framed → **step 2** to
     reframe. **Loop cap 3** → stop and take the inconclusive result to step 4.

4. **Evaluate + decide**
   - Compare results to the threshold from step 2. Choose one:
     - **Graduate** → the idea works: switch to `chalk-feature` (open a proper
       `feature/` branch off `railway`, port the validated approach cleanly with review
       + ship). Do **not** ship the raw spike.
     - **Park** → promising but not now: leave the branch, document why.
     - **Discard** → it didn't work: that's a valid, valuable outcome.

5. **Compound (mandatory)** (`chalk-compound` skill)
   - Always invoke `chalk-compound`: write what the experiment tested, the result
     (including negative results), and guidance for the next loop, into
     `docs/solutions/`. An undocumented experiment is a wasted one.
