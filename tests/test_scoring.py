import pytest

from pronunciation_coach.phonemes import ExpectedWord, expected_for_sentence
from pronunciation_coach.scoring import align, score, status_for
from pronunciation_coach.tips import EPENTHESIS_TIP, FINAL_CONSONANT_TIP, PAIR_TIPS


def words(*pairs):
    return [ExpectedWord(t, p.split()) for t, p in pairs]


def test_align_identity():
    ops = align(list("abc"), list("abc"))
    assert [o.kind for o in ops] == ["match"] * 3


def test_align_substitution_deletion_insertion():
    ops = align(["θ", "ɪ", "ŋ", "k"], ["t", "ɪ", "ŋ"])
    assert [(o.kind, o.expected, o.actual) for o in ops] == [
        ("substitution", "θ", "t"), ("match", "ɪ", "ɪ"), ("match", "ŋ", "ŋ"), ("deletion", "k", None),
    ]
    ops = align(["s", "k"], ["ɛ", "s", "k"])
    assert [o.kind for o in ops] == ["insertion", "match", "match"]


def test_align_prefers_close_pairs():
    ops = align(["s", "ɪ", "t"], ["s", "i", "t"])
    assert ops[1].kind == "close"


def test_perfect_score(phonemize):
    exp = expected_for_sentence("I think this is good", phonemize=phonemize)
    flat = [p for w in exp for p in w.phonemes]
    r = score(exp, flat)
    assert r.accuracy == 1.0
    assert all(w.status == "good" for w in r.words)
    assert r.errors == []


def test_th_substitution_reports_message_and_tip():
    exp = words(("think", "θ ɪ ŋ k"))
    r = score(exp, ["t", "ɪ", "ŋ", "k"])
    assert r.accuracy == pytest.approx(0.75)
    w = r.words[0]
    assert w.status == "unsure"
    assert w.heard == ["t", "ɪ", "ŋ", "k"]
    [err] = r.errors
    assert err.message == "think: said /t/, expected /θ/"
    assert err.tip == PAIR_TIPS[("θ", "t")]


def test_dropped_final_consonant():
    exp = words(("cat", "k æ t"))
    r = score(exp, ["k", "æ"])
    [err] = r.errors
    assert err.kind == "deletion"
    assert err.message == "cat: missing /t/"
    assert err.tip == FINAL_CONSONANT_TIP


def test_epenthetic_e_before_s_cluster():
    exp = words(("the", "ð ə"), ("school", "s k u l"))
    r = score(exp, ["ð", "ə", "ɛ", "s", "k", "u", "l"])
    [err] = r.errors
    assert err.kind == "insertion"
    assert err.word == "school"
    assert err.tip == EPENTHESIS_TIP
    # 4 credits / (4 + 0.5 insertion penalty)
    assert r.words[1].score == pytest.approx(4 / 4.5)


def test_leading_epenthesis_on_first_word():
    exp = words(("school", "s k u l"))
    r = score(exp, ["e", "s", "k", "u", "l"])
    assert r.errors[0].word == "school"
    assert r.errors[0].tip == EPENTHESIS_TIP


def test_close_pair_partial_credit():
    exp = words(("sit", "s ɪ t"))
    r = score(exp, ["s", "i", "t"])
    assert r.words[0].score == pytest.approx(2.5 / 3)
    assert r.errors[0].kind == "close"


def test_v_b_is_a_full_error():
    exp = words(("very", "v ɛ ɹ i"))
    r = score(exp, ["b", "ɛ", "ɹ", "i"])
    assert r.words[0].score == pytest.approx(0.75)
    assert r.errors[0].tip == PAIR_TIPS[("v", "b")]


def test_words_mapped_independently():
    exp = words(("this", "ð ɪ s"), ("is", "ɪ z"))
    r = score(exp, ["d", "ɪ", "s", "ɪ", "s"])
    assert [w.text for w in r.words] == ["this", "is"]
    assert r.words[0].errors[0].message == "this: said /d/, expected /ð/"
    assert r.words[1].errors[0].message == "is: said /s/, expected /z/"
    assert r.accuracy == pytest.approx(3 / 5)


def test_silence_scores_zero():
    exp = words(("cat", "k æ t"))
    r = score(exp, [])
    assert r.accuracy == 0.0
    assert r.words[0].status == "bad"
    assert len(r.errors) == 3


def test_word_without_phonemes_is_unknown():
    exp = words(("cat", "k æ t")) + [ExpectedWord("???", [])]
    r = score(exp, ["k", "æ", "t"])
    assert r.words[1].status == "unknown"
    assert r.accuracy == 1.0


def test_no_expected_phonemes():
    r = score([], ["a"])
    assert r.accuracy == 0.0 and r.words == []


@pytest.mark.parametrize("value,status", [(0.95, "good"), (0.8, "good"), (0.79, "unsure"),
                                          (0.5, "unsure"), (0.49, "bad"), (None, "unknown")])
def test_status_thresholds(value, status):
    assert status_for(value) == status
