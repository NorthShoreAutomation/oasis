package main

import (
	"encoding/json"
	"errors"
	"os"
	"reflect"
	"strings"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

func TestResultJSONFieldsExactly(t *testing.T) {
	result := validateBytes(currentRoot, "asset.schema.json", modeRequired, record(t, "minimal-asset.json"))
	data, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]any
	json.Unmarshal(data, &fields)
	want := map[string]any{"adapter_status": "complete", "structural": "valid", "limitation": nil, "errors": []any{}}
	if !reflect.DeepEqual(fields, want) {
		t.Fatalf("got %s", data)
	}
}

func TestInvalidResultListsPointersWithoutMessages(t *testing.T) {
	result := validateBytes(currentRoot, "asset.schema.json", modeRequired, record(t, "missing-required-asset.json"))
	assertComplete(t, result, false)
	if len(result.Errors) == 0 {
		t.Fatal("invalid result has no error locations")
	}
	data, _ := json.Marshal(result)
	if strings.Contains(string(data), "missing propert") || strings.Contains(string(data), "required") {
		t.Fatalf("result copies library message text: %s", data)
	}
}

func TestErrorLocationsAreEscapedPointers(t *testing.T) {
	root := makeBundle(t, map[string]string{"t.schema.json": `{"properties": {"a/b~c": {"type": "string"}, "l": {"items": {"type": "string"}}}}`})
	result := validateBytes(root, "t.schema.json", modeRequired, []byte(`{"a/b~c": 1, "l": ["x", 2]}`))
	assertComplete(t, result, false)
	want := []string{"/a~1b~0c", "/l/1"}
	if !reflect.DeepEqual(result.Errors, want) {
		t.Fatalf("got %v", result.Errors)
	}
	result = validateBytes(root, "t.schema.json", modeRequired, []byte(`"SECRET"`))
	if result.Structural != structuralValid {
		t.Fatalf("got %+v", result)
	}
}

func TestInputInvalidResult(t *testing.T) {
	result := validateBytes(currentRoot, "asset.schema.json", modeRequired, []byte(`{"asset_id": "SECRET", "asset_id": "SECRET"}`))
	if result.AdapterStatus != statusInputInvalid || result.Structural != structuralNotRun || len(result.Errors) != 0 {
		t.Fatalf("got %+v", result)
	}
	data, _ := json.Marshal(result)
	if strings.Contains(string(data), "SECRET") {
		t.Fatal("result echoes input")
	}
}

func TestNumericRefusalResultNamesAllLimits(t *testing.T) {
	secret := strings.Repeat("7", 1100)
	result := validateBytes(currentRoot, "temporal_annotation.schema.json", modeRequired,
		[]byte(`{"source_id": "a", "start_frame": `+secret+`}`))
	assertSetupFailed(t, result)
	text := *result.Limitation
	for _, part := range []string{"1,024", "10,000", "100,000", "Exceeded limit: numeric token length exceeds 1024 bytes"} {
		if !strings.Contains(text, part) {
			t.Fatalf("limitation %q lacks %q", text, part)
		}
	}
	if strings.Contains(text, "7777") {
		t.Fatal("limitation echoes input")
	}
}

func TestInputInvalidOutranksNumericRefusal(t *testing.T) {
	huge := strings.Repeat("9", 5000)
	result := validateBytes(currentRoot, "asset.schema.json", modeRequired, []byte(`{"a": `+huge+`, "a": 1}`))
	if result.AdapterStatus != statusInputInvalid {
		t.Fatalf("got %+v", result)
	}
	assertSetupFailed(t, validateBytes(currentRoot, "asset.schema.json", modeRequired, []byte(`{"a": `+huge+`}`)))
}

func TestDecoderNestingLimitIsSetupFailure(t *testing.T) {
	nested := func(depth int) []byte {
		return []byte(strings.Repeat("[", depth) + strings.Repeat("]", depth))
	}
	root := makeBundle(t, map[string]string{"t.schema.json": `{}`})
	assertComplete(t, validateBytes(root, "t.schema.json", modeRequired, nested(10000)), true)
	for _, depth := range []int{10001, 100000} {
		result := validateBytes(root, "t.schema.json", modeRequired, nested(depth))
		assertSetupFailed(t, result)
		if *result.Limitation != "Setup failed: the lossless decoder refused a strictly parsed document." {
			t.Fatalf("depth %d: unexpected limitation %q", depth, *result.Limitation)
		}
	}
}

func TestHistoricalModeDisablesDateTimeOnly(t *testing.T) {
	root := makeBundle(t, map[string]string{"t.schema.json": `{"properties": {"d": {"type": "string", "format": "date-time"}, "tc": {"pattern": "^x_"}}}`})
	bad := []byte(`{"d": "2026-09-29 12:00:00Z"}`)
	assertComplete(t, validateBytes(root, "t.schema.json", modeRequired, bad), false)
	result := validateBytes(root, "t.schema.json", modeHistorical, bad)
	assertComplete(t, result, true)
	if result.Limitation == nil || !strings.Contains(*result.Limitation, "historical-unchecked") {
		t.Fatalf("historical result is not labelled: %+v", result)
	}
	// Pattern assertions still apply in historical mode.
	assertComplete(t, validateBytes(root, "t.schema.json", modeHistorical, []byte(`{"tc": "y_"}`)), false)
}

