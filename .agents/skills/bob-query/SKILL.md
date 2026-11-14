---
name: bob-query
description: >-
  Answer a question from the Bob wiki when the user invokes /query or asks for
  retrieval and synthesis grounded in existing wiki pages.
---

# Bob Query

Read [`../../../.bob/commands/query.md`](../../../.bob/commands/query.md) completely and follow it together with the repository `AGENTS.md`.

Run `python tools/bob_runner.py query --question "<question>"` to retrieve candidates, then read the underlying wiki pages and synthesize the answer with precise citations. Runner output is not itself an answer.

Preserve the result as an analysis page only when the documented preservation criteria apply. If preservation is appropriate but not explicitly requested, ask for direction before writing. Update the index and log only when an analysis is preserved.

If the runner exhibits a genuine defect, stop and follow `AGENTS.md` section 12 before reading or changing the runner.
