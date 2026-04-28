# Beal Conjecture Search: GitHub Actions Edition
# Auto-persists via git commits. Runs 6 hours daily.
# Improved sieve + corrected coprime check.

import math
import json
import os
import time
import signal
import sys
import subprocess

try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass

# ================= CONFIGURATION =================
STATE_PATH    = "beal_state.json"
RESULTS_PATH  = "beal_results.jsonl"

START_BASE = 1000
MAX_BASE   = 2_000_000
MAX_EXP    = 12
MAX_SUM    = 10**30
MAX_RUNTIME_HOURS = 5.8   # 5.8 hours to leave time for git commit
TIME_CHECK_INTERVAL = 100_000
SAVE_INTERVAL_SEC = 180
# =================================================

# 🟦 1. LOAD STATE FROM GIT-TRACKED FILE
state = {
    "A": START_BASE, "B": START_BASE, "x": 3, "y": 3,
    "checked": 0, "found": 0, "last_S": 0,
    "start_time": time.time()
}

if os.path.exists(STATE_PATH):
    with open(STATE_PATH, "r") as f:
        loaded = json.load(f)
        state.update(loaded)
        state["checked"] = loaded.get("checked", 0)
        state["found"] = loaded.get("found", 0)
        state["counterexamples"] = loaded.get("counterexamples", [])
        state["start_time"] = time.time()

state.setdefault("counterexamples", [])
state["current_run_id"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(state["start_time"]))

# 🟦 2. GLOBAL PRECOMPUTATIONS
MODULI = (16, 9, 25, 27, 7, 5, 13, 17, 19, 11, 31)
EXP_RANGE = range(3, MAX_EXP + 1)
EXP_LEN = len(EXP_RANGE)
pp_res_sets = [{pow(c, z, m) for c in range(m) for z in EXP_RANGE} for m in MODULI]
MODULI_COUNT = len(MODULI)

# 🟦 3. SAVE HELPERS
def save_state():
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)

def save_discovery_jsonl(A, x, B, y, C, z, S, run_id):
    discovery = {
        "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "run_id": run_id,
        "equation": f"{A}^{x} + {B}^{y} = {C}^{z}",
        "values": {"A": A, "x": x, "B": B, "y": y, "C": C, "z": z},
        "sum_S": S, "gcd_ABC": 1,
        "config": {"MAX_BASE": MAX_BASE, "MAX_EXP": MAX_EXP}
    }
    with open(RESULTS_PATH, "a") as f:
        f.write(json.dumps(discovery) + "\n")

# 🟦 4. GRACEFUL SHUTDOWN
MAX_RUNTIME_SEC = MAX_RUNTIME_HOURS * 3600
runtime_expired = False
def handle_timeout():
    global runtime_expired
    runtime_expired = True

def handle_sigterm(signum, frame):
    save_state()
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
save_state()

# 🟦 5. MAIN SEARCH LOOP
curr_A, curr_B, curr_x, curr_y = state["A"], state["B"], state["x"], state["y"]
last_save_time = time.time()
checks_since_check = 0

try:
    for A in range(curr_A, MAX_BASE + 1):
        A_powers = [A ** x for x in EXP_RANGE]
        A_mods = [[pow(A, x, m) for x in EXP_RANGE] for m in MODULI]

        b_start = curr_B if A == curr_A else A
        for B in range(b_start, MAX_BASE + 1):
            if math.gcd(A, B) > 1: continue

            B_powers = [B ** y for y in EXP_RANGE]
            B_mods = [[pow(B, y, m) for y in EXP_RANGE] for m in MODULI]

            for xi in range(EXP_LEN):
                val_A = A_powers[xi]
                if val_A > MAX_SUM: break

                for yi in range(EXP_LEN):
                    skip = False
                    for mi in range(MODULI_COUNT):
                        if (A_mods[mi][xi] + B_mods[mi][yi]) % MODULI[mi] not in pp_res_sets[mi]:
                            skip = True
                            break
                    if skip: continue

                    S = val_A + B_powers[yi]
                    if S > MAX_SUM: break

                    found_C, found_z = None, None
                    for z in range(3, MAX_EXP + 1):
                        c = int(S ** (1.0 / z))
                        p = c ** z
                        if p == S:
                            found_C, found_z = c, z
                            break
                        if p < S:
                            c += 1
                            if c ** z == S:
                                found_C, found_z = c, z
                                break
                        if c < 2: break

                    if found_C is not None:
                        if math.gcd(A, found_C) == 1 and math.gcd(B, found_C) == 1:
                            state["found"] += 1
                            run_id = state["current_run_id"]
                            state["counterexamples"].append({
                                "A": A, "x": xi+3, "B": B, "y": yi+3,
                                "C": found_C, "z": found_z, "sum_S": S,
                                "run_id": run_id, "timestamp": time.time()
                            })
                            save_discovery_jsonl(A, xi+3, B, yi+3, found_C, found_z, S, run_id)
                            save_state()

                    state.update({
                        "A": A, "B": B, "x": xi+3, "y": yi+3,
                        "checked": state["checked"] + 1, "last_S": S
                    })
                    checks_since_check += 1

                    if checks_since_check >= TIME_CHECK_INTERVAL:
                        elapsed = time.time() - state["start_time"]
                        if elapsed > MAX_RUNTIME_SEC:
                            handle_timeout()
                        if time.time() - last_save_time > SAVE_INTERVAL_SEC or runtime_expired:
                            save_state()
                            last_save_time = time.time()
                        if runtime_expired:
                            raise KeyboardInterrupt
                        checks_since_check = 0

except KeyboardInterrupt:
    pass
finally:
    save_state()
    elapsed = time.time() - state["start_time"]
    cps = state["checked"] / elapsed if elapsed > 0 else 0
    print(f"\n🏁 SESSION COMPLETE")
    print(f"🔹 LAST CHECKED: A={state['A']}, B={state['B']}, x={state['x']}, y={state['y']}")
    print(f"📊 Total checked: {state['checked']:,} | Avg: {cps:,.0f} checks/sec")
    print(f"⏱️  Runtime: {elapsed/3600:.2f} hours")
    print(f"🛡️  COUNTEREXAMPLES FOUND: {state.get('found', 0)}")
    print("💾 State auto-committed to repo. Next run resumes exactly here.")
