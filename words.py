"""Lexical helpers shared by the experimental grader.

Screening only: these are cheap surface-form checks, not semantic entailment.
Matching is negation- and hedge-aware so that a properly qualified denial
("the record does not establish criminal corruption") is not reported as an
overclaim, and a claim that survives only an unqualified assertion is flagged.
"""
import re
from unicodedata import normalize

_TRANSLIT = {
    "‘": "'", "’": "'", "‘": "'", "ʼ": "'",
    "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
}

# Strong breaks sever a denial from the phrase it qualifies: sentence-ending
# punctuation, semicolons and contrast conjunctions. Commas, colons, brackets and
# slashes are deliberately NOT breaks - in real prose the denial usually lands in a
# later comma clause of the same sentence ("favoritism ... , not an established
# fact"), and treating every comma as a boundary flagged those as overclaims.
# A full stop only breaks when followed by whitespace or the end of the text, so a
# decimal such as "1.3m" or "0.5 %" stays one token run.
_BREAK_WORDS = ("but|however|although|though|whereas|nevertheless|instead|"
                "despite|yet|because|since|unless|while")
_CLAUSE_BREAK = re.compile(r"\.(?=\s|$)|[!;?]|\b(?:" + _BREAK_WORDS + r")\b", re.IGNORECASE)
_PUNCT_BREAK = re.compile(r"\.(?=\s|$)|[!;?]", re.IGNORECASE)
_BREAK_SET = frozenset(_BREAK_WORDS.split("|"))

# Stems; matched with startswith so inflections are covered.
# Two stems present in the general v0.4 list are removed here because they are
# subject vocabulary in this corpus rather than qualifiers: "risk" (failure risk,
# exposure risk, delivery risk) and "fail" (radio failure, engine failure, test
# failed its check). Prefix matching turns both into cues, and either one lets a
# complying-looking violation mute its own region: "the radio failure caused the
# contact" was scored as qualified because the sentence named a failure. What the
# change costs is the verbal negation "the record fails to establish X", which no
# longer qualifies the region around it; the 33 researcher reference answers still
# pass, so no answer in this set relies on that suppression. The remaining
# region-level muting is a documented false-negative: see LIMITATIONS in score.py
# and tests/fixtures/grader_calibration.json.
NEGATION_CUES = (
    "not", "no", "none", "neither", "without", "lack",
    "absent", "deni", "disput", "unsupport", "unproven", "unfounded",
    "unlikely", "refut", "retract", "withdraw",
)
HEDGE_CUES = (
    "alleg", "suspect", "hypothes", "possib", "potentially", "appear",
    "reported", "reportedly", "claimed", "claiming", "accuse", "speculat", "may", "might", "could",
    "indicative", "suggest", "unclear", "uncertain", "unverified",
    "unconfirmed", "remain", "remains", "prima", "argued", "argues", "arguably", "pending",
    "whether", "unknown", "undetermined", "contingent",
)

# A phrase counts as asserted only when its whole region is cue-free. Cues found
# after the phrase are what usually qualify it in real prose: "favoritism ... is
# not an established fact", "a corrupt exchange ... can not be inferred".
_POST_QUALIFIERS = (
    "remain", "remains", "alleg", "hypothes", "possib", "unproven", "suggest",
    "unclear", "unverified", "speculat", "hedges", "qualifi",
    "allegation", "disput", "deni", "lack",
)


def norm(text):
    """Lowercase, ASCII-fold and strip punctuation to a single-spaced token stream."""
    if not isinstance(text, str):
        return ""
    out = text
    for src, dst in _TRANSLIT.items():
        out = out.replace(src, dst)
    out = normalize("NFKD", out).encode("ascii", "ignore").decode("ascii")
    out = out.lower().replace("n't", " not").replace("cannot", "can not")
    out = re.sub(r"[^a-z0-9]+", " ", out)
    return re.sub(r"\s+", " ", out).strip()


# Only adverbs that never change what is being claimed. "fully", "clearly", "explicitly"
# are NOT dropped: "fully demonstrated" and "demonstrated" are different claims.
_FILLER = frozenset({"yet", "currently", "also"})


def tokens(text):
    """Normalised tokens with meaning-neutral adverbs dropped (both sides of a match)."""
    return [t for t in norm(text).split() if t not in _FILLER]


def clauses(text, soft=False):
    """Token lists, one per qualifier region of the original text.

    soft=True splits on sentence punctuation only. It is used for phrases that
    themselves contain a contrast word ("since kessell approved"), which the
    hard split would cut in half so that they could never match.
    """
    out = text if isinstance(text, str) else ""
    for src, dst in _TRANSLIT.items():
        out = out.replace(src, dst)
    parts = (_PUNCT_BREAK if soft else _CLAUSE_BREAK).split(out)
    return [toks for toks in (tokens(p) for p in parts) if toks]


# Matched only as whole tokens. As prefixes they would license unrelated words:
# "northstar" starts with "no", and in this dataset that would qualify almost
# every phrase preceding it.
_EXACT_CUES = frozenset({"no", "not", "may", "prima", "report", "reports", "indicator",
                         "indicators", "claim", "claims", "remain", "argu"})


def _cue(tok, stems):
    for s in stems:
        if tok == s or (s not in _EXACT_CUES and tok.startswith(s)):
            return True
    return False


