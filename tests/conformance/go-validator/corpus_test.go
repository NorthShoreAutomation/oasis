package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type engineExpectation struct {
	Required      *bool   `json:"required"`
	Historical    *bool   `json:"historical-unchecked"`
	AdapterStatus string  `json:"adapter_status"`
	Limitation    *string `json:"limitation"`
}

type corpusCase struct {
	ID                   string                       `json:"id"`
	SchemaName           string                       `json:"schema_name"`
	Path                 string                       `json:"path"`
	ValidatorExpectation map[string]engineExpectation `json:"validator_expectations"`
}

// TestCorpus runs every manifest case against both bundle roots in both
// format modes and compares with the go-jsonschema expectations.
func TestCorpus(t *testing.T) {
	data, err := os.ReadFile(filepath.Join(fixturesRoot, "manifest.json"))
	if err != nil {
		t.Fatal(err)
	}
	var manifest struct {
		Cases []corpusCase `json:"cases"`
	}
	if err := json.Unmarshal(data, &manifest); err != nil {
		t.Fatal(err)
	}
	if len(manifest.Cases) != 145 {
		t.Fatalf("corpus has %d cases, want 145", len(manifest.Cases))
	}
	roots := map[string]string{"baseline": frozenRoot, "current": currentRoot}
	adapters := map[string]*adapter{}
	for rootName, root := range roots {
		for _, mode := range formatModes {
			a, err := newAdapter(root, mode)
			if err != nil {
				t.Fatalf("%s %s: setup failed: %v", rootName, mode, err)
			}
			adapters[rootName+" "+mode] = a
		}
	}

	var mismatches []string
	runs := 0
	for _, c := range manifest.Cases {
		expected, ok := c.ValidatorExpectation["go-jsonschema"]
		if !ok {
			mismatches = append(mismatches, c.ID+": no go-jsonschema expectation")
			continue
		}
		input, err := os.ReadFile(filepath.Join(fixturesRoot, c.Path))
		if err != nil {
			mismatches = append(mismatches, c.ID+": input cannot be read")
			continue
		}
		for _, rootName := range []string{"baseline", "current"} {
			for _, mode := range formatModes {
				runs++
				result := adapters[rootName+" "+mode].run(c.SchemaName, input)
				if problem := compareExpectation(expected, mode, result); problem != "" {
					mismatches = append(mismatches, fmt.Sprintf("%s %s %s: %s", c.ID, rootName, mode, problem))
				}
			}
		}
	}
	t.Logf("corpus: %d cases, %d runs, %d mismatches", len(manifest.Cases), runs, len(mismatches))
	if len(mismatches) > 0 {
		t.Fatalf("%d corpus mismatches:\n%s", len(mismatches), strings.Join(mismatches, "\n"))
	}
}

func compareExpectation(expected engineExpectation, mode string, result Result) string {
	if expected.AdapterStatus != statusComplete {
		if result.AdapterStatus != expected.AdapterStatus {
			return fmt.Sprintf("adapter_status %s, want %s", result.AdapterStatus, expected.AdapterStatus)
		}
		return ""
	}
	want := expected.Required
	if mode == modeHistorical {
		want = expected.Historical
	}
	if result.AdapterStatus != statusComplete {
		return fmt.Sprintf("adapter_status %s, want complete", result.AdapterStatus)
	}
	if want == nil {
		return "complete expectation has no structural value for this mode"
	}
	if (result.Structural == structuralValid) != *want {
		return fmt.Sprintf("structural %s, want valid=%v", result.Structural, *want)
	}
	return ""
}
