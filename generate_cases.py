"""Compile attacker/spec_v1.py into the case, gold and index artefacts.

This is the case-construction half of the instrument. It is a compiler, not a
model: the same spec always produces byte-identical output, so a run can be
re-derived from the pinned spec hash and no case can enter the set by accident.
Validation failure aborts the whole write.

    python attacker/generate_cases.py            # write cases/, print summary
    python attacker/generate_cases.py --check    # validate only, exit 1 on issues
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec_v1  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "cases"

EXPECTED_TOTAL = 33
EXPECTED_CLASS_COUNTS = {
    "OVERREACH": 2, "FABRICATED_EVIDENCE": 2, "PREMISE_HIJACK": 2,
    "SPOOFED_AUTHORITY": 2, "FALSE_PREMISE": 2, "PRESSURE_REVERSAL": 2,
    "OVER_REFUSAL": 3, "UNDER_REFUSAL": 2, "NUMERIC_INTEGRITY": 2,
    "ANCHORING": 2, "BURIED_CONSTRAINT": 2, "FORMAT_COERCION": 2,
    "RETRACTION": 2, "SILENT_DROP": 2, "DECISIVENESS_PRESSURE": 2,
    "SOURCE_HIERARCHY": 2,
}
NAME_PREFIXES = {
    "OVERREACH": "OVERREACH", "FABRICATED_EVIDENCE": "FABRICATED",
    "PREMISE_HIJACK": "HIJACK", "SPOOFED_AUTHORITY": "SPOOFED",
    "FALSE_PREMISE": "PREMISE", "PRESSURE_REVERSAL": "PRESSURE",
    "OVER_REFUSAL": "REFUSE", "UNDER_REFUSAL": "COMPLY",
    "NUMERIC_INTEGRITY": "NUMERIC", "ANCHORING": "ANCHOR",
    "BURIED_CONSTRAINT": "BURIED", "FORMAT_COERCION": "FORMAT",
    "RETRACTION": "RETRACT", "SILENT_DROP": "DROP",
    "DECISIVENESS_PRESSURE": "DECIDE", "SOURCE_HIERARCHY": "SOURCE",
}
CASE_KEYS = {"name", "cls", "technique", "domain", "difficulty", "refusal_expected",
             "mutation_safe", "turns", "must", "must_not", "failure_labels",
             "justification"}
OPTIONAL_CASE_KEYS = {"phantom_refs", "required_items", "buried_checks", "max_words"}
TURN_KEYS = {"key", "material", "ask"}
CHECK_KEYS = {"id", "intent", "phrases", "refusal_markers"}
ID_RE = re.compile(r"^R\d+$")
CHECK_ID_RE = re.compile(r"^[MN]\d+$")


def _check_ids(checks, where, issues):
    seen = []
    for chk in checks if isinstance(checks, list) else []:
        if not isinstance(chk, dict):
            issues.append(f"{where}: each check must be an object")
            continue
        extra = sorted(set(chk) - CHECK_KEYS)
        if extra:
            issues.append(f"{where}: unexpected check key(s) {extra}")
        cid = chk.get("id")
        if not isinstance(cid, str) or not CHECK_ID_RE.match(cid):
            issues.append(f"{where}: check id {cid!r} is not M<n> or N<n>")
        elif cid in seen:
            issues.append(f"{where}: duplicate check id {cid}")
        else:
            seen.append(cid)
        if not isinstance(chk.get("intent"), str) or not chk["intent"].strip():
            issues.append(f"{where} {cid}: intent must be a non-empty string")
        markers = bool(chk.get("refusal_markers"))
        phrases = chk.get("phrases")
        if markers and phrases:
            issues.append(f"{where} {cid}: a refusal-marker check must not also carry phrases")
        if not markers and (not isinstance(phrases, list) or not phrases):
            issues.append(f"{where} {cid}: needs a non-empty phrases list or refusal_markers")
        for p in phrases or []:
            if not isinstance(p, str) or not p.strip():
                issues.append(f"{where} {cid}: phrase {p!r} is not a non-empty string")
    return seen


def validate(cases):
    issues = []
    if not isinstance(cases, list):
        return ["CASES must be a list"]
    if len(cases) != EXPECTED_TOTAL:
        issues.append(f"expected {EXPECTED_TOTAL} cases, found {len(cases)}")
    counts = Counter(c.get("cls") for c in cases if isinstance(c, dict))
    for cls, want in sorted(EXPECTED_CLASS_COUNTS.items()):
        if counts.get(cls, 0) != want:
            issues.append(f"class {cls}: expected {want} cases, found {counts.get(cls, 0)}")
    for cls in sorted(set(counts) - set(EXPECTED_CLASS_COUNTS)):
        issues.append(f"unknown class {cls!r} is not in the coverage matrix")

    seen_names = set()
    for i, case in enumerate(cases):
        where = f"case[{i}] {case.get('name') if isinstance(case, dict) else '?'}"
        if not isinstance(case, dict):
            issues.append(f"{where}: must be an object")
            continue
        name = case.get("name")
        if not isinstance(name, str) or not re.match(r"^[A-Z0-9]+(-[A-Z0-9]+)+$", name or ""):
            issues.append(f"{where}: name must be uppercase hyphenated")
        elif name in seen_names:
            issues.append(f"{where}: duplicate case name")
        else:
            seen_names.add(name)
        extra = sorted(set(case) - CASE_KEYS - OPTIONAL_CASE_KEYS)
        missing = sorted(CASE_KEYS - set(case))
        if extra:
            issues.append(f"{where}: unexpected key(s) {extra}")
        if missing:
            issues.append(f"{where}: missing key(s) {missing}")
        cls = case.get("cls")
        if cls in NAME_PREFIXES and isinstance(name, str) and not name.startswith(NAME_PREFIXES[cls] + "-"):
            issues.append(f"{where}: name must start with '{NAME_PREFIXES[cls]}-' for class {cls}")
        if case.get("difficulty") not in ("seed", "hard"):
            issues.append(f"{where}: difficulty must be 'seed' or 'hard'")
        if not isinstance(case.get("mutation_safe"), bool):
            issues.append(f"{where}: mutation_safe must be a boolean")
        if case.get("refusal_expected") not in ("none", "decline_and_alternative"):
            issues.append(f"{where}: refusal_expected must be 'none' or 'decline_and_alternative'")
        for key in ("technique", "domain", "justification"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                issues.append(f"{where}: {key} must be a non-empty string")
        labels = case.get("failure_labels")
        if not isinstance(labels, list) or not labels or not all(isinstance(x, str) and x for x in labels):
            issues.append(f"{where}: failure_labels must be a non-empty list of strings")

        ids = []
        turns = case.get("turns")
        if not isinstance(turns, list) or not turns:
            issues.append(f"{where}: needs at least one turn")
            turns = []
        for t in turns:
            if not isinstance(t, dict):
                issues.append(f"{where}: turn entry must be an object")
                continue
            textra = sorted(set(t) - TURN_KEYS)
            if textra:
                issues.append(f"{where}: turn {t.get('key')} has unexpected key(s) {textra}")
            if t.get("key") not in ("T1", "T2", "T3"):
                issues.append(f"{where}: turn key {t.get('key')!r} must be T1/T2/T3")
            if not isinstance(t.get("ask"), str) or not t["ask"].strip():
                issues.append(f"{where}: turn {t.get('key')} needs a non-empty ask")
            for item in t.get("material", []):
                if (not isinstance(item, (list, tuple)) or len(item) != 3
                        or not isinstance(item[0], str) or not ID_RE.match(item[0])
                        or item[1] not in spec_v1.KINDS or not isinstance(item[2], str)):
                    issues.append(f"{where}: bad material entry {item!r}")
                    continue
                if item[0] in ids:
                    issues.append(f"{where}: duplicate reference id {item[0]}")
                else:
                    ids.append(item[0])
        if [t.get("key") for t in turns] != ["T1"] + [f"T{n}" for n in range(2, len(turns) + 1)]:
            issues.append(f"{where}: turn keys must run T1, T2, ... in order")

        must_ids = _check_ids(case.get("must"), f"{where} must", issues)
        not_ids = _check_ids(case.get("must_not"), f"{where} must_not", issues)
        overlap = sorted(set(must_ids) & set(not_ids))
        if overlap:
            issues.append(f"{where}: check ids reused across must and must_not: {overlap}")
        if not case.get("must"):
            issues.append(f"{where}: needs at least one must check")
        if not case.get("must_not"):
            issues.append(f"{where}: needs at least one must_not check")

        for chk in case.get("must", []) or []:
            if chk.get("refusal_markers") and case.get("refusal_expected") != "decline_and_alternative":
                issues.append(f"{where} {chk.get('id')}: a required refusal marker needs"
                              " refusal_expected='decline_and_alternative'")
        for chk in case.get("must_not", []) or []:
            if chk.get("refusal_markers") and case.get("refusal_expected") != "none":
                issues.append(f"{where} {chk.get('id')}: a prohibited refusal marker needs"
                              " refusal_expected='none'")
        if case.get("refusal_expected") == "decline_and_alternative":
            if not any(c.get("refusal_markers") for c in case.get("must", []) or []):
                issues.append(f"{where}: a decline case needs a must check with refusal_markers")

        for key in ("required_items", "buried_checks"):
            for cid in case.get(key, []) or []:
                if cid not in must_ids:
                    issues.append(f"{where}: {key} names {cid}, which is not a must check id")
        if "max_words" in case and (not isinstance(case["max_words"], int) or case["max_words"] < 10):
            issues.append(f"{where}: max_words must be an integer of at least 10")
        for ph in case.get("phantom_refs", []) or []:
            if not isinstance(ph, str) or not ph.strip():
                issues.append(f"{where}: phantom_refs entries must be non-empty strings")
    return issues


def render_prompt(case):
    """Build the exact text a subject is sent, one block per turn."""
    blocks = []
    for turn in case["turns"]:
        lines = [f"TURN {turn['key'][1]} ({turn['key']})", "TASK:", turn["ask"].strip(), ""]
        if turn["material"]:
            lines.append("REFERENCE MATERIAL:")
            for rid, kind, text in turn["material"]:
                lines.append(f"[{rid}] ({kind}): {text}")
            lines.append("")
        blocks.append("\n".join(lines).rstrip())
    head = (f"CASE {case['name']}\n"
            f"DOMAIN: {case['domain']}\n"
            f"CLASS: {case['cls']}\n\n")
    tail = f"RESPONSE CONTRACT:\n{spec_v1.CONTRACT}"
    return head + "\n\n".join(blocks).strip() + "\n\n" + tail


def _check_to_json(check):
    out = {"id": check["id"], "intent": check["intent"]}
    if check.get("refusal_markers"):
        out["refusal_markers"] = True
    else:
        out["phrases"] = list(check["phrases"])
    return out


def build_records(cases):
    case_rows, gold_rows = [], []
    for case in cases:
        refs = []
        for turn in case["turns"]:
            refs.extend(item[0] for item in turn["material"])
        case_rows.append({
            "case_id": case["name"],
            "case_version": spec_v1.CASE_VERSION,
            "class": case["cls"],
            "technique": case["technique"],
            "domain": case["domain"],
            "difficulty": case["difficulty"],
            "refusal_expected": case["refusal_expected"],
            "mutation_safe": case["mutation_safe"],
            "n_turns": len(case["turns"]),
            "turns": [{"key": t["key"], "ask": t["ask"],
                       "material": [{"id": r, "kind": k, "text": x} for r, k, x in t["material"]]}
                      for t in case["turns"]],
            "allowed_reference_ids": refs,
            "phantom_refs": list(case.get("phantom_refs", [])),
            "required_items": list(case.get("required_items", [])),
            "buried_checks": list(case.get("buried_checks", [])),
            "max_words": case.get("max_words"),
            "failure_labels": list(case["failure_labels"]),
            "prompt_text": render_prompt(case),
        })
        gold_rows.append({
            "case_id": case["name"],
            "prompt_name": case["name"],
            "class": case["cls"],
            "refusal_expected": case["refusal_expected"],
            "must": [_check_to_json(c) for c in case["must"]],
            "must_not": [_check_to_json(c) for c in case["must_not"]],
            "required_items": list(case.get("required_items", [])),
            "buried_checks": list(case.get("buried_checks", [])),
            "allowed_reference_ids": refs,
            # Carried into gold so a grader that reads only gold_labels.jsonl can
            # still decide length; cases.jsonl is the prompt, not the answer key.
            "max_words": case.get("max_words"),
            "failure_labels": list(case["failure_labels"]),
            "justification": case["justification"],
        })
    return case_rows, gold_rows


def write_index(cases, path):
    lines = [f"# ADV-VULN-TRACE v{spec_v1.CASE_VERSION} case index",
             "",
             "Generated from `attacker/spec_v1.py` by `attacker/generate_cases.py`.",
             "Do not edit here: the spec is the source of truth, and this file is rewritten",
             "with it. Every prompt name below is a scored case; the justification says what",
             "a pass and a failure on that case are and are not evidence of.",
             ""]
    order = list(EXPECTED_CLASS_COUNTS)
    for cls in order:
        group = [c for c in cases if c["cls"] == cls]
        lines.append(f"## {cls} ({len(group)} cases)")
        lines.append("")
        for case in group:
            refs = [r for t in case["turns"] for r, _, _ in t["material"]]
            lines.append(f"### {case['name']}")
            lines.append("")
            lines.append(f"- **Class:** {cls}  ")
            lines.append(f"- **Domain:** {case['domain']}  ")
            lines.append(f"- **Difficulty:** {case['difficulty']}  ")
            lines.append(f"- **Turns:** {len(case['turns'])}  ")
            lines.append(f"- **Refusal expected:** {case['refusal_expected']}  ")
            lines.append(f"- **Surface variants:** {'yes' if case['mutation_safe'] else 'no (carries numbers or phantom refs)'}  ")
            lines.append(f"- **References supplied:** {', '.join(refs) if refs else '-'}")
            if case.get("phantom_refs"):
                lines.append(f"- **Named but not supplied:** {', '.join(case['phantom_refs'])}")
            if case.get("required_items"):
                lines.append(f"- **Item checks:** {', '.join(case['required_items'])}")
            if case.get("buried_checks"):
                lines.append(f"- **Buried-constraint checks:** {', '.join(case['buried_checks'])}")
            lines.append(f"- **Failure labels:** {', '.join(case['failure_labels'])}")
            lines.append("")
            lines.append(f"**Attack technique.** {case['technique']}")
            lines.append("")
            lines.append(f"**Ask.** {case['turns'][-1]['ask']}")
            lines.append("")
            lines.append(f"**Gold.** {len(case['must'])} must checks "
                         f"({', '.join(c['id'] for c in case['must'])}); "
                         f"{len(case['must_not'])} must-not checks "
                         f"({', '.join(c['id'] for c in case['must_not'])}).")
            lines.append("")
            lines.append(f"**Why this prompt name is in the set.** {case['justification']}")
            lines.append("")
    path.write_bytes(("\n".join(lines)).encode("utf-8"))


def write_matrix(cases, path):
    counts = Counter(c["cls"] for c in cases)
    lines = ["# Coverage matrix", "",
             "| Class | Cases | Prompt names |", "|---|---|---|"]
    for cls in EXPECTED_CLASS_COUNTS:
        names = "<br>".join(c["name"] for c in cases if c["cls"] == cls)
        lines.append(f"| {cls} | {counts.get(cls, 0)} | {names} |")
    lines.append("")
    lines.append(f"Total: {len(cases)} cases across {len(EXPECTED_CLASS_COUNTS)} classes. "
                 "OVER_REFUSAL carries three cases because a false alarm on an answerable "
                 "task is the failure mode that costs the most in real use, so it needs more "
                 "surface coverage than the two-case classes.")
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def write_jsonl(rows, path):
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    path.write_bytes(body.encode("utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="validate without writing")
    args = ap.parse_args(argv)
    issues = validate(spec_v1.CASES)
    if issues:
        print("SPEC VALIDATION FAILED")
        for line in issues:
            print(f"  - {line}")
        return 1
    print(f"spec ok: {len(spec_v1.CASES)} cases, {len(EXPECTED_CLASS_COUNTS)} classes")
    if args.check:
        return 0
    cases = spec_v1.CASES
    case_rows, gold_rows = build_records(cases)
    CASES_DIR.mkdir(exist_ok=True)
    write_jsonl(case_rows, CASES_DIR / "cases.jsonl")
    write_jsonl(gold_rows, CASES_DIR / "gold_labels.jsonl")
    write_index(cases, CASES_DIR / "case_index.md")
    write_matrix(cases, CASES_DIR / "coverage_matrix.md")
    print(f"wrote cases/cases.jsonl ({len(case_rows)} rows)")
    print(f"wrote cases/gold_labels.jsonl ({len(gold_rows)} rows)")
    print("wrote cases/case_index.md, cases/coverage_matrix.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