def qualified(clause, start, end):
    """True when the span [start,end) sits in a region that negates, hedges or retracts.

    Qualification is a property of the whole region, not of a fixed-width window:
    a list denial ("without extending to bribery, quid pro quo, or legal guilt") and
    a late retraction ("... is now WITHDRAWN") both sit several tokens from the phrase
    they govern.
    """
    if any(_cue(t, NEGATION_CUES) for t in clause[:start]):
        return True
    if any(_cue(t, HEDGE_CUES) for t in clause[:start]):
        return True
    if any(_cue(t, NEGATION_CUES) for t in clause[end:]):
        return True
    if any(_cue(t, _POST_QUALIFIERS) for t in clause[end:]):
        return True
    return False


def affirmative_hits(text, patterns):
    """Return the patterns that occur unqualified somewhere in `text`.

    Phrase patterns (containing a space) are matched token-wise so that word
    boundaries are respected; single-word patterns use a regex alternation.
    """
    hits = []
    for name, specs in patterns.items():
        for spec in specs if isinstance(specs, (list, tuple)) else [specs]:
            if any(_phrase_hit(clause, spec) for clause in clauses(text)):
                hits.append(name)
                break
    return hits


def needs_soft(needle):
    """True when a tokenised phrase contains a clause-break word."""
    return any(t in _BREAK_SET for t in needle)


def _phrase_hit(clause, spec):
    """True when `spec` occurs in `clause` at an unqualified position."""
    needle = tokens(spec)
    if not needle:
        return False
    for i in range(0, max(0, len(clause) - len(needle) + 1)):
        if clause[i:i + len(needle)] == needle and not qualified(clause, i, i + len(needle)):
            return True
    return False


def stems(text, minimum=5):
    """Content-word stems used for the lexical alternative-coverage proxy."""
    stop = {
        "that", "this", "these", "those", "with", "from", "have", "has", "had",
        "were", "which", "while", "their", "there", "they", "them", "would",
        "could", "should", "about", "above", "under", "into", "over", "upon",
        "after", "before", "because", "since", "either", "neither", "being",
        "been", "must", "may", "might", "shall", "than", "then", "when",
        "where", "what", "how", "does", "did", "made", "make", "makes",
        "against", "record", "records", "provide", "provided", "provides",
        "establish", "established", "evidence", "model", "claim", "claims",
    }
    seen = []
    for tok in tokens(text):
        if len(tok) < minimum or tok in stop or tok in seen:
            continue
        if _cue(tok, NEGATION_CUES) or _cue(tok, HEDGE_CUES):
            continue
        seen.append(tok)
    return seen


# ---- attributed-and-rejected claims ----------------------------------------------
# "The newsletter says X; that is unverified." / "The memo stated X. That figure is
# withdrawn." report a claim in order to reject it. A region scanner cannot see across
# the semicolon or the sentence end, so this is checked at sentence level: the phrase
# must sit after an attribution cue in its own sentence, and a rejection must follow it
# in that sentence or open the next one with a demonstrative ("that", "this", "it").
ATTRIB = frozenset({
    "says", "said", "claims", "claimed", "claim", "states", "stated", "stating", "alleges",
    "alleged", "according", "asserts", "asserted", "told", "reads", "reported", "reportedly",
    "release", "post", "memo", "memorandum", "newsletter", "flyer", "article", "blog",
    "note", "letter", "email", "briefing", "submission", "contractor", "vendor",
})
_REJ_SINGLE = frozenset({
    "unverified", "unsupported", "unproven", "unfounded", "contradicts", "contradicted",
    "contradict", "disputed", "incorrect", "withdrawn", "retracted", "misleading",
    "baseless", "unreliable", "refuted", "rejected", "wrong", "superseded", "erroneous",
})
_REJ_BIGRAM = frozenset({
    ("not", "supported"), ("no", "basis"), ("not", "established"), ("should", "not"),
    ("not", "reliable"), ("not", "shown"), ("not", "proven"), ("no", "evidence"),
    ("conflicts", "with"), ("not", "correct"), ("not", "true"), ("not", "credible"),
    ("not", "substantiated"), ("no", "supporting"), ("no", "report"), ("no", "record"),
    ("no", "data"),
})
_DEMONSTRATIVE = frozenset({"that", "this", "it", "such", "which", "the"})


def sentences(text):
    out = text if isinstance(text, str) else ""
    for src, dst in _TRANSLIT.items():
        out = out.replace(src, dst)
    parts = re.split(r"\.(?=\s|$)|[!?]|\n", out)
    return [toks for toks in (tokens(p) for p in parts) if toks]


def _rejects(span):
    if any(t in _REJ_SINGLE for t in span):
        return True
    return any((a, b) in _REJ_BIGRAM for a, b in zip(span, span[1:]))


def attributed_rejected(sents, si, i, j):
    """True when sentence `si`, span [i, j) is an attributed claim that is then rejected."""
    sent = sents[si]
    if not any(t in ATTRIB for t in sent[:i]):
        return False
    if _rejects(sent[j:]):
        return True
    nxt = sents[si + 1] if si + 1 < len(sents) else []
    return bool(nxt) and nxt[0] in _DEMONSTRATIVE and _rejects(nxt[:14])


def all_occurrences_attributed_rejected(text, needle):
    """True when the phrase occurs and every occurrence is an attributed-and-rejected claim."""
    sents = sentences(text)
    found = False
    for si, sent in enumerate(sents):
        for i in range(0, max(0, len(sent) - len(needle) + 1)):
            if sent[i:i + len(needle)] == needle:
                found = True
                if not attributed_rejected(sents, si, i, i + len(needle)):
                    return False
    return found
