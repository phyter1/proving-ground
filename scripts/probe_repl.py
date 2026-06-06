"""Probe lean-interact's API and the real REPL response shapes. Run on ren4.

Throwaway diagnostic — prints what the REPL actually returns so the checker leaves can be
written against reality, not guesses.
"""

import json

import lean_interact as li

print("=== lean_interact public names ===")
print([n for n in dir(li) if not n.startswith("_")])

# Find the project class for an existing local mathlib project.
from lean_interact import Command, LeanREPLConfig, LeanServer  # noqa: E402

proj_cls = None
for name in ("LocalProject", "LocalConfig", "Project"):
    if hasattr(li, name):
        proj_cls = getattr(li, name)
        print(f"\n=== using project class: {name} ===")
        break

PROJECT_DIR = "/models/proving-ground-lean"

try:
    if proj_cls is not None:
        config = LeanREPLConfig(project=proj_cls(directory=PROJECT_DIR))
    else:
        config = LeanREPLConfig()
except Exception as e:  # noqa: BLE001
    print("config attempt 1 failed:", e)
    # try positional
    config = LeanREPLConfig(project=proj_cls(PROJECT_DIR)) if proj_cls else LeanREPLConfig()

server = LeanServer(config)


def show(label, resp):
    print(f"\n=== {label} ===")
    print("type:", type(resp).__name__)
    # Try common shapes
    for attr in ("messages", "sorries", "env", "lean_code"):
        if hasattr(resp, attr):
            print(f"  .{attr}:", getattr(resp, attr))
    d = getattr(resp, "model_dump", None)
    if d:
        try:
            print("  dump:", json.dumps(d(), default=str)[:800])
        except Exception as e:  # noqa: BLE001
            print("  dump err:", e)


# 1. import Mathlib (establish env)
r0 = server.run(Command(cmd="import Mathlib"))
show("import Mathlib", r0)
env = getattr(r0, "env", None)

# 2. clean theorem
r1 = server.run(Command(cmd="theorem t_clean (n : Nat) : n + 0 = n := by simp", env=env))
show("clean theorem", r1)

# 3. theorem with sorry
r2 = server.run(Command(cmd="theorem t_sorry (n : Nat) : 0 + n = n := by sorry", env=env))
show("sorry theorem", r2)

# 4. #print axioms on the clean one
r3 = server.run(Command(cmd="#print axioms t_clean", env=getattr(r1, "env", env)))
show("print axioms clean", r3)

# 5. #print axioms on the sorry one
r4 = server.run(Command(cmd="#print axioms t_sorry", env=getattr(r2, "env", env)))
show("print axioms sorry", r4)

# 6. an outright error
r5 = server.run(Command(cmd="theorem t_err : Nat := by simp", env=env))
show("error theorem", r5)

print("\n=== DONE ===")
