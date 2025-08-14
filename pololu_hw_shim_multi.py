# pololu_hw_shim_multi.py
# Thread-local, multi-robot shim for: from pololu_3pi_2040_robot import robot
import time, threading, queue, sys

_thread_to_robot = {}        # thread ident -> robot_id
_robots = {}                 # robot_id -> RobotContext
_world = None                # SharedWorld

def _now(): return time.time()

class RobotContext:
    def __init__(self, robot_id, start=(0,0), heading=(0,-1)):
        self.robot_id = robot_id
        self.pos = list(start)         # [x, y]
        self.heading = list(heading)   # [dx, dy] (N/E/S/W)
        self.left_speed = 0
        self.right_speed = 0
        self.last_move_time = _now()
        self.visited = set([tuple(start)])
        self.path = [tuple(start)]
        self.revisits = 0
        self.lock = threading.Lock()
    def set_speeds(self, left, right):
        with self.lock:
            self.left_speed, self.right_speed = int(left), int(right)

class SharedWorld:
    def __init__(self, grid_size=10, step_seconds=2.0, kid=(5,5)):
        self.size = grid_size
        self.step_seconds = float(step_seconds)
        self.kid = tuple(kid)
        self.lock = threading.Lock()
    def _turn_left(self, v):
        dx,dy = v; return (-dy, dx)
    def _turn_right(self, v):
        dx,dy = v; return (dy, -dx)
    def _move_one(self, ctx: RobotContext, forward: int):
        dx,dy = ctx.heading
        nx, ny = ctx.pos[0] + forward*dx, ctx.pos[1] + forward*dy
        if 0 <= nx < self.size and 0 <= ny < self.size:
            cell = (nx, ny)
            if cell in ctx.visited: ctx.revisits += 1
            ctx.visited.add(cell)
            ctx.pos = [nx, ny]
            ctx.path.append(cell)
            return True
        return False
    def tick_all(self):
        moved = 0
        with self.lock:
            for rid, ctx in _robots.items():
                with ctx.lock:
                    if _now() - ctx.last_move_time < self.step_seconds:
                        continue
                    ctx.last_move_time = _now()
                    ls, rs = ctx.left_speed, ctx.right_speed
                    if (ls>0 and rs>0) or (ls<0 and rs<0):
                        moved += int(self._move_one(ctx, +1 if ls>0 else -1))
                    elif ls > rs:
                        ctx.heading = list(self._turn_left(tuple(ctx.heading)))
                    elif rs > ls:
                        ctx.heading = list(self._turn_right(tuple(ctx.heading)))
        return moved

# shim glue / helpers
def _shim_set_world(world: SharedWorld):
    global _world; _world = world
def _shim_register_robot(robot_id: str, ctx: RobotContext):
    _robots[robot_id] = ctx
def _shim_bind_thread(robot_id: str):
    _thread_to_robot[threading.get_ident()] = robot_id
def _shim_get_ctx_for_current_thread() -> RobotContext:
    rid = _thread_to_robot.get(threading.get_ident())
    if rid is None:
        raise RuntimeError("Shim not bound: call _shim_bind_thread(robot_id) in this thread.")
    return _robots[rid]
def _shim_world() -> SharedWorld:
    if _world is None: raise RuntimeError("World not set. Call _shim_set_world first.")
    return _world
def _shim_kid_found_robot() -> str|None:
    for rid, ctx in _robots.items():
        if tuple(ctx.pos) == _world.kid: return rid
    return None
def _shim_metrics(robot_id: str):
    ctx = _robots[robot_id]
    return {"path_len": max(0, len(ctx.path)-1), "revisits": ctx.revisits,
            "endx": ctx.pos[0], "endy": ctx.pos[1]}

# Fake Pololu API surface
class _Motors:
    def __init__(self): pass
    def set_speeds(self, left, right): _shim_get_ctx_for_current_thread().set_speeds(left, right)
    def stop(self): self.set_speeds(0,0)
class _LineSensors:
    def __init__(self): pass
    def read(self): return [1000,1000,1000,1000,1000]
    def read_calibrated_line(self): return 2000
class _BumpSensors:
    def __init__(self): pass
    def read(self):
        ctx = _shim_get_ctx_for_current_thread()
        hit = (tuple(ctx.pos) == _shim_world().kid)
        return {"left": hit, "right": hit}
class _Display:
    def __init__(self): pass
    def clear(self): pass
    def print(self, *args, **kwargs):
        msg = " ".join(str(a) for a in args)
        sys.stdout.write(f"[DISPLAY] {msg}\n")
    def text(self, s, x=0, y=0): sys.stdout.write(f"[DISPLAY] ({x},{y}) {s}\n")
    def show(self): pass
class _Button:
    def __init__(self): self._pressed=False
    def is_pressed(self): return self._pressed
    def wait_for_press(self): time.sleep(0.1)
class _RGBLEDs:
    def __init__(self): self._b=0
    def set_brightness(self, b): self._b=b
    def hsv2rgb(self, h,s,v): return (min(255,v), min(255,s), min(255,(h//60)%256))
    def set(self, idx, rgb): pass
    def show(self): pass
class _UART:
    def __init__(self):
        self.rx = queue.Queue(); self.tx = queue.Queue()
    def write(self, b: bytes):
        sys.stdout.write(f"[UART TX] {b!r}\n"); self.tx.put(bytes(b))
    def readline(self):
        try: return self.rx.get(timeout=0.01)
        except queue.Empty: return b""

class robot:
    Motors = _Motors
    LineSensors = _LineSensors
    BumpSensors = _BumpSensors
    Display = _Display
    ButtonA = _Button
    ButtonB = _Button
    ButtonC = _Button
    RGBLEDs = _RGBLEDs
    UART = _UART
