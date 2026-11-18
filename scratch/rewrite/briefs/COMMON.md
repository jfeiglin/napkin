# Rules for every prototype of Phase A

You are one of several agents that work in parallel on prototypes for a rewrite of the napkin
language. Read this file, then your own brief, then `scratch/rewrite/spec.md` (the specification:
long, and all of it matters), then the parts of `scratch/rewrite/PLAN.md` that your brief names.

## What napkin is

A typed scenario language, its compiler (`napkin/model/`) and an engine (`napkin/engine/`). The
rewrite replaces the language in place. The spec says what the new language is. It also lists many
details as open. The prototypes exist to close them: each open item gets a rule with an example, or
"not in the first version" with the message that a model gets.

## Where you work

- The checkout is `/home/user/napkin`. Write only inside your own folder, which your brief names
  (`scratch/rewrite/aN/`), and in a temporary folder of your own under
  `/tmp/claude-0/-home-user-napkin/e09158c7-7039-5d6d-be85-61b3a193adaf/scratchpad/`.
- Edit nothing else in the checkout. Run no git command that changes the repository: no commit, no
  checkout, no stash, no reset. The main session commits your folder.
- Do not run the repository's test suite. Tests of your own prototype are fine.
- Python is `/home/user/napkin/.venv/bin/python` (numpy 2.5, scipy 1.18.1 with HiGHS 1.12, pytest,
  hypothesis, mpmath). Add no dependency.
- The package in the checkout changes while you work. When you import `napkin`, import the stable
  copy at the base commit: `PYTHONPATH=/home/user/napkin-base`. Read source files there too. Line
  numbers in the briefs are those of that copy.
- The machine has 4 cores and other agents use them. For a timing, give the best of three runs and
  the load (`uptime`). Leave one script that makes your whole table again; the main session runs
  it alone later.

## What you deliver

A file `FINDINGS.md` in your folder, in plain English with short sentences:

1. **Summary**: ten lines at most.
2. **What was done**: the scripts, and how to run each.
3. **Results**: tables and numbers. Each claim has a run or a reference (`file:line`) behind it.
   Say plainly what you did not verify.
4. **Rulings**: one for each open item that your brief gives you, and for each one that you find.
   Use this form exactly:

   ```
   ### R-A1-01: <title>  [owner | technical]
   Rule: <the rule that you propose>
   Alternative: <the best other rule>
   Example: <ten lines at most, and what the rule and the alternative each give for it>
   Recommendation: <one or two sentences>
   ```

   Tag a ruling `owner` when it changes what a model author writes or sees. Tag it `technical`
   when it does not.
5. **Not covered**: what you left out, and why.

Keep the examples generic: tanks, pumps, places, routes, crews. Name no real scenario of the
catalogue in a rule.

Your last message to the main session: 300 words at most. What is done, the five findings that
matter most, what is not done, and the list of your files. The main session reads `FINDINGS.md` for
the rest.