func TestDateTimeAppliesThroughReferences(t *testing.T) {
	text := `{"assets": [{"asset_id": "a", "title": "t", "type": "video", "created_date": "bad"}]}`
	assertComplete(t, validateBytes(currentRoot, "asset_batch_import.schema.json", modeRequired, []byte(text)), false)
	assertComplete(t, validateBytes(currentRoot, "asset_batch_import.schema.json", modeHistorical, []byte(text)), true)
}

func TestNonStringPassesDateTimeFormat(t *testing.T) {
	root := makeBundle(t, map[string]string{"t.schema.json": `{"type": ["string", "number"], "format": "date-time"}`})
	assertComplete(t, validateBytes(root, "t.schema.json", modeRequired, []byte("5")), true)
	assertComplete(t, validateBytes(root, "t.schema.json", modeRequired, []byte(`"x"`)), false)
}

func TestUnknownModeIsRefused(t *testing.T) {
	if _, err := newAdapter(currentRoot, "lenient"); err == nil {
		t.Fatal("unknown mode accepted")
	}
}

func annotation(t *testing.T, mode, fields string) Result {
	t.Helper()
	text := `{"source_id": "a", "is_point_marker": true, ` + fields + `}`
	return validateBytes(currentRoot, "temporal_annotation.schema.json", mode, []byte(text))
}

func TestTimecodePatternASCIIDigitsAndAbsoluteEnd(t *testing.T) {
	for _, mode := range formatModes {
		for _, good := range []string{"01:00:00", "1:00:00", "01:00:00:12", "01:00:00'12", "01:00:00.12"} {
			assertComplete(t, annotation(t, mode, `"start_timecode": `+quote(good)), true)
		}
		for _, bad := range []string{"01:00:00\n", "١:00:00", "01:00:0٠", "01:00:00:123", "x01:00:00", "０１:00:00"} {
			assertComplete(t, annotation(t, mode, `"start_timecode": `+quote(bad)), false)
		}
	}
}

func report(t *testing.T, changes map[string]any) []byte {
	t.Helper()
	var data map[string]any
	if err := json.Unmarshal(record(t, "minimal-migration-report-output.json"), &data); err != nil {
		t.Fatal(err)
	}
	for k, v := range changes {
		data[k] = v
	}
	out, _ := json.Marshal(data)
	return out
}

func TestReportPatternsASCIIDigitsAndAbsoluteEnd(t *testing.T) {
	name := "migration-report-output.schema.json"
	for _, root := range []string{frozenRoot, currentRoot} {
		for _, mode := range formatModes {
			assertComplete(t, validateBytes(root, name, mode, report(t, nil)), true)
			for _, changes := range []map[string]any{
				{"report_id": "20260929_120000\n"},
				{"report_id": "2026092٩_120000"},
				{"report_version": "1.0.0\n"},
				{"report_version": "1.٠.0"},
				{"extensions": map[string]any{"y_a": 1}},
				{"extensions": map[string]any{"\nx_a": 1}},
			} {
				assertComplete(t, validateBytes(root, name, mode, report(t, changes)), false)
			}
			assertComplete(t, validateBytes(root, name, mode, report(t, map[string]any{"extensions": map[string]any{"x_a": 1}})), true)
		}
	}
}

func TestPatternEngineIsASCIIAndAbsoluteEnd(t *testing.T) {
	if len(allowedPatterns) != 4 {
		t.Fatalf("allowlist has %d expressions", len(allowedPatterns))
	}
	for _, expression := range allowedPatterns {
		if _, err := compileAllowedPattern(expression); err != nil {
			t.Fatalf("%q: %v", expression, err)
		}
	}
	checks := []struct {
		expression, text string
		match            bool
	}{
		{`^\d+\.\d+\.\d+$`, "10.20.30", true},
		{`^\d+\.\d+\.\d+$`, "1.0.0\n", false},
		{`^\d+\.\d+\.\d+$`, "1.٠.0", false},
		{`^\d{8}_\d{6}$`, "20260929_120000", true},
		{`^\d{8}_\d{6}$`, "20260929_120000\n", false},
		{`^\d{8}_\d{6}$`, "2026092９_120000", false},
		{`^\d{1,2}:\d{2}:\d{2}[:'\.]?\d{0,2}$`, "1:00:00'12", true},
		{`^\d{1,2}:\d{2}:\d{2}[:'\.]?\d{0,2}$`, "01:00:00\n", false},
		{"^x_", "x_a", true},
		{"^x_", "\nx_a", false},
	}
	for _, c := range checks {
		re, _ := compileAllowedPattern(c.expression)
		if re.MatchString(c.text) != c.match {
			t.Errorf("%q on %q: want %v", c.expression, c.text, c.match)
		}
	}
	if _, err := compileAllowedPattern("^a$"); err == nil {
		t.Fatal("unlisted expression compiled")
	}
}

