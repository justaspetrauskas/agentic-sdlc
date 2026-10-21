---
name: sdlc-board
description: Open the metrics board for the current pipeline project (cost, turns, tokens, outcomes, daily cap)
---
Build and open the board for the repo in the current directory.

1. Check that `.sdlc/board/board.py` exists and `gh auth status` works. If the script is missing, tell the user to run
   `/sdlc-upgrade` first.
2. Run `python3 .sdlc/board/board.py --open`. It reads the run ledger from the `sdlc-metrics` branch and the repo's PRs
   with `gh`, writes one static HTML file to the temp folder and opens it.
3. Say the file path, and give three facts from the data: today's runs against the daily cap, the total cost, and how
   many task PRs passed CI and merged. Do not paste the data.

The board never leaves the machine. Do not deploy it anywhere; a Pages deploy would be public.
