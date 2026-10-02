package main

import (
	"bytes"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

// Numeric resource guards. These are operational setup guards, not OASIS
// ranges. They match the Python adapter exactly.
//
//   - Token length: the lexeme exactly as written, including sign, decimal
//     point, and exponent syntax, must be at most 1,024 bytes.
//   - Exponent: the exponent digit text, without its sign and leading zeros,
//     must have at most 5 digits. This is checked before any integer is
//     built from it. The exponent value must then be at most 10,000.
//   - Expansion budget: each token charges every coefficient digit written
//     before the exponent marker (integer and fraction parts, leading zeros
//     included) plus the absolute exponent. The sum over every token in one
//     document must be at most 100,000.
const (
	maxTokenBytes     = 1024
	maxAbsExponent    = 10000
	maxExponentDigits = 5
	maxExpansionUnits = 100000
)

var byteOrderMark = []byte{0xef, 0xbb, 0xbf}

var simpleEscapes = map[byte]byte{
	'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t',
}

// inputInvalidError is a strict parse policy failure. Its message never
// echoes input values.
type inputInvalidError struct{ msg string }

func (e *inputInvalidError) Error() string { return e.msg }

// numericRefusedError is a numeric resource guard refusal. It is a setup
// failure, never input-invalid. Its message names the exceeded limit only.
type numericRefusedError struct{ msg string }

func (e *numericRefusedError) Error() string { return e.msg }

// parseStrict applies the strict transport policy to the original bytes,
// then the numeric guards, and only then decodes with lossless json.Number
// values. Policy failures always take precedence over guard refusals.
func parseStrict(data []byte) (any, error) {
	lexemes, err := strictScan(data)
	if err != nil {
		return nil, err
	}
	if err := guardNumbers(lexemes); err != nil {
		return nil, err
	}
	value, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))
	if err != nil {
		// The strict scan accepted the bytes, so only a decoder limit such as
		// nesting depth can reach this point.
		return nil, &setupError{"the lossless decoder refused a strictly parsed document"}
	}
	return value, nil
}

// strictScan checks the whole document under RFC 8259 with the selected
// policy and returns every number lexeme in document order.
func strictScan(data []byte) ([]string, error) {
	if bytes.HasPrefix(data, byteOrderMark) {
		return nil, &inputInvalidError{"byte-order mark is not permitted"}
	}
	if !utf8.Valid(data) {
		return nil, &inputInvalidError{"input is not valid UTF-8"}
	}
	s := &scanner{data: data}
	if err := s.document(); err != nil {
		return nil, err
	}
	return s.lexemes, nil
}

type container struct {
	object bool
	keys   map[string]struct{}
}

type scanner struct {
	data    []byte
	pos     int
	stack   []container
	lexemes []string
}

func (s *scanner) malformed() error {
	return &inputInvalidError{"malformed JSON at byte offset " + strconv.Itoa(s.pos)}
}

func (s *scanner) skipSpace() {
	for s.pos < len(s.data) {
		switch s.data[s.pos] {
		case ' ', '\t', '\n', '\r':
			s.pos++
		default:
			return
		}
	}
}

func (s *scanner) peek() (byte, bool) {
	if s.pos >= len(s.data) {
		return 0, false
	}
	return s.data[s.pos], true
}

