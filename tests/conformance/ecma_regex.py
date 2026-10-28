"""ECMA-262 pattern syntax checking and translation to Python ``re`` syntax.

Parses the strict ECMA-262 2024 Pattern grammar (section 22.2.1) without
Annex B and without the ``u`` and ``v`` flags. Without the ``u`` flag the
source is a sequence of UTF-16 code units, so the parser splits each character
above U+FFFF into its surrogate pair and judges every unit on its own. ``to_python`` keeps ECMA
meaning: ASCII digit and word classes, the ECMA whitespace set, a dot that
stops at line terminators, and absolute anchors. Backreferences, named groups,
lookbehind, surrogates, and characters above U+FFFF raise ``Untranslatable``.

Identifier properties follow Unicode ``UNICODE_VERSION`` (15.1): Python's
Unicode 15.0 data plus the explicit 15.1 additions listed in this module.

Node tuples: ("char", c), ("dot",), ("escape", letter), ("class", negated,
items), ("range", low, high), ("group", capturing, name, node), ("backref",
number_or_name), ("assert", kind, node_or_None), ("quant", node, min, max,
lazy) with max None when unbounded, ("alt", [nodes]), ("seq", [nodes]).
A quantifier bound is an int, or its digit text without leading zeros when
that text is longer than 20 digits.
"""

import unicodedata

# The Unicode version of the identifier properties. unicodedata carries 15.0;
# _UNICODE_15_1_ID_START and _EXTRA_ID_CONTINUE add the 15.1 changes.
UNICODE_VERSION = "15.1"

__all__ = ["RegexResourceLimit", "RegexSyntaxError", "Untranslatable", "is_valid", "to_python"]


class RegexSyntaxError(ValueError):
    """The source is not a valid ECMA-262 pattern."""


class RegexResourceLimit(Exception):
    """The pattern nests beyond the parser's resource limit; it is neither valid nor invalid."""


class Untranslatable(ValueError):
    """The source is valid ECMA-262 syntax that the translator does not carry."""


_SYNTAX_CHARACTERS = frozenset("^$\\.*+?()[]{}|")
_CONTROL_ESCAPES = {"f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\x0b"}
_CLASS_ESCAPES = frozenset("dDsSwW")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_DECIMAL_DIGITS = frozenset("0123456789")
_BOUND_DIGITS = 20
# Python identifiers use XID_Start and XID_Continue. These code points are
# ID_Start (so also ID_Continue) but not XID_Start or XID_Continue.
_ID_NOT_XID = frozenset(
    "\u037a\u0e33\u0eb3\u309b\u309c\ufc5e\ufc5f\ufc60\ufc61\ufc62\ufc63\ufdfa\ufdfb"
    "\ufe70\ufe72\ufe74\ufe76\ufe78\ufe7a\ufe7c\ufe7e\uff9e\uff9f"
)
# Other_ID_Continue code points, plus the Unicode 15.1 additions to
# ID_Continue: ZERO WIDTH NON-JOINER, ZERO WIDTH JOINER, KATAKANA MIDDLE DOT,
# and HALFWIDTH KATAKANA MIDDLE DOT.
_EXTRA_ID_CONTINUE = frozenset(
    "\u00b7\u0387\u1369\u136a\u136b\u136c\u136d\u136e\u136f\u1370\u1371\u19da"
    "\u200c\u200d\u30fb\uff65"
)
# CJK Unified Ideographs Extension I, assigned in Unicode 15.1 (ID_Start).
_UNICODE_15_1_ID_START = (0x2EBF0, 0x2EE5D)


def _in_15_1_id_start(char):
    return _UNICODE_15_1_ID_START[0] <= ord(char) <= _UNICODE_15_1_ID_START[1]


def _assigned(char):
    return unicodedata.category(char) not in ("Cs", "Co", "Cn")


def _is_id_start(char):
    if char in _ID_NOT_XID or _in_15_1_id_start(char):
        return True
    return _assigned(char) and char != "_" and char.isidentifier()


