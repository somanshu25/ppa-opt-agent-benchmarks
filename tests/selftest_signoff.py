"""Sign-off mechanism self-test.

Runs sign-off STA with golden == the SDC the flow actually used.  If the
sign-off path is wired correctly (right liberty, right ODB, parasitics read,
constraints not double-applied) it must reproduce the flow's own finish__*
timing numbers exactly.  Any mismatch means the gate is measuring something
other than what the flow measured, and every downstream verdict is suspect.
"""

import json
import sys

signoff_json, finish_json = sys.argv[1], sys.argv[2]

s = json.load(open(signoff_json))
f = json.load(open(finish_json))

PAIRS = [
    ("timing__setup__ws", "setup WS"),
    ("timing__setup__tns", "setup TNS"),
    ("timing__hold__ws", "hold WS"),
    ("timing__hold__tns", "hold TNS"),
    ("clock__skew__setup", "clock skew"),
    ("timing__fmax", "fmax"),
]

print("{:12} {:>18} {:>18}   match".format("metric", "finish", "signoff"))
print("-" * 62)
ok = True
for key, label in PAIRS:
    a = f.get("finish__" + key)
    b = s.get("signoff__" + key)
    match = a == b
    ok = ok and match
    print("{:12} {:>18} {:>18}   {}".format(label, str(a), str(b), match))

print()
print("SELF-TEST", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