// document scans iteratively with an explicit container stack, so deep
// nesting cannot exhaust the goroutine stack.
func (s *scanner) document() error {
	needValue := true
	for {
		s.skipSpace()
		if needValue {
			c, ok := s.peek()
			if !ok {
				return s.malformed()
			}
			switch {
			case c == '{':
				s.pos++
				s.stack = append(s.stack, container{object: true, keys: map[string]struct{}{}})
				s.skipSpace()
				if c, ok := s.peek(); ok && c == '}' {
					s.pos++
					s.stack = s.stack[:len(s.stack)-1]
					needValue = false
					continue
				}
				if err := s.member(); err != nil {
					return err
				}
				continue
			case c == '[':
				s.pos++
				s.stack = append(s.stack, container{})
				s.skipSpace()
				if c, ok := s.peek(); ok && c == ']' {
					s.pos++
					s.stack = s.stack[:len(s.stack)-1]
					needValue = false
				}
				continue
			case c == '"':
				if _, err := s.str(); err != nil {
					return err
				}
			case c == '-' || (c >= '0' && c <= '9'):
				if err := s.number(); err != nil {
					return err
				}
			case c == 't':
				if err := s.literal("true"); err != nil {
					return err
				}
			case c == 'f':
				if err := s.literal("false"); err != nil {
					return err
				}
			case c == 'n':
				if err := s.literal("null"); err != nil {
					return err
				}
			default:
				return s.malformed()
			}
			needValue = false
			continue
		}
		if len(s.stack) == 0 {
			if s.pos != len(s.data) {
				return s.malformed()
			}
			return nil
		}
		c, ok := s.peek()
		if !ok {
			return s.malformed()
		}
		top := s.stack[len(s.stack)-1]
		switch {
		case c == ',':
			s.pos++
			needValue = true
			if top.object {
				s.skipSpace()
				if err := s.member(); err != nil {
					return err
				}
			}
		case top.object && c == '}', !top.object && c == ']':
			s.pos++
			s.stack = s.stack[:len(s.stack)-1]
		default:
			return s.malformed()
		}
	}
}

// member reads an object member name and its colon. The value follows.
func (s *scanner) member() error {
	if c, ok := s.peek(); !ok || c != '"' {
		return s.malformed()
	}
	key, err := s.str()
	if err != nil {
		return err
	}
	keys := s.stack[len(s.stack)-1].keys
	if _, seen := keys[key]; seen {
		return &inputInvalidError{"duplicate object member name"}
	}
	keys[key] = struct{}{}
	s.skipSpace()
	if c, ok := s.peek(); !ok || c != ':' {
		return s.malformed()
	}
	s.pos++
	return nil
}

func (s *scanner) literal(word string) error {
	if !bytes.HasPrefix(s.data[s.pos:], []byte(word)) {
		return s.malformed()
	}
	s.pos += len(word)
	return nil
}

func isDigit(c byte) bool { return c >= '0' && c <= '9' }

func (s *scanner) digits() int {
	start := s.pos
	for s.pos < len(s.data) && isDigit(s.data[s.pos]) {
		s.pos++
	}
	return s.pos - start
}

// number accepts -?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)? and keeps
// the lexeme text. A following character is checked by the caller.
func (s *scanner) number() error {
	start := s.pos
	if s.data[s.pos] == '-' {
		s.pos++
	}
	c, ok := s.peek()
	switch {
	case !ok:
		return s.malformed()
	case c == '0':
		s.pos++
	case c >= '1' && c <= '9':
		s.digits()
	default:
		return s.malformed()
	}
	if c, ok := s.peek(); ok && c == '.' {
		s.pos++
		if s.digits() == 0 {
			return s.malformed()
		}
	}
	if c, ok := s.peek(); ok && (c == 'e' || c == 'E') {
		s.pos++
		if c, ok := s.peek(); ok && (c == '+' || c == '-') {
			s.pos++
		}
		if s.digits() == 0 {
			return s.malformed()
		}
	}
	s.lexemes = append(s.lexemes, string(s.data[start:s.pos]))
	return nil
}

func hexValue(b []byte) (rune, bool) {
	var r rune
	for _, c := range b {
		r <<= 4
		switch {
		case c >= '0' && c <= '9':
			r |= rune(c - '0')
		case c >= 'a' && c <= 'f':
			r |= rune(c-'a') + 10
		case c >= 'A' && c <= 'F':
			r |= rune(c-'A') + 10
		default:
			return 0, false
		}
	}
	return r, true
}

func (s *scanner) unicodeEscape() (rune, bool) {
	// s.pos is at the 'u' after a backslash.
	if s.pos+5 > len(s.data) {
		return 0, false
	}
	r, ok := hexValue(s.data[s.pos+1 : s.pos+5])
	if !ok {
		return 0, false
	}
	s.pos += 5
	return r, true
}

