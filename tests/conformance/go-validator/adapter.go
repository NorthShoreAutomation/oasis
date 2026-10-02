package main

import (
	"errors"
	"os"
	"regexp"
	"slices"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

const (
	statusComplete     = "complete"
	statusInputInvalid = "input-invalid"
	statusSetupFailed  = "setup-failed"

	structuralValid   = "valid"
	structuralInvalid = "invalid"
	structuralNotRun  = "not-run"

	modeRequired   = "required"
	modeHistorical = "historical-unchecked"
)

var formatModes = []string{modeRequired, modeHistorical}

// allowedPatterns are the four audited bundle expressions. Go's standard
// RE2 engine without flags gives their ECMA-262 behavior: \d matches ASCII
// digits only and $ matches only at the absolute end of the text.
var allowedPatterns = []string{
	`^\d{8}_\d{6}$`,
	`^\d+\.\d+\.\d+$`,
	`^\d{1,2}:\d{2}:\d{2}[:'\.]?\d{0,2}$`,
	`^x_`,
}

const (
	unexpectedStopLimitation = "Setup failed: the structural library stopped unexpectedly."
	historicalLimitation     = "Date-time format assertions were not checked: labelled historical-unchecked baseline comparison."
	numericLimitationPrefix  = "Numeric resource guards refused the input before structural evaluation. " +
		"Configured limits: numeric token length at most 1,024 ASCII bytes; " +
		"absolute decimal exponent at most 10,000; " +
		"expansion budget at most 100,000 digit units per document. Exceeded limit: "
)

// Result is the adapter output. Errors holds only JSON Pointer instance
// locations, never library message text.
type Result struct {
	AdapterStatus string   `json:"adapter_status"`
	Structural    string   `json:"structural"`
	Limitation    *string  `json:"limitation"`
	Errors        []string `json:"errors"`
}

func notRun(status string, limitation *string) Result {
	return Result{AdapterStatus: status, Structural: structuralNotRun, Limitation: limitation, Errors: []string{}}
}

func setupFailed(err error) Result {
	var setup *setupError
	text := "Setup failed: an unexpected setup error occurred."
	if errors.As(err, &setup) {
		text = "Setup failed: " + setup.msg + "."
	}
	return notRun(statusSetupFailed, &text)
}

func stoppedUnexpectedly() Result {
	text := unexpectedStopLimitation
	return notRun(statusSetupFailed, &text)
}

func isAllowedPattern(expression string) bool {
	return slices.Contains(allowedPatterns, expression)
}

// compileAllowedPattern is the compiler's regular expression engine. It
// refuses any expression outside the audited list, so a pattern the audit
// walk did not reach still fails setup.
func compileAllowedPattern(expression string) (jsonschema.Regexp, error) {
	if !isAllowedPattern(expression) {
		return nil, setupFail("schema regular expression is not in the audited list")
	}
	return regexp.Compile(expression)
}

// adapter holds one compiled bundle for one format mode.
type adapter struct {
	bundle  *bundle
	mode    string
	schemas map[string]*jsonschema.Schema
}

// newAdapter loads and compiles a bundle offline. Every entry is compiled
// by its base_uri, so every reference in the bundle is resolved at setup.
func newAdapter(root, mode string) (a *adapter, err error) {
	defer func() {
		if recover() != nil {
			a, err = nil, setupFail("the structural library stopped unexpectedly")
		}
	}()
	if !slices.Contains(formatModes, mode) {
		return nil, setupFail("format mode must be required or historical-unchecked")
	}
	b, err := loadBundle(root)
	if err != nil {
		return nil, err
	}
	compiler := jsonschema.NewCompiler()
	compiler.DefaultDraft(jsonschema.Draft7)
	compiler.UseLoader(nil) // no file or network loading
	compiler.UseRegexpEngine(compileAllowedPattern)
	compiler.RegisterVocabulary(auditVocabulary)
	if mode == modeRequired {
		compiler.RegisterFormat(&jsonschema.Format{Name: "date-time", Validate: checkDateTime})
		compiler.AssertFormat()
	} else {
		// Draft 7 asserts formats by default, so an explicit no-op is needed.
		compiler.RegisterFormat(&jsonschema.Format{Name: "date-time", Validate: func(any) error { return nil }})
	}
	for _, entry := range b.entries {
		for _, uri := range append([]string{entry.BaseURI}, entry.Aliases...) {
			if err := compiler.AddResource(uri, entry.doc); err != nil {
				return nil, setupFail("a bundle identifier cannot be registered")
			}
		}
	}
	a = &adapter{bundle: b, mode: mode, schemas: map[string]*jsonschema.Schema{}}
	for _, entry := range b.entries {
		schema, err := compiler.Compile(entry.BaseURI)
		var audit *setupError
		if errors.As(err, &audit) {
			return nil, audit
		}
		if err != nil {
			return nil, setupFail("a bundle schema does not compile offline: an unresolved reference, an unaudited regular expression, or a metaschema violation")
		}
		a.schemas[entry.Name] = schema
	}
	return a, nil
}

func (a *adapter) schema(name string) (*jsonschema.Schema, error) {
	schema, ok := a.schemas[name]
	if !ok {
		return nil, setupFail("schema name is not in the bundle manifest")
	}
	return schema, nil
}

// validateInstance is the library call. Tests replace it to prove panic
// recovery.
var validateInstance = func(schema *jsonschema.Schema, value any) error {
	return schema.Validate(value)
}

// run strictly parses input and evaluates it against one compiled schema.
func (a *adapter) run(name string, input []byte) (result Result) {
	defer func() {
		if recover() != nil {
			result = stoppedUnexpectedly()
		}
	}()
	schema, err := a.schema(name)
	if err != nil {
		return setupFailed(err)
	}
	value, err := parseStrict(input)
	var invalid *inputInvalidError
	var refused *numericRefusedError
	switch {
	case errors.As(err, &invalid):
		return notRun(statusInputInvalid, nil)
	case errors.As(err, &refused):
		text := numericLimitationPrefix + refused.Error() + "."
		return notRun(statusSetupFailed, &text)
	case err != nil:
		return setupFailed(err)
	}
	result = Result{AdapterStatus: statusComplete, Structural: structuralValid, Errors: []string{}}
	if err := validateInstance(schema, value); err != nil {
		var verr *jsonschema.ValidationError
		if !errors.As(err, &verr) {
			return setupFailed(setupFail("structural evaluation failed without a validation result"))
		}
		result.Structural = structuralInvalid
		result.Errors = errorLocations(verr)
	}
	if a.mode == modeHistorical {
		text := historicalLimitation
		result.Limitation = &text
	}
	return result
}

// errorLocations returns the sorted, unique instance locations of the leaf
// errors as RFC 6901 JSON Pointers.
func errorLocations(root *jsonschema.ValidationError) []string {
	seen := map[string]bool{}
	var walk func(*jsonschema.ValidationError)
	walk = func(e *jsonschema.ValidationError) {
		if len(e.Causes) == 0 {
			seen[jsonPointer(e.InstanceLocation)] = true
		}
		for _, cause := range e.Causes {
			walk(cause)
		}
	}
	walk(root)
	locations := make([]string, 0, len(seen))
	for location := range seen {
		locations = append(locations, location)
	}
	slices.Sort(locations)
	return locations
}

var pointerEscaper = strings.NewReplacer("~", "~0", "/", "~1")

func jsonPointer(tokens []string) string {
	var b strings.Builder
	for _, token := range tokens {
		b.WriteString("/")
		b.WriteString(pointerEscaper.Replace(token))
	}
	return b.String()
}

// validateBytes runs setup, then the strict input policy, then structural
// validation. Setup failures take precedence over input failures.
func validateBytes(root, name, mode string, input []byte) Result {
	a, err := newAdapter(root, mode)
	if err != nil {
		return setupFailed(err)
	}
	return a.run(name, input)
}

// validateFile is validateBytes for an input file. The file is read only
// after setup succeeds.
func validateFile(root, name, mode, inputPath string) Result {
	a, err := newAdapter(root, mode)
	if err != nil {
		return setupFailed(err)
	}
	input, err := os.ReadFile(inputPath)
	if err != nil {
		return setupFailed(setupFail("input file cannot be read"))
	}
	return a.run(name, input)
}
