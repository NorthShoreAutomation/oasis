package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

func assertInputInvalid(t *testing.T, data []byte) {
	t.Helper()
	_, err := parseStrict(data)
	var invalid *inputInvalidError
	if !errors.As(err, &invalid) {
		t.Fatalf("want input-invalid, got %v", err)
	}
}

func assertRefused(t *testing.T, data []byte, limit string) {
	t.Helper()
	_, err := parseStrict(data)
	var refused *numericRefusedError
	if !errors.As(err, &refused) {
		t.Fatalf("want numeric refusal, got %v", err)
	}
	if !strings.Contains(refused.Error(), limit) {
		t.Fatalf("refusal %q does not name limit %q", refused.Error(), limit)
	}
}

func mustParse(t *testing.T, data []byte) any {
	t.Helper()
	value, err := parseStrict(data)
	if err != nil {
		t.Fatalf("parse failed: %v", err)
	}
	return value
}

func TestStrictPolicyRejects(t *testing.T) {
	cases := map[string]string{
		"duplicate":                  `{"a": 1, "a": 2}`,
		"duplicate after escape":     `{"a": 1, "\u0061": 2}`,
		"nested duplicate":           `{"x": [{"b": true, "b": false}]}`,
		"byte order mark":            "\xef\xbb\xbf{\"a\": 1}",
		"invalid utf-8":              "{\"a\": \"\xff\"}",
		"encoded surrogate bytes":    "{\"a\": \"\xed\xa0\x80\"}",
		"NaN":                        `{"a": NaN}`,
		"Infinity":                   `{"a": Infinity}`,
		"negative Infinity":          `{"a": -Infinity}`,
		"empty":                      ``,
		"whitespace only":            " \n",
		"unclosed object":            `{`,
		"trailing comma":             `{"a": 1,}`,
		"missing comma":              `[1 2]`,
		"leading zero":               `{"a": 01}`,
		"plus sign":                  `+1`,
		"bare fraction":              `.5`,
		"empty fraction":             `1.`,
		"empty exponent":             `1e`,
		"single quotes":              `{'a': 1}`,
		"control character":          "\"a\tb\"",
		"bad escape":                 `"\x"`,
		"short unicode escape":       `"\u12"`,
		"trailing content":           `{} {}`,
		"unpaired high in key":       `{"\ud800": 1}`,
		"unpaired low in value":      `{"a": ["ok", "\udc00"]}`,
		"reversed pair":              `"\ude00\ud83d"`,
		"high then plain char":       `"\ud800A"`,
		"high then escaped non-low":  `"\ud800\u0041"`,
		"high then high":             `"\ud800\ud800"`,
		"high at end":                `"\ud800"`,
		"literal true misspelled":    `tru`,
		"non-string key":             `{1: 2}`,
		"non-ASCII digit":            "[١]",
		"form feed is not space":     "\f1",
		"non-breaking space":         " 1",
		"closing bracket mismatch":   `[1}`,
		"extra closing bracket":      `[1]]`,
		"colon without member value": `{"a":}`,
	}
	for name, text := range cases {
		t.Run(name, func(t *testing.T) { assertInputInvalid(t, []byte(text)) })
	}
}

func TestStrictAcceptsValidPair(t *testing.T) {
	value := mustParse(t, []byte(`{"\ud83d\ude00": "\ud83d\ude00"}`))
	want := map[string]any{"\U0001F600": "\U0001F600"}
	if got, _ := json.Marshal(value); !bytes.Equal(got, mustMarshal(t, want)) {
		t.Fatalf("got %s", got)
	}
}

func TestStrictAcceptsScalarsAndWhitespace(t *testing.T) {
	for _, text := range []string{"true", "false", "null", `"s"`, "-0", "0.5e-3", " \t\r\n[ ]\n", "{}"} {
		mustParse(t, []byte(text))
	}
}

func TestStrictMessageDoesNotEchoInput(t *testing.T) {
	secret := "SECRETVALUE123"
	_, err := parseStrict([]byte(`{"` + secret + `": 1, "` + secret + `": 2}`))
	if err == nil || strings.Contains(err.Error(), secret) {
		t.Fatalf("error %v echoes input", err)
	}
}