def _is_id_continue(char):
    if char in _ID_NOT_XID or char in _EXTRA_ID_CONTINUE or _in_15_1_id_start(char):
        return True
    return _assigned(char) and ("a" + char).isidentifier()


def _is_group_name(name):
    # RegExpIdentifierName: ID_Start, "$", or "_", then ID_Continue, "$",
    # U+200C, or U+200D. The name holds code points, not code units.
    if not name:
        return False
    if not (_is_id_start(name[0]) or name[0] in "$_"):
        return False
    return all(_is_id_continue(char) or char in "$_\u200c\u200d" for char in name[1:])


def _code_units(source):
    # The UTF-16 code unit sequence of source, one unit per character.
    units = []
    for char in source:
        code = ord(char)
        if code > 0xFFFF:
            code -= 0x10000
            units.append(chr(0xD800 + (code >> 10)))
            units.append(chr(0xDC00 + (code & 0x3FF)))
        else:
            units.append(char)
    return "".join(units)


def _is_lead(char):
    return char is not None and 0xD800 <= ord(char) <= 0xDBFF


def _is_trail(char):
    return char is not None and 0xDC00 <= ord(char) <= 0xDFFF


def _pair(lead, trail):
    return chr(0x10000 + ((ord(lead) - 0xD800) << 10) + (ord(trail) - 0xDC00))


def _bound(text):
    # Digit text to an int, or to its digits without leading zeros when long.
    text = text.lstrip("0") or "0"
    return int(text) if len(text) <= _BOUND_DIGITS else text


def _bound_key(bound):
    # Orders ints and long digit texts by value without converting the text.
    text = str(bound)
    return len(text), text


