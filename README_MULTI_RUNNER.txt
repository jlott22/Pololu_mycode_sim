Multi-Robot Batch Runner — Executes Your Actual Pololu Script
============================================================

What this is
------------
A multi-robot orchestrator that runs your real `pololu-astar.py` on a shared grid using a thread-local fake hardware module.
It supports N robots, batch episodes, and produces CSV/JSON stats.

Files
-----
- pololu_hw_shim_multi.py — multi-robot fake `pololu_3pi_2040_robot`
- run_multi_on_sim.py — master/worker batch runner (one worker process per episode)

Run (example, 2 robots, 10×10 grid, 10 episodes)
-------------------------------------------------
python run_multi_on_sim.py --script "/path/to/pololu-astar.py" \
  --n 2 --grid 10 --episodes 10 --seed 123 --out multi_out --step_seconds 2.0

Outputs
-------
- multi_out/episodes.csv — per-episode metrics (found/steps/kid + per-robot path length, revisits, end positions)
- multi_out/summary.json — aggregate stats (found rate, avg steps, etc.)

Defaults
--------
- Starts/headings: 00 at (0,0) North; 01 at (grid-1,grid-1) South; 3rd/4th fill corners; 5+ along perimeter.
- Movement: both>0 → forward 1 cell per step_seconds; both<0 → backward; left>right → left turn 90°; right>left → right turn 90°.
- "Found": a robot stands on the kid cell (BumpSensors.read() true).
