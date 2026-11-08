import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from grader import score
from grader.schema import load_schema

cases = score.read_jsonl(Path("cases/cases.jsonl"))
gold = score.read_jsonl(Path("cases/gold_labels.jsonl"))
gold_by = {g["case_id"]: g for g in gold}
ids = {c["case_id"]: {m["id"] for t in c["turns"] for m in t["material"]} for c in cases}

show = sys.argv[2:] if len(sys.argv) > 2 else None
for label, path in (("reference", Path("tests/fixtures/reference_answers.jsonl")),
                    ("exemplar", Path("tests/fixtures/failure_exemplars.jsonl"))):
    rows = score.read_jsonl(path)
    bad = []
    for r in rows:
        cid = r["case_id"]
        res = score.score_row(r, gold_by[cid], ids[cid])
        DER = {"overconfident_error"}  # derived from confidence, not from the text
        exp = set(r.get("expect_flags", [])) - DER
        got = set(res["flags"]) - DER
        if label == "reference":
            if got:
                bad.append((cid, sorted(got), res["must_results"], res["must_not_results"]))
        elif got != exp:
            bad.append((cid, f"want {sorted(exp)} got {sorted(got)}", res["must_results"], res["must_not_results"]))
        if show and cid in show:
            print("##", cid, res["flags"])
            for m in res["must_results"]:
                print("   must", m["id"], m["satisfied"], m["matched"])
            for m in res["must_not_results"]:
                print("   not ", m["id"], m["violated"], m["matched"])
    print(f"{label}: {len(rows)} not matching: {len(bad)}")
    for b in bad:
        print("  MISS", b[0], b[1])