func TestNumbersStayLossless(t *testing.T) {
	value := mustParse(t, []byte(`[23.976, 29.97, 59.94, 9007199254740993, 9007199254740992, 1.0]`))
	list := value.([]any)
	want := []string{"23.976", "29.97", "59.94", "9007199254740993", "9007199254740992", "1.0"}
	for i, item := range list {
		number, ok := item.(json.Number)
		if !ok || string(number) != want[i] {
			t.Fatalf("item %d: got %#v", i, item)
		}
	}
}

func TestGuardFiveThousandDigitInteger(t *testing.T) {
	assertRefused(t, []byte("["+strings.Repeat("9", 5000)+"]"), "1024")
}

func TestMalformedInputWithHugeNumberIsInputInvalid(t *testing.T) {
	huge := strings.Repeat("9", 5000)
	for _, text := range []string{
		"[" + huge + ",]",
		`{"a": ` + huge + `, "a": 1}`,
		`["\ud800", ` + huge + `]`,
		`["\ud800", 1e99999999999999999999]`,
		"\xef\xbb\xbf" + huge,
		huge + "\xff",
	} {
		assertInputInvalid(t, []byte(text))
	}
}

func TestGuardTokenLengthBoundary(t *testing.T) {
	mustParse(t, []byte(strings.Repeat("1", 1024)))
	assertRefused(t, []byte(strings.Repeat("1", 1025)), "1024")
}

func TestGuardTokenLengthCountsSignAndExponent(t *testing.T) {
	accepted := "-" + strings.Repeat("1", 1020) + "e+0"
	if len(accepted) != 1024 {
		t.Fatal("bad fixture length")
	}
	mustParse(t, []byte(accepted))
	assertRefused(t, []byte("-"+strings.Repeat("1", 1021)+"e+0"), "1024")
}

func TestGuardExponentBoundary(t *testing.T) {
	mustParse(t, []byte("1e10000"))
	mustParse(t, []byte("1e-10000"))
	mustParse(t, []byte("1e0000010000"))
	for _, text := range []string{"1e10001", "1E-10001", "1e+10001", "1e99999"} {
		assertRefused(t, []byte(text), "10000")
	}
}

func TestGuardLongExponentRefusedBeforeConversion(t *testing.T) {
	exponent := strings.Repeat("9", 20)
	var converted []string
	original := convertExponent
	t.Cleanup(func() { convertExponent = original })
	convertExponent = func(text string) (int, error) {
		converted = append(converted, text)
		return original(text)
	}
	_, err := parseStrict([]byte("1e" + exponent))
	if len(converted) != 0 {
		t.Fatalf("exponent text was converted: %d calls", len(converted))
	}
	var refused *numericRefusedError
	if !errors.As(err, &refused) || !strings.Contains(err.Error(), "exponent") {
		t.Fatalf("want exponent refusal, got %v", err)
	}
	if strings.Contains(err.Error(), exponent) {
		t.Fatal("refusal echoes the exponent")
	}
	// Six significant exponent digits are refused by digit count alone.
	if exponentTooLong("+0100000") != true || exponentTooLong("-000010000") != false {
		t.Fatal("exponent digit count check is wrong")
	}
}

func TestGuardBudgetBoundary(t *testing.T) {
	ten := "[" + strings.TrimSuffix(strings.Repeat("1e9999,", 10), ",") + "]"
	mustParse(t, []byte(ten))
	assertRefused(t, []byte(strings.TrimSuffix(ten, "]")+",0]"), "100000")
}

func TestGuardBudgetCountsFractionAndLeadingZeros(t *testing.T) {
	tokens := strings.Repeat("0.5e9997,", 10) + "0.00000000"
	mustParse(t, []byte("["+tokens+"]"))
	assertRefused(t, []byte("["+tokens+",10]"), "100000")
}

func TestGuardBudgetCountsObjectMembers(t *testing.T) {
	var members []string
	for i := 0; i < 10; i++ {
		members = append(members, `"k`+string(rune('0'+i))+`": 1e9999`)
	}
	body := strings.Join(members, ",")
	mustParse(t, []byte("{"+body+"}"))
	assertRefused(t, []byte("{"+body+`, "z": 1}`), "100000")
}

func mustMarshal(t *testing.T, value any) []byte {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return data
}
