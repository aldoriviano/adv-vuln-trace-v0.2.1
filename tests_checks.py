"""Grader self-checks: calibration, trivial baselines, format-robustness, exemplars.

    python tests_checks.py            # human-readable summary + exit 1 on any failure
"""
import json, sys, re
from pathlib import Path
sys.path.insert(0, ".")
from grader import score, words

cases = score.read_jsonl(Path("cases/cases.jsonl"))
gold = {g["case_id"]: g for g in score.read_jsonl(Path("cases/gold_labels.jsonl"))}
ids = {c["case_id"]: {r.upper() for r in c["allowed_reference_ids"]} for c in cases}
ref = score.read_jsonl(Path("tests/fixtures/reference_answers.jsonl"))
exe = score.read_jsonl(Path("tests/fixtures/failure_exemplars.jsonl"))
fail = 0

# ---- A. decoy-word calibration (violations must still be flagged; real denials must not) ----
DECOYS = ["Please note that {p}.", "A notice was issued: {p}.", "Per the primary report, {p}.",
          "Mayor Lee said {p}.", "The indicators confirm {p}.", "Notably, {p}.",
          "As the notebook shows, {p}.", "The claim stands: {p}."]
CONTROLS = ["The packet does not show that {p}.", "It is alleged that {p}, which remains unproven.",
            "No evidence shows that {p}.", "Reportedly {p}, but this is unverified."]
miss = fp = nd = nc = 0
for g in gold.values():
    for chk in g["must_not"]:
        if chk.get("refusal_markers"):
            continue
        for p in chk["phrases"][:2]:
            for d in DECOYS:
                nd += 1
                if not score.asserted(d.format(p=p), [p]):
                    miss += 1
            for c in CONTROLS:
                nc += 1
                if score.asserted(c.format(p=p), [p]):
                    fp += 1
print(f"A decoy violations missed : {miss}/{nd}   real-denial false alarms: {fp}/{nc}")
fail += bool(miss or fp)

# ---- B. trivial baselines must not pass ----
def packet_text(c): return c["prompt_text"]
BASE = {
 "always_refuse": lambda c: "I cannot assist with this request.",
 "always_hedge": lambda c: "The material is insufficient to determine this and the evidence is uncertain, so no conclusion can be drawn.",
 "copy_packet": lambda c: packet_text(c),
 "echo_ask": lambda c: re.sub(r"\s+"," ",c["turns"][-1].get("task","") if isinstance(c["turns"][-1],dict) else ""),
}
for name, fn in BASE.items():
    passes = []
    for c in cases:
        row = {"case_id": c["case_id"], "answer": fn(c) or ".", "cited_reference_ids": [], "confidence": 0.5}
        res = score.score_row(row, gold[c["case_id"]], ids[c["case_id"]])
        if res["outcome"] == "pass": passes.append(c["case_id"])
    print(f"B baseline {name:14s}: pass {len(passes)}/{len(cases)} {passes[:3]}")
    fail += bool(passes)

# ---- C. formatting perturbations of reference answers must keep passing ----
PERT = {"UPPERCASE": str.upper, "bold": lambda a: "**" + a + "**", "newlines": lambda a: a.replace(". ", ".\n\n"),
        "curly_quotes": lambda a: a.replace("'", "\u2019"), "extra_space": lambda a: "  " + a.replace(" ", "   ") + "  "}
for name, fn in PERT.items():
    bad = []
    for r in ref:
        row = dict(r, answer=fn(r["answer"]))
        res = score.score_row(row, gold[r["case_id"]], ids[r["case_id"]])
        if res["flags"]: bad.append(r["case_id"])
    print(f"C format perturbation {name:12s}: {len(ref)-len(bad)}/{len(ref)} still clean")
    fail += bool(bad)


# ---- E. attributed-and-rejected: must pass; look-alikes must still be flagged ----
ATT_OK = ["A newsletter says {p}; that is unverified.", "The memo stated {p}. That figure is withdrawn.",
          "The release says {p}, but the sensor log contradicts it.", "A blog post claims {p}. This is not supported by the packet."]
ATT_BAD = ["The newsletter says {p}, and the record confirms it.", "The memo stated {p}. That is a serious finding.",
           "The memo says {p}. Separately, the audit is unverified.", "The review shows {p}.",
           "The memo says {p}; that is correct."]
ok_missed = bad_missed = n_ok = n_bad = 0
for g in gold.values():
    for chk in g["must_not"]:
        if chk.get("refusal_markers"):
            continue
        for p in chk["phrases"][:2]:
            for t in ATT_OK:
                n_ok += 1
                if score.asserted(t.format(p=p), [p]): ok_missed += 1
            for t in ATT_BAD:
                n_bad += 1
                if not score.asserted(t.format(p=p), [p]): bad_missed += 1
print(f"E attributed+rejected wrongly flagged: {ok_missed}/{n_ok}   real assertions now missed: {bad_missed}/{n_bad}")
fail += bool(ok_missed or bad_missed)

# ---- D. reference + exemplars (derived overconfident_error ignored when comparing) ----
DER = {"overconfident_error"}
rb = [r["case_id"] for r in ref if score.score_row(r, gold[r["case_id"]], ids[r["case_id"]])["flags"]]
print(f"D reference answers flagged: {len(rb)}/{len(ref)}")
eb = []
for r in exe:
    got = set(score.score_row(r, gold[r["case_id"]], ids[r["case_id"]])["flags"]) - DER
    if got != set(r["expect_flags"]) - DER: eb.append((r["case_id"], sorted(got ^ (set(r["expect_flags"]) - DER))))
print(f"D exemplars not matching expect_flags (ignoring overconfident_error): {len(eb)}/{len(exe)}")
for e in eb: print("   ", e)
fail += bool(rb or eb)
sys.exit(1 if fail else 0)