// str reads a string token and returns its decoded value. It rejects
// control characters, invalid escapes, and unpaired surrogate escapes.
func (s *scanner) str() (string, error) {
	s.pos++ // opening quote
	var out strings.Builder
	for {
		c, ok := s.peek()
		if !ok {
			return "", s.malformed()
		}
		switch {
		case c == '"':
			s.pos++
			return out.String(), nil
		case c < 0x20:
			return "", s.malformed()
		case c == '\\':
			s.pos++
			e, ok := s.peek()
			if !ok {
				return "", s.malformed()
			}
			if v, isSimple := simpleEscapes[e]; isSimple {
				out.WriteByte(v)
				s.pos++
				continue
			}
			if e != 'u' {
				return "", s.malformed()
			}
			r, ok := s.unicodeEscape()
			if !ok {
				return "", s.malformed()
			}
			switch {
			case r >= 0xDC00 && r <= 0xDFFF:
				return "", &inputInvalidError{"string contains an unpaired surrogate escape"}
			case r >= 0xD800 && r <= 0xDBFF:
				if !bytes.HasPrefix(s.data[s.pos:], []byte(`\u`)) {
					return "", &inputInvalidError{"string contains an unpaired surrogate escape"}
				}
				s.pos++
				low, ok := s.unicodeEscape()
				if !ok {
					return "", s.malformed()
				}
				if low < 0xDC00 || low > 0xDFFF {
					return "", &inputInvalidError{"string contains an unpaired surrogate escape"}
				}
				r = 0x10000 + (r-0xD800)<<10 + (low - 0xDC00)
			}
			out.WriteRune(r)
		default:
			// The whole input is valid UTF-8, so copy the encoded character.
			_, size := utf8.DecodeRune(s.data[s.pos:])
			out.Write(s.data[s.pos : s.pos+size])
			s.pos += size
		}
	}
}

// guardNumbers applies the numeric resource guards in document order.
func guardNumbers(lexemes []string) error {
	total := 0
	for _, text := range lexemes {
		charge, err := numberCharge(text)
		if err != nil {
			return err
		}
		total += charge
		if total > maxExpansionUnits {
			return &numericRefusedError{"numeric expansion budget exceeds " + strconv.Itoa(maxExpansionUnits) + " digit units per document"}
		}
	}
	return nil
}

func significantExponentDigits(text string) string {
	return strings.TrimLeft(strings.TrimLeft(text, "+-"), "0")
}

// exponentTooLong reports whether exponent text has more significant digits
// than any permitted exponent. It never converts the text to an integer.
func exponentTooLong(text string) bool {
	return len(significantExponentDigits(text)) > maxExponentDigits
}

// convertExponent builds an integer from exponent digits. Tests replace it
// to prove that oversized exponent text never reaches conversion.
var convertExponent = strconv.Atoi

func numberCharge(text string) (int, error) {
	if len(text) > maxTokenBytes {
		return 0, &numericRefusedError{"numeric token length exceeds " + strconv.Itoa(maxTokenBytes) + " bytes"}
	}
	coefficient, exponent := text, 0
	if marker := strings.IndexAny(text, "eE"); marker >= 0 {
		coefficient = text[:marker]
		exponentText := text[marker+1:]
		exponentRefused := &numericRefusedError{"absolute decimal exponent exceeds " + strconv.Itoa(maxAbsExponent)}
		if exponentTooLong(exponentText) {
			return 0, exponentRefused
		}
		if digits := significantExponentDigits(exponentText); digits != "" {
			value, err := convertExponent(digits) // at most 5 ASCII digits
			if err != nil {
				return 0, exponentRefused
			}
			exponent = value
		}
		if exponent > maxAbsExponent {
			return 0, exponentRefused
		}
	}
	count := 0
	for i := 0; i < len(coefficient); i++ {
		if isDigit(coefficient[i]) {
			count++
		}
	}
	return count + exponent, nil
}
