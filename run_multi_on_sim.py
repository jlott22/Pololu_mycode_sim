# run_multi_on_sim.py
# Multi-robot, batch-capable runner that executes your actual Pololu script.
import argparse, os, sys, json, random, subprocess, time
from pathlib import Path

def default_starts(n, size):
    starts = [((0,0),(0,-1)), ((size-1,size-1),(0,1)), ((size-1,0),(-1,0)), ((0,size-1),(1,0))]
    if n <= 4: return starts[:n]
    extra = []
    for x in range(1, size-1): extra.append(((x,0),(0,1)))
    for y in range(1, size-1): extra.append(((size-1,y),(-1,0)))
    for x in range(size-2, 0, -1): extra.append(((x,size-1),(0,-1)))
    for y in range(size-2, 0, -1): extra.append(((0,y),(1,0)))
    return starts + extra[:n-4]

def run_master(args):
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    episode_rows = []; found_count = 0
    for ep in range(args.episodes):
        kid = args.kid if args.kid else (rng.randrange(args.grid), rng.randrange(args.grid))
        res_path = out / f"ep_{ep:05d}.json"
        cmd = [sys.executable, __file__, "--mode","worker","--script",args.script,
               "--n",str(args.n),"--grid",str(args.grid),
               "--step_seconds",str(args.step_seconds),
               "--kid", f"{kid[0]},{kid[1]}","--result", str(res_path)]
        if args.seed is not None: cmd += ["--seed", str(rng.randrange(10**9))]
        subprocess.run(cmd, check=True)
        with open(res_path) as f: r = json.load(f)
        found_count += int(bool(r["found"]))
        row = [ep, int(bool(r["found"])), r.get("found_by",""), r["steps"], r["sim_seconds"],
               kid[0], kid[1], args.n, args.grid]
        for rid in r["robots"]:
            st = r["robots"][rid]; row += [st["path_len"], st["revisits"], st["endx"], st["endy"]]
        episode_rows.append(row)

    header = ["ep","found","found_by","steps","sim_seconds","kid_x","kid_y","n","grid"]
    for i in range(args.n): header += [f"path_{i:02d}", f"revisits_{i:02d}", f"endx_{i:02d}", f"endy_{i:02d}"]
    import csv
    with open(out/"episodes.csv","w",newline="") as f:
        w=csv.writer(f); w.writerow(header); w.writerows(episode_rows)
    summary = {"episodes": args.episodes, "found_rate": found_count/max(1,args.episodes),
               "avg_steps": sum(r[3] for r in episode_rows)/max(1,len(episode_rows)),
               "n": args.n, "grid": args.grid}
    with open(out/"summary.json","w") as f: json.dump(summary,f,indent=2)
    print("Wrote:", out/"episodes.csv"); print("Wrote:", out/"summary.json")

def run_worker(args):
    import importlib.util, threading, time as _t
    import pololu_hw_shim_multi as shim
    sys.modules["pololu_3pi_2040_robot"] = shim
    world = shim.SharedWorld(grid_size=args.grid, step_seconds=args.step_seconds, kid=args.kid)
    shim._shim_set_world(world)
    starts = default_starts(args.n, args.grid)
    robots = {}
    for i in range(args.n):
        rid=f"{i:02d}"; start,head=starts[i]
        ctx=shim.RobotContext(rid,start=start,heading=head)
        shim._shim_register_robot(rid, ctx); robots[rid]=ctx
    def launch(rid, script_path):
        shim._shim_bind_thread(rid)
        spec=importlib.util.spec_from_file_location(f"user_pololu_script_{rid}",script_path)
        mod=importlib.util.module_from_spec(spec); sys.modules[f"user_pololu_script_{rid}"]=mod
        try: spec.loader.exec_module(mod)
        except Exception as e: sys.stderr.write(f"[Worker] Robot {rid} script error: {e}\n")
    threads = []
    for i in range(args.n):
        rid=f"{i:02d}"; t=threading.Thread(target=launch,args=(rid,args.script),daemon=True); t.start(); threads.append(t)
    steps=0; max_steps=args.grid*args.grid*5; start_t=time.time(); found_by=None
    while steps<max_steps:
        moved=world.tick_all()
        if moved>0: steps+=moved
        rid=shim._shim_kid_found_robot()
        if rid is not None: found_by=rid; break
        _t.sleep(0.02)
    sim_seconds=round(time.time()-start_t,3)
    res={"found":bool(found_by),"found_by":found_by or "","steps":steps,"sim_seconds":sim_seconds,"robots":{}}
    for rid in robots: res["robots"][rid]=shim._shim_metrics(rid)
    with open(args.result,"w") as f: json.dump(res,f)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",choices=["master","worker"],default="master")
    ap.add_argument("--script",required=True)
    ap.add_argument("--n",type=int,default=2)
    ap.add_argument("--grid",type=int,default=10)
    ap.add_argument("--episodes",type=int,default=100)
    ap.add_argument("--seed",type=int,default=42)
    ap.add_argument("--out",type=str,default="multi_out")
    ap.add_argument("--kid",type=lambda s: tuple(int(x) for x in s.split(",")),default=None)
    ap.add_argument("--step_seconds",type=float,default=2.0)
    ap.add_argument("--result",type=str)
    args=ap.parse_args()
    if args.mode=="master": run_master(args)
    else:
        if not args.result: raise SystemExit("--result required in worker mode")
        run_worker(args)
if __name__=="__main__": main()
