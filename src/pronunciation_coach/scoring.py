"""Phoneme alignment (Needleman-Wunsch with backtrace) and per-word scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .phonemes import ExpectedWord
from .tips import VOWELS, tip_for

GOOD_THRESHOLD = 0.80
UNSURE_THRESHOLD = 0.50
PARTIAL_CREDIT = 0.5
INSERTION_WEIGHT = 0.5  # each extra phoneme counts this much against the score

_CLOSE_PAIRS = [
    ("i", "ɪ"), ("ə", "ʌ"), ("ə", "ɪ"), ("ʌ", "ɑ"), ("ɑ", "ɔ"), ("u", "ʊ"),
    ("ɚ", "ɜ"), ("ɚ", "ə"), ("æ", "ɛ"), ("e", "ɛ"), ("eɪ", "e"), ("oʊ", "o"),
    ("ɾ", "t"), ("ɾ", "d"), ("ə", "ɛ"), ("ɑ", "a"), ("o", "ɔ"), ("ɹ", "ɚ"),
]
CLOSE_PAIRS: frozenset[frozenset[str]] = frozenset(frozenset(p) for p in _CLOSE_PAIRS)

SUB_COST = 1.0
CLOSE_COST = 0.4
GAP_COST = 1.0


def is_close(a: str, b: str) -> bool:
    return frozenset((a, b)) in CLOSE_PAIRS


def _sub_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    return CLOSE_COST if is_close(a, b) else SUB_COST


@dataclass
class Op:
    kind: str  # match | close | substitution | deletion | insertion
    expected: str | None
    actual: str | None
    exp_index: int | None  # index into the expected sequence (None for insertions)


def align(expected: list[str], actual: list[str]) -> list[Op]:
    """Global alignment minimizing edit cost; returns the operation path."""
    n, m = len(expected), len(actual)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i * GAP_COST
        back[i][0] = "D"
    for j in range(1, m + 1):
        cost[0][j] = j * GAP_COST
        back[0][j] = "I"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = cost[i - 1][j - 1] + _sub_cost(expected[i - 1], actual[j - 1])
            dele = cost[i - 1][j] + GAP_COST
            ins = cost[i][j - 1] + GAP_COST
            best = min(diag, dele, ins)
            cost[i][j] = best
            back[i][j] = "M" if best == diag else ("D" if best == dele else "I")

    ops: list[Op] = []
    i, j = n, m
    while i > 0 or j > 0:
        step = back[i][j]
        if step == "M":
            e, a = expected[i - 1], actual[j - 1]
            kind = "match" if e == a else ("close" if is_close(e, a) else "substitution")
            ops.append(Op(kind, e, a, i - 1))
            i, j = i - 1, j - 1
        elif step == "D":
            ops.append(Op("deletion", expected[i - 1], None, i - 1))
            i -= 1
        else:
            ops.append(Op("insertion", None, actual[j - 1], None))
            j -= 1
    ops.reverse()
    return ops


@dataclass
class PhonemeError:
    kind: str
    word: str
    word_index: int
    expected: str | None
    actual: str | None
    message: str
    tip: str | None = None


@dataclass
class WordResult:
    text: str
    index: int
    expected: list[str]
    heard: list[str]
    score: float | None
    status: str  # good | unsure | bad | unknown
    errors: list[PhonemeError] = field(default_factory=list)


@dataclass
class ScoreResult:
    accuracy: float
    words: list[WordResult]
    errors: list[PhonemeError]
    expected: list[str]
    recognized: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def status_for(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= GOOD_THRESHOLD:
        return "good"
    if score >= UNSURE_THRESHOLD:
        return "unsure"
    return "bad"


def _message(kind: str, word: str, expected: str | None, actual: str | None) -> str:
    if kind in ("substitution", "close"):
        return f"{word}: said /{actual}/, expected /{expected}/"
    if kind == "deletion":
        return f"{word}: missing /{expected}/"
    return f"{word}: extra /{actual}/"


def _is_epenthesis(op: Op, nxt: int | None, flat: list[str], owner: list[int],
                   word_start: dict[int, int]) -> bool:
    return (
        nxt is not None
        and op.actual in VOWELS
        and nxt == word_start[owner[nxt]]
        and flat[nxt] == "s"
        and nxt + 1 < len(flat)
        and owner[nxt + 1] == owner[nxt]
        and flat[nxt + 1] not in VOWELS
    )


def score(expected_words: list[ExpectedWord], recognized: list[str]) -> ScoreResult:
    flat: list[str] = []
    owner: list[int] = []  # word index of each expected phoneme
    word_start: dict[int, int] = {}
    for wi, w in enumerate(expected_words):
        word_start[wi] = len(flat)
        flat.extend(w.phonemes)
        owner.extend([wi] * len(w.phonemes))

    ops = align(flat, recognized)

    nw = len(expected_words)
    credit = [0.0] * nw
    inserted = [0] * nw
    heard: list[list[str]] = [[] for _ in range(nw)]
    word_errors: list[list[PhonemeError]] = [[] for _ in range(nw)]

    last_word = 0
    for k, op in enumerate(ops):
        if op.exp_index is not None:
            wi = owner[op.exp_index]
            last_word = wi
        else:
            # Insertions belong to the previous word; leading ones to the first word
            # that has an expected phoneme after them.
            nxt = next((o.exp_index for o in ops[k:] if o.exp_index is not None), None)
            if not any(o.exp_index is not None for o in ops[:k]):
                wi = owner[nxt] if nxt is not None else 0
            elif _is_epenthesis(op, nxt, flat, owner, word_start):
                # A vowel before an s+consonant onset belongs to the following word.
                wi = owner[nxt]
            else:
                wi = last_word
        if nw == 0:
            break
        if op.actual is not None:
            heard[wi].append(op.actual)
        if op.kind == "match":
            credit[wi] += 1.0
            continue
        if op.kind == "close":
            credit[wi] += PARTIAL_CREDIT
        if op.kind == "insertion":
            inserted[wi] += 1

        word = expected_words[wi].text
        phs = expected_words[wi].phonemes
        pos_in_word = op.exp_index - word_start[wi] if op.exp_index is not None else None
        word_final = (pos_in_word == len(phs) - 1) if pos_in_word is not None else (
            # insertion after the last phoneme of the word
            k + 1 >= len(ops) or ops[k + 1].exp_index is None or owner[ops[k + 1].exp_index] != wi
        )
        before_s = (
            op.kind == "insertion"
            and k + 1 < len(ops)
            and ops[k + 1].exp_index is not None
            and ops[k + 1].exp_index == word_start[wi]
            and ops[k + 1].expected == "s"
        )
        tip = tip_for(
            "substitution" if op.kind == "close" else op.kind,
            op.expected or "", op.actual or "",
            word_final=word_final, word_initial_before_s=before_s,
        )
        word_errors[wi].append(
            PhonemeError(op.kind, word, wi, op.expected, op.actual,
                         _message(op.kind, word, op.expected, op.actual), tip)
        )

    words: list[WordResult] = []
    total_credit = 0.0
    total_den = 0.0
    for wi, w in enumerate(expected_words):
        n = len(w.phonemes)
        if n == 0:
            s = None
        else:
            den = n + INSERTION_WEIGHT * inserted[wi]
            s = max(0.0, min(1.0, credit[wi] / den))
            total_credit += credit[wi]
            total_den += den
        words.append(WordResult(w.text, wi, w.phonemes, heard[wi], s, status_for(s), word_errors[wi]))

    accuracy = total_credit / total_den if total_den else 0.0
    all_errors = [e for we in word_errors for e in we]
    return ScoreResult(round(accuracy, 4), words, all_errors, flat, recognized)