class _Parser:
    """Recursive-descent parser for the strict ECMA-262 Pattern grammar."""

    def __init__(self, source):
        self.source = source
        self.pos = 0
        self.group_count = 0
        self.group_names = set()
        self.number_refs = []
        self.name_refs = []

    # Helpers

    def peek(self, offset=0):
        index = self.pos + offset
        return self.source[index] if index < len(self.source) else None

    def startswith(self, text):
        return self.source.startswith(text, self.pos)

    def error(self, message):
        raise RegexSyntaxError(f"{message} at offset {self.pos} in {self.source!r}")

    def expect(self, char):
        if self.peek() != char:
            self.error(f"expected {char!r}")
        self.pos += 1

    def digits(self):
        start = self.pos
        while self.peek() in _DECIMAL_DIGITS:
            self.pos += 1
        return self.source[start:self.pos]

    def hex_digits(self, count):
        text = self.source[self.pos:self.pos + count]
        if len(text) != count or not all(char in _HEX_DIGITS for char in text):
            return None
        self.pos += count
        return chr(int(text, 16))

    # Productions

    def parse(self):
        node = self.disjunction()
        if self.pos != len(self.source):
            self.error("unmatched ')'" if self.peek() == ")" else "unexpected character")
        for number in self.number_refs:
            if number > self.group_count:
                raise RegexSyntaxError(f"backreference \\{number} exceeds the group count in {self.source!r}")
        for name in self.name_refs:
            if name not in self.group_names:
                raise RegexSyntaxError(f"backreference to undefined group {name!r} in {self.source!r}")
        return node

    def disjunction(self):
        alternatives = [self.alternative()]
        while self.peek() == "|":
            self.pos += 1
            alternatives.append(self.alternative())
        return alternatives[0] if len(alternatives) == 1 else ("alt", alternatives)

    def alternative(self):
        terms = []
        while self.peek() is not None and self.peek() not in "|)":
            terms.append(self.term())
        return ("seq", terms)

    def term(self):
        node = self.assertion()
        if node is not None:
            if self.peek() in ("*", "+", "?", "{"):
                self.error("quantifier after an assertion")
            return node
        node = self.atom()
        quantifier = self.quantifier()
        if quantifier is None:
            return node
        return ("quant", node) + quantifier

    def assertion(self):
        char = self.peek()
        if char in ("^", "$"):
            self.pos += 1
            return ("assert", char, None)
        if char == "\\" and self.peek(1) in ("b", "B"):
            self.pos += 2
            return ("assert", self.source[self.pos - 1], None)
        for opener, kind in (("(?=", "="), ("(?!", "!"), ("(?<=", "<="), ("(?<!", "<!")):
            if self.startswith(opener):
                self.pos += len(opener)
                body = self.disjunction()
                self.expect(")")
                return ("assert", kind, body)
        return None

    def braced_quantifier(self):
        # Returns (min, max) and advances past "}", or None without a valid form.
        # A bound is converted to int only when it has at most 20 digits.
        start = self.pos
        self.pos += 1
        low = self.digits()
        if not low:
            self.pos = start
            return None
        high = low
        if self.peek() == ",":
            self.pos += 1
            high = self.digits() or None
        if self.peek() != "}":
            self.pos = start
            return None
        self.pos += 1
        return _bound(low), None if high is None else _bound(high)

    def quantifier(self):
        char = self.peek()
        if char == "*":
            self.pos += 1
            bounds = (0, None)
        elif char == "+":
            self.pos += 1
            bounds = (1, None)
        elif char == "?":
            self.pos += 1
            bounds = (0, 1)
        elif char == "{":
            bounds = self.braced_quantifier()
            if bounds is None:
                self.error("'{' does not start a valid quantifier")
            if bounds[1] is not None and _bound_key(bounds[0]) > _bound_key(bounds[1]):
                self.error("quantifier minimum exceeds its maximum")
        else:
            return None
        lazy = self.peek() == "?"
        if lazy:
            self.pos += 1
        return bounds + (lazy,)

    def atom(self):
        char = self.peek()
        if char == ".":
            self.pos += 1
            return ("dot",)
        if char == "\\":
            self.pos += 1
            return self.atom_escape()
        if char == "[":
            return self.character_class()
        if char == "(":
            return self.group()
        if char in _SYNTAX_CHARACTERS:
            self.error(f"unexpected {char!r}")
        self.pos += 1
        return ("char", char)

    def group(self):
        self.pos += 1
        if self.startswith("?:"):
            self.pos += 2
            capturing, name = False, None
        elif self.startswith("?<"):
            self.pos += 2
            name = self.group_name()
            if name in self.group_names:
                self.error(f"duplicate group name {name!r}")
            self.group_names.add(name)
            capturing = True
        elif self.peek() == "?":
            self.error("invalid group specifier")
        else:
            capturing, name = True, None
        if capturing:
            self.group_count += 1
        body = self.disjunction()
        self.expect(")")
        return ("group", capturing, name, body)

    def unicode_escape(self):
        # RegExpUnicodeEscapeSequence[+UnicodeMode] after "\u": a surrogate
        # pair written as two \uXXXX escapes, \uXXXX, or \u{CodePoint}.
        if self.peek() == "{":
            start = self.pos + 1
            end = self.source.find("}", start)
            text = self.source[start:end] if end != -1 else ""
            if not text or not all(char in _HEX_DIGITS for char in text) or int(text, 16) > 0x10FFFF:
                self.error("invalid '\\u{...}' escape in group name")
            self.pos = end + 1
            return chr(int(text, 16))
        char = self.hex_digits(4)
        if char is None:
            self.error("invalid escape in group name")
        if _is_lead(char) and self.startswith("\\u"):
            mark = self.pos
            self.pos += 2
            trail = self.hex_digits(4)
            if _is_trail(trail):
                return _pair(char, trail)
            self.pos = mark
        return char

    def group_name(self):
        # Reads "name>" after the "<" as code points. Escapes use the Unicode
        # mode grammar in every mode; a literal surrogate pair joins.
        chars = []
        while self.peek() not in (">", None):
            char = self.peek()
            self.pos += 1
            if char == "\\":
                if self.peek() != "u":
                    self.error("invalid escape in group name")
                self.pos += 1
                chars.append(self.unicode_escape())
            elif _is_lead(char) and _is_trail(self.peek()):
                chars.append(_pair(char, self.peek()))
                self.pos += 1
            else:
                chars.append(char)
        self.expect(">")
        name = "".join(chars)
        if not _is_group_name(name):
            self.error(f"invalid group name {name!r}")
        return name

    def atom_escape(self):
        char = self.peek()
        if char is None:
            self.error("pattern ends with '\\'")
        if char in _DECIMAL_DIGITS and char != "0":
            text = self.digits()
            if len(text) > _BOUND_DIGITS:
                # No pattern holds that many groups.
                self.error(f"backreference \\{text[:20]}... exceeds the group count")
            number = int(text)
            self.number_refs.append(number)
            return ("backref", number)
        if char in _CLASS_ESCAPES:
            self.pos += 1
            return ("escape", char)
        if char == "k":
            self.pos += 1
            if self.peek() != "<":
                self.error("'\\k' must be followed by a group name")
            self.pos += 1
            name = self.group_name()
            self.name_refs.append(name)
            return ("backref", name)
        return ("char", self.character_escape())

    def character_escape(self):
        # Called with pos on the character after "\"; returns the character.
        char = self.peek()
        self.pos += 1
        if char in _CONTROL_ESCAPES:
            return _CONTROL_ESCAPES[char]
        if char == "c":
            letter = self.peek()
            if letter is None or not ("a" <= letter <= "z" or "A" <= letter <= "Z"):
                self.error("'\\c' must be followed by an ASCII letter")
            self.pos += 1
            return chr(ord(letter) % 32)
        if char == "0":
            if self.peek() in _DECIMAL_DIGITS:
                self.error("'\\0' followed by a digit")
            return "\x00"
        if char in ("x", "u"):
            value = self.hex_digits(2 if char == "x" else 4)
            if value is None:
                self.error(f"invalid '\\{char}' escape")
            return value
        if _is_id_continue(char):
            self.pos -= 1
            self.error(f"invalid identity escape '\\{char}'")
        return char

    def character_class(self):
        self.pos += 1
        negated = self.peek() == "^"
        if negated:
            self.pos += 1
        items = []
        while self.peek() != "]":
            if self.peek() is None:
                self.error("unterminated character class")
            low = self.class_atom()
            if self.peek() == "-" and self.peek(1) not in ("]", None):
                self.pos += 1
                high = self.class_atom()
                if low[0] != "char" or high[0] != "char":
                    self.error("class range with a class escape at one end")
                if low[1] > high[1]:
                    self.error("class range out of order")
                items.append(("range", low[1], high[1]))
            else:
                items.append(low)
        self.pos += 1
        return ("class", negated, items)

    def class_atom(self):
        char = self.peek()
        self.pos += 1
        if char != "\\":
            return ("char", char)
        char = self.peek()
        if char is None:
            self.error("pattern ends with '\\'")
        if char == "b":
            self.pos += 1
            return ("char", "\b")
        if char in _CLASS_ESCAPES:
            self.pos += 1
            return ("escape", char)
        return ("char", self.character_escape())


