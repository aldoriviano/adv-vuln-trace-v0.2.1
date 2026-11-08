import sys
from pathlib import Path
sys.path.insert(0, ".")
from grader import words, score

cases = score.read_jsonl(Path("cases/cases.jsonl"))
gold = {g["case_id"]: g for g in score.read_jsonl(Path("cases/gold_labels.jsonl"))}
ex = {r["id"]: r for r in score.read_jsonl(Path("tests/fixtures/failure_exemplars.jsonl"))}

def trace(text, phrase):
    needle = words.tokens(phrase)
    hit = False
    for ci, clause in enumerate(words.clauses(text)):
        for i in range(0, max(0, len(clause) - len(needle) + 1)):
            if clause[i:i + len(needle)] != needle:
                continue
            hit = True
            before, after = clause[:i], clause[i + len(needle):]
            pre = [t for t in before if words._cue(t, words.NEGATION_CUES)]
            pre_h = [t for t in before if words._cue(t, words.HEDGE_CUES)]
            post = [t for t in after if words._cue(t, words.NEGATION_CUES)]
            post_p = [t for t in after if words._cue(t, words._POST_QUALIFIERS)]
            muted = bool(pre or pre_h or post or post_p)
            print(f"    region{ci} {'MUTED' if muted else 'asserts'} :: before neg={pre} hedge={pre_h} | after neg={post} postq={post_p}")
    if not hit:
        print("    (phrase not present)")

for eid in sys.argv[1:]:
    row = ex[eid]
    g = gold[row["case_id"]]
    print(f"== {eid} ({row['case_id']})")
    for chk in g["must_not"]:
        for p in chk["phrases"]:
            trace(row["answer"], p)
