package main

import (
	"encoding/json"
	"testing"
)

func TestDateTimeGrammarAccepts(t *testing.T) {
	for _, value := range []string{
		"2024-02-29T00:00:00Z",
		"2000-02-29T23:59:59z",
		"0001-01-01t00:00:00Z",
		"9999-12-31T23:59:59.9+23:59",
		"2026-09-29T12:00:00-00:00",
		"2026-09-29T12:00:00.000000000000001Z",
	} {
		if err := checkDateTime(value); err != nil {
			t.Errorf("%q rejected", value)
		}
	}
}

func TestDateTimeGrammarRejects(t *testing.T) {
	for _, value := range []string{
		"2023-02-29T00:00:00Z",
		"1900-02-29T00:00:00Z",
		"0000-01-01T00:00:00Z",
		"2026-13-01T00:00:00Z",
		"2026-00-01T00:00:00Z",
		"2026-04-31T00:00:00Z",
		"2026-01-00T00:00:00Z",
		"2026-09-29T24:00:00Z",
		"2026-09-29T12:60:00Z",
		"2026-09-29T12:00:60Z",
		"2026-09-29T12:00:00.Z",
		"2026-09-29T12:00:00+24:00",
		"2026-09-29T12:00:00+01:60",
		"2026-09-29T12:00:00",
		"2026-09-29T12:00:00+01",
		"2026-09-29T12:00:00+0100",
		"2026-09-29 12:00:00Z",
		"2026-09-29T12:00:00Z\n",
		"\n2026-09-29T12:00:00Z",
		"20260-09-29T12:00:00Z",
		"2026-09-29T12:00Z",
		"２026-09-29T12:00:00Z",
		"2026-09-29T12:00:00.١Z",
		"",
	} {
		if err := checkDateTime(value); err == nil {
			t.Errorf("%q accepted", value)
		}
	}
}

func TestDateTimeIgnoresNonStrings(t *testing.T) {
	for _, value := range []any{json.Number("5"), true, nil, []any{}, map[string]any{}} {
		if err := checkDateTime(value); err != nil {
			t.Errorf("%#v rejected", value)
		}
	}
}
