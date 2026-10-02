package main

import (
	"bytes"
	"encoding/json"
	"testing"
)

func TestCLIPrintsOneResult(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := runCLI([]string{
		"--bundle", currentRoot, "--schema", "asset.schema.json",
		"--format-mode", "required", "--input", fixturesRoot + "/records/minimal-asset.json",
	}, &stdout, &stderr)
	if code != 0 {
		t.Fatalf("exit %d: %s", code, stderr.String())
	}
	var result map[string]any
	if err := json.Unmarshal(stdout.Bytes(), &result); err != nil {
		t.Fatalf("output is not one JSON object: %v", err)
	}
	if result["adapter_status"] != "complete" || result["structural"] != "valid" {
		t.Fatalf("got %v", result)
	}
}

func TestCLIExitsZeroForSetupFailure(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := runCLI([]string{
		"--bundle", t.TempDir(), "--schema", "x", "--format-mode", "historical-unchecked", "--input", "missing.json",
	}, &stdout, &stderr)
	var result Result
	if code != 0 || json.Unmarshal(stdout.Bytes(), &result) != nil || result.AdapterStatus != statusSetupFailed {
		t.Fatalf("exit %d, output %q", code, stdout.String())
	}
}

func TestCLIUsageErrors(t *testing.T) {
	full := []string{"--bundle", currentRoot, "--schema", "asset.schema.json", "--format-mode", "required", "--input", "x.json"}
	for name, args := range map[string][]string{
		"no arguments":   {},
		"missing input":  full[:6],
		"missing bundle": full[2:],
		"bad mode":       {"--bundle", "b", "--schema", "s", "--format-mode", "lenient", "--input", "i"},
		"unknown flag":   append([]string{"--color"}, full...),
		"positional":     append(append([]string{}, full...), "extra"),
		"empty value":    {"--bundle", "", "--schema", "s", "--format-mode", "required", "--input", "i"},
	} {
		t.Run(name, func(t *testing.T) {
			var stdout, stderr bytes.Buffer
			if code := runCLI(args, &stdout, &stderr); code == 0 {
				t.Fatal("usage error exited 0")
			}
			if stdout.Len() != 0 {
				t.Fatal("usage error printed a result")
			}
		})
	}
}