func TestExactNumbers(t *testing.T) {
	// Binary64 would round -1E-400 to -0.0, which passes minimum 0.
	assertComplete(t, annotation(t, modeRequired, `"start_seconds": -1E-400`), false)
	assertComplete(t, annotation(t, modeRequired, `"start_seconds": 0E-400`), true)
	assertComplete(t, annotation(t, modeRequired, `"start_seconds": -0`), true)
	for _, v := range []string{"23.976", "29.97", "59.94", "1E+400"} {
		assertComplete(t, annotation(t, modeRequired, `"start_seconds": 0, "frame_rate": `+v), true)
	}
	for _, v := range []string{"9007199254740993", "123456789012345678901234567890", "1.0", "1E+3", "2.50E+1"} {
		assertComplete(t, annotation(t, modeRequired, `"start_frame": `+v), true)
	}
	for _, v := range []string{"1.5", "1E-1", "9007199254740993.5", "true", "-1"} {
		assertComplete(t, annotation(t, modeRequired, `"start_frame": `+v), false)
	}
}

func TestDecimalBoundAgainstLargeIntegers(t *testing.T) {
	root := makeBundle(t, map[string]string{"t.schema.json": `{"minimum": 9007199254740992.5, "maximum": 9007199254740993}`})
	assertComplete(t, validateBytes(root, "t.schema.json", modeRequired, []byte("9007199254740993")), true)
	assertComplete(t, validateBytes(root, "t.schema.json", modeRequired, []byte("9007199254740992")), false)
	assertComplete(t, validateBytes(root, "t.schema.json", modeRequired, []byte("9007199254740993.0000000000000001")), false)
	assertComplete(t, validateBytes(root, "t.schema.json", modeRequired, []byte("9007199254740994")), false)
}

func TestEnumConstAndRateEquality(t *testing.T) {
	root := makeBundle(t, map[string]string{
		"e.schema.json": `{"enum": [1, false, 2.5, 29.97]}`,
		"c.schema.json": `{"const": 9007199254740993}`,
	})
	for _, good := range []string{"1", "1.0", "1E0", "false", "2.50", "25E-1", "29.97", "2997E-2"} {
		assertComplete(t, validateBytes(root, "e.schema.json", modeRequired, []byte(good)), true)
	}
	for _, bad := range []string{"true", "0", "0.0", "1.0000000000000000000001", `"1"`, "29.970000000000001", "29.969999999999999"} {
		assertComplete(t, validateBytes(root, "e.schema.json", modeRequired, []byte(bad)), false)
	}
	assertComplete(t, validateBytes(root, "c.schema.json", modeRequired, []byte("9007199254740993")), true)
	assertComplete(t, validateBytes(root, "c.schema.json", modeRequired, []byte("9007199254740992")), false)
	assertComplete(t, validateBytes(root, "c.schema.json", modeRequired, []byte("9007199254740994")), false)
}

func TestLibraryPanicBecomesSetupFailure(t *testing.T) {
	original := validateInstance
	t.Cleanup(func() { validateInstance = original })
	validateInstance = func(_ *jsonschema.Schema, value any) error {
		panic(value)
	}
	result := validateBytes(currentRoot, "asset.schema.json", modeRequired, []byte(`{"asset_id": "SECRET"}`))
	assertSetupFailed(t, result)
	if strings.Contains(*result.Limitation, "SECRET") {
		t.Fatal("panic message echoes input")
	}
}

func TestNonValidationErrorBecomesSetupFailure(t *testing.T) {
	original := validateInstance
	t.Cleanup(func() { validateInstance = original })
	validateInstance = func(*jsonschema.Schema, any) error { return errors.New("SECRET") }
	result := validateBytes(currentRoot, "asset.schema.json", modeRequired, []byte(`{}`))
	assertSetupFailed(t, result)
	if strings.Contains(*result.Limitation, "SECRET") {
		t.Fatal("limitation echoes library text")
	}
}

func TestUnreadableInputFailsSetup(t *testing.T) {
	assertSetupFailed(t, validateFile(currentRoot, "asset.schema.json", modeRequired, t.TempDir()+"/missing.json"))
}

func TestInputIsNotMutatedOnDisk(t *testing.T) {
	path := fixturesRoot + "/records/annotation-token-absent.json"
	before, _ := os.ReadFile(path)
	assertComplete(t, validateFile(currentRoot, "temporal_annotation.schema.json", modeRequired, path), true)
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("input changed")
	}
}

func quote(s string) string {
	data, _ := json.Marshal(s)
	return string(data)
}