def _parse(source):
    if not isinstance(source, str):
        raise RegexSyntaxError("pattern source must be a string")
    try:
        return _Parser(_code_units(source)).parse()
    except RecursionError:
        raise RegexResourceLimit("pattern nesting exceeds the parser's resource limit") from None


def is_valid(source: str) -> bool:
    """Return True when ``source`` is a valid ECMA-262 pattern.

    Raises ``RegexResourceLimit`` when the pattern nests too deeply to judge.
    """
    try:
        _parse(source)
    except RegexSyntaxError:
        return False
    return True


# Translation

_PY_MAX_REPEAT = 2**32 - 2
_WHITESPACE = "\t\n\x0b\x0c\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_LINE_TERMINATORS = "\n\r\u2028\u2029"
_POSITIVE_SETS = {"d": [("0", "9")], "w": [("A", "Z"), ("a", "z"), ("0", "9"), ("_", "_")]}
_ANY = "[\\x00-\\U0010ffff]"
_WORD = "A-Za-z0-9_"


def _literal(char):
    # Used for every char and range node. ECMA without the u flag matches
    # 16-bit code units and Python matches code points, so surrogates and
    # characters above U+FFFF would change meaning.
    if char.isascii() and (char.isalnum() or char == "_"):
        return char
    code = ord(char)
    if 0xD800 <= code <= 0xDFFF or code > 0xFFFF:
        raise Untranslatable(f"character U+{code:04X} is a surrogate or above U+FFFF")
    if code < 0x100:
        return f"\\x{code:02x}"
    return f"\\u{code:04x}"


