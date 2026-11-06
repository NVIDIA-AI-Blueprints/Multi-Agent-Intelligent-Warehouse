# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Deterministic Copilot intent classification.

Classifies operator messages into ASK / ANALYZE / ACT / OBSERVE_OUTCOME
without an LLM call. Pattern matching is ordered: OBSERVE_OUTCOME markers,
then ACT (an explicit command that is not a cancellation), then ANALYZE
markers (recommendation requests), then default to ASK.

ACT can select a stored recommendation and submit it for governance, so it
needs a command: an action verb that opens a clause of a sentence that is not
a question. A message that only mentions an action ("Should we reassign
Maria?", "I didn't ask you to move it", "Tell me about the dispatch") is not
ACT.
"""

from __future__ import annotations

import re

from .models import CopilotIntent

# ── OBSERVE_OUTCOME markers — post-execution observation ─────────────────────
# Must be checked BEFORE ACT so "did it work" doesn't match ACT's "execute"/"do" patterns.
_OBSERVE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bdid\s+it\s+(work|help|run|execute|succeed|go\s+through)\b", re.IGNORECASE),
    re.compile(r"\bdid\s+that\s+(work|help|execute|succeed|happen)\b", re.IGNORECASE),
    re.compile(r"\bdid\s+the\s+(action|execution|labor|allocation|worker)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+happened\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(was\s+the\s+|is\s+the\s+)?outcome\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(was\s+the\s+)?result\b", re.IGNORECASE),
    re.compile(r"\bany\s+(improvement|change|effect|impact)\b", re.IGNORECASE),
    re.compile(r"\bdid\s+(it|that|the\s+action)\s+(improve|reduce|fix|resolve)\b", re.IGNORECASE),
    re.compile(r"\b(show|check)\s+(me\s+)?(the\s+)?(outcome|result|improvement|effect)\b", re.IGNORECASE),
    re.compile(r"\bis\s+(wave\s+17|the\s+backlog|the\s+risk)\s+(better|lower|improved|reduced)\b", re.IGNORECASE),
]

# ── ACT markers — the action vocabulary ──────────────────────────────────────
# Match whole-word or start-of-phrase to avoid false positives like "movement".
# A match anywhere means the message *names* an action; it is ACT only when
# the action is also commanded (see is_directive below).
_ACT_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(do it|execute|confirm|apply|approve|commit)\b", re.IGNORECASE),
    re.compile(r"\b(allocate|reassign|move|reprioritize|reprioritise|dispatch)\b", re.IGNORECASE),
    re.compile(r"\b(make it happen|go ahead|proceed with)\b", re.IGNORECASE),
    re.compile(r"\bproceed\b", re.IGNORECASE),
    re.compile(r"\bprepare (that|this|the) action\b", re.IGNORECASE),
    # Explicit index reference to a listed recommendation: "do the first one", "do #1", etc.
    re.compile(r"\bdo (the )?(first|second|third|1st|2nd|3rd|#?1|#?2|#?3|one|that)\b", re.IGNORECASE),
]

# ── Cancellation / negation guard ────────────────────────────────────────────
# A message that calls an action off ("cancel that", "never mind") or negates an
# operational verb ("don't dispatch anything", "no need to move it") must never
# select and run a pending recommendation. The guard is deliberately narrow so
# that a command with an unrelated negation ("Reprioritize wave 17 so we don't
# miss the cutoff", "Approve it, I don't see any risk") stays ACT.

_APOS = r"['\u2019]?"  # don't / dont / don’t

# Operational verbs a negation can govern (the ACT vocabulary plus the
# capability verbs). "do" only counts with an object pronoun ("don't do it").
_NEGATABLE_VERB = (
    r"(?:execute|confirm|apply|approve|commit|allocate|reassign|assign|move"
    r"|reprioriti[sz]e|dispatch|release|proceed|prepare|go\s+ahead"
    r"|make\s+it\s+happen|(?:do|run)\s+(?:it|that|this|anything|any\s+of))\b"
)

_NEGATOR = (
    r"(?<!why\s)\b(?:"
    rf"do\s+not|don{_APOS}t|never|not|no\s+need\s+(?:to|for)"
    rf"|must\s+not|mustn{_APOS}t|should\s+not|shouldn{_APOS}t"
    rf"|will\s+not|won{_APOS}t|would\s+not|wouldn{_APOS}t"
    rf"|cannot|can\s+not|can{_APOS}t|could\s+not|couldn{_APOS}t"
    rf"|didn{_APOS}t|hasn{_APOS}t|haven{_APOS}t|hadn{_APOS}t"
    rf"|isn{_APOS}t|aren{_APOS}t|wasn{_APOS}t|weren{_APOS}t"
    r"|nobody|no\s*-?\s*one|none\s+of\s+us"
    r")"
)

# Words allowed between the negator and the verb ("don't actually move",
# "not to move", "don't you dare move", "no need to go and dispatch", and
# reported requests: "I didn't ask you to move it", "nobody said to reassign").
_FILLER = (
    r"(?:to|you|we|i|me|us|them|actually|really|yet|just|even|ever|please|now"
    r"|need|have|want(?:ed)?|bother|try|dare|go\s+and"
    r"|ask(?:ed)?|tell|told|say|said|mean|meant|agree(?:d)?|plan(?:ned)?"
    r"|intend(?:ed)?|decide(?:d)?)"
)

# Things a cancel-family verb can take as its object: the pending action.
_ACTION_OBJECT = (
    r"(?:it|that|this|everything|all(?:\s+of\s+(?:it|that|this))?"
    r"|(?:the|my|your|that|this)\s+"
    r"(?:(?:last|current|pending|whole|entire|previous|proposed|recommended)\s+)?"
    r"(?:action|actions|dispatch|move|reassignment|allocation"
    r"|reprioriti[sz]ation|release|assignment|maintenance|plan|request|order"
    r"|recommendation|proposal|job|change|changes))\b"
)

_CANCEL_VERB = (
    r"(?:cancel(?:l?ing|l?ed)?|halt(?:ing|ed)?|abort(?:ing|ed)?|stop(?:ping|ped)?"
    r"|call(?:ing)?\s+off|scrap|undo|withdraw|revoke)"
)

# Discourse openers that may precede a leading cancel marker ("Actually, no.").
_OPENER = r"(?:(?:actually|ok(?:ay)?|oh|hmm+|um+|sorry|wait|on\s+second\s+thought)\W+)*"

# (a) The message opens with a cancel / negation marker.
_LEADING_CANCEL = re.compile(
    r"^\W*" + _OPENER + r"(?:"
    r"cancel\w*|halt\w*|abort\w*|stop(?:ping|ped)?|wait|hold\s+off"
    r"|never\s*-?\s*mind|not\s+now|not\s+yet"
    r"|no\s+need(?!\s+to\s+worry)"
    rf"|must\s+not|mustn{_APOS}t"
    rf"|do\s+not(?!\s+worry)|don{_APOS}t(?!\s+worry)|never"
    r"|nope|nah|no(?!\s+(?:problem|worries|worry|issue|issues|doubt)\b)"
    r")\b",
    re.IGNORECASE,
)

# (b) A negator directly governs an operational verb.
_NEGATED_ACT = re.compile(
    _NEGATOR + rf"(?:\s+{_FILLER}){{0,3}}\s+" + _NEGATABLE_VERB, re.IGNORECASE
)

# (c) A cancel-family verb takes the pending action as its object, or an
# unambiguous call-off idiom appears anywhere ("..., never mind").
_CANCEL_ACTION = re.compile(
    rf"\b{_CANCEL_VERB}\s+{_ACTION_OBJECT}"
    r"|\bhold\s+off\b|\bnever\s*-?\s*mind\b",
    re.IGNORECASE,
)

# ── Directive guard — ACT needs a command, not a mention ─────────────────────
# An action verb only makes a message ACT when it opens a clause ("Do it.",
# "OK, go ahead", "Let's reprioritize wave 17", "If it is safe, move it") of a
# sentence that is not a question. A question ("Should we reassign Maria?",
# "Why not move it?"), a report ("I didn't ask you to move it") or a noun use
# ("Tell me about the dispatch") names an action without asking for it.

# A sentence and its terminator(s); a sentence containing "?" is a question.
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]*")

# Clause breaks inside a sentence: comma, semicolon, en / em dash, " - ".
_CLAUSE_BREAK = re.compile(r"[,;–—]|\s-\s")

# Words that may precede the verb of a command in the same clause.
_DIRECTIVE_LEAD = (
    r"(?:(?:please|pls|kindly|ok(?:ay)?|yes|yeah|yep|yup|sure|alright"
    r"|all\s+right|right|fine|great|good|perfect|cool|agreed"
    r"|sounds\s+good|looks\s+good|then|so|now|just|and"
    rf"|let{_APOS}s|let\s+us|you\s+(?:can|may)"
    r"|i\s+(?:want|need)\s+you\s+to"
    rf"|i{_APOS}d\s+like\s+you\s+to|i\s+would\s+like\s+you\s+to"
    r")\W+)*"
)

# The command verbs: the ACT vocabulary in imperative position.
_DIRECTIVE_VERB = (
    r"(?:do\s+it|do\s+(?:the\s+)?(?:first|second|third|1st|2nd|3rd|#?[123]|one|that)"
    r"|execute|confirm|apply|approve|commit|allocate|reassign|move"
    r"|reprioriti[sz]e|dispatch|make\s+it\s+happen|go\s+ahead|proceed"
    r"|prepare\s+(?:that|this|the)\s+action)\b"
)

_DIRECTIVE_CLAUSE = re.compile(
    r"^\W*" + _DIRECTIVE_LEAD + _DIRECTIVE_VERB, re.IGNORECASE
)

# ── ANALYZE markers — recommendation-oriented questions ───────────────────────
_ANALYZE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bwhat should (we|i|you)\b", re.IGNORECASE),
    re.compile(r"\bwhat (do|would|can) (we|i|you) (do|recommend|suggest)\b", re.IGNORECASE),
    re.compile(r"\b(recommend|recommendations?)\b", re.IGNORECASE),
    re.compile(r"\bhow should (we|i|you)\b", re.IGNORECASE),
    re.compile(r"\bhow (can|could|do) (we|i|you)\b", re.IGNORECASE),
    re.compile(r"\bbest (action|response|approach|course)\b", re.IGNORECASE),
    re.compile(r"\b(protect|mitigate|address|fix|resolve|handle) (this|the|wave|risk)\b", re.IGNORECASE),
    re.compile(r"\bwhat('s| is) (our|the) (best|next|recommended)\b", re.IGNORECASE),
    re.compile(r"\bwhat (action|step|option)s?\b", re.IGNORECASE),
    re.compile(r"\breduce (the )?risk\b", re.IGNORECASE),
    re.compile(r"\bimprove (the )?(situation|status|wave|throughput)\b", re.IGNORECASE),
    re.compile(r"\bwhat (are|would be) (our|the|my) (best |)options\b", re.IGNORECASE),
]


def is_cancellation(message: str) -> bool:
    """
    True if the message calls off or negates an action, so it must not run one.

    A message is a cancellation when

    (a) it opens with a cancel / negation marker ("cancel", "stop", "halt",
        "never mind", "hold off", "not now", "no, ...", "don't ...", "never
        ...", "no need ...", "wait"), except "no problem" / "no worries" /
        "don't worry"; or
    (b) a negator directly governs an operational verb ("don't dispatch",
        "not to move", "no need to dispatch", "mustn't reassign"); or
    (c) a cancel-family verb takes the pending action as its object
        ("cancel that", "halt the dispatch"), or "never mind" / "hold off"
        appears anywhere.

    A negation of anything else ("so we don't miss the cutoff", "I don't see
    any risk") is not a cancellation. A question that merely opens with a
    marker and names no operational verb ("Wait, why is FL-01 down?") is left
    to the conversational path: without an ACT verb it cannot run anything.
    """
    if _NEGATED_ACT.search(message) or _CANCEL_ACTION.search(message):
        return True
    if not _LEADING_CANCEL.search(message):
        return False
    is_question = message.rstrip().endswith("?")
    names_an_action = any(p.search(message) for p in _ACT_PATTERNS)
    return not (is_question and not names_an_action)


def is_directive(message: str) -> bool:
    """
    True if the message commands an action, so it may select a recommendation.

    Some clause of a sentence that is not a question must open with a command
    verb, optionally after a lead-in ("ok", "yes", "please", "let's", "then",
    "I want you to"). Cancellation is checked separately (is_cancellation):
    "Move it. Actually, cancel that." is directive and a cancellation, and the
    cancellation wins.
    """
    for sentence in _SENTENCE.findall(message):
        if "?" in sentence:
            continue
        for clause in _CLAUSE_BREAK.split(sentence):
            if _DIRECTIVE_CLAUSE.search(clause):
                return True
    return False


def classify(message: str) -> CopilotIntent:
    """
    Classify a single operator message into ASK / ANALYZE / ACT / OBSERVE_OUTCOME.

    Order of precedence:
    1. OBSERVE_OUTCOME markers (post-execution questions — checked before ACT)
    2. ACT — an explicit command (is_directive) that is not a cancellation /
       negated message ("cancel that", "don't dispatch anything"). A question
       or statement that only mentions an action ("Should we reassign
       Maria?") falls through to ANALYZE / ASK.
    3. ANALYZE markers (recommendation-oriented questions)
    4. Default: ASK (explanation / status / "why")
    """
    for pattern in _OBSERVE_PATTERNS:
        if pattern.search(message):
            return CopilotIntent.OBSERVE_OUTCOME

    if is_directive(message) and not is_cancellation(message):
        return CopilotIntent.ACT

    for pattern in _ANALYZE_PATTERNS:
        if pattern.search(message):
            return CopilotIntent.ANALYZE

    return CopilotIntent.ASK