def _escape_body(letter):
    # Bracket body for the positive form of d, s, or w.
    lower = letter.lower()
    if lower == "s":
        return "".join(_literal(c) if c != "-" else "-" for c in _WHITESPACE)
    return "".join(_literal(low) if low == high else f"{_literal(low)}-{_literal(high)}"
                   for low, high in _POSITIVE_SETS[lower])


def _escape_class(letter):
    negation = "^" if letter.isupper() else ""
    return f"[{negation}{_escape_body(letter)}]"


def _class(negated, items):
    body = []
    negated_escapes = []
    for item in items:
        if item[0] == "char":
            body.append(_literal(item[1]))
        elif item[0] == "range":
            body.append(f"{_literal(item[1])}-{_literal(item[2])}")
        elif item[1].isupper():
            negated_escapes.append(_escape_class(item[1]))
        else:
            body.append(_escape_body(item[1]))
    parts = ([f"[{''.join(body)}]"] if body else []) + negated_escapes
    if not negated_escapes:
        if not body:
            return _ANY if negated else "(?!)"
        return f"[^{''.join(body)}]" if negated else parts[0]
    union = parts[0] if len(parts) == 1 else "(?:" + "|".join(parts) + ")"
    return f"(?!{union}){_ANY}" if negated else union


def _emit(node):
    kind = node[0]
    if kind == "char":
        return _literal(node[1])
    if kind == "dot":
        return "[^" + "".join(_literal(c) for c in _LINE_TERMINATORS) + "]"
    if kind == "escape":
        return _escape_class(node[1])
    if kind == "class":
        return _class(node[1], node[2])
    if kind == "seq":
        return "".join(_emit(child) for child in node[1])
    if kind == "alt":
        return "|".join(_emit(child) for child in node[1])
    if kind == "backref":
        raise Untranslatable(f"backreference {node[1]!r} is not translated")
    if kind == "group":
        if node[2] is not None:
            raise Untranslatable(f"named group {node[2]!r} is not translated")
        return ("(" if node[1] else "(?:") + _emit(node[3]) + ")"
    if kind == "assert":
        assertion = node[1]
        if assertion == "^":
            return "\\A"
        if assertion == "$":
            return "\\Z"
        if assertion == "b":
            return f"(?:(?<=[{_WORD}])(?![{_WORD}])|(?<![{_WORD}])(?=[{_WORD}]))"
        if assertion == "B":
            return f"(?:(?<=[{_WORD}])(?=[{_WORD}])|(?<![{_WORD}])(?![{_WORD}]))"
        if assertion in ("<=", "<!"):
            raise Untranslatable("lookbehind assertions are not translated")
        return f"(?{assertion}" + _emit(node[2]) + ")"
    # kind == "quant"
    _, child, low, high, lazy = node
    if isinstance(low, str) or isinstance(high, str):
        raise Untranslatable("quantifier bound exceeds the Python repeat limit")
    if low > _PY_MAX_REPEAT or (high is not None and high > _PY_MAX_REPEAT):
        raise Untranslatable("quantifier bound exceeds the Python repeat limit")
    suffix = f"{{{low},{'' if high is None else high}}}"
    return "(?:" + _emit(child) + ")" + suffix + ("?" if lazy else "")


def to_python(source: str) -> str:
    """Translate a valid ECMA-262 pattern into equivalent Python ``re`` syntax."""
    return _emit(_parse(source))
