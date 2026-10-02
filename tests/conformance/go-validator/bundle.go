package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"maps"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

const (
	manifestName    = "bundle-manifest.json"
	manifestVersion = "1.0.0"
)

var (
	revisionPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)
	digestPattern   = regexp.MustCompile(`^[0-9a-f]{64}$`)
	drivePattern    = regexp.MustCompile(`^[A-Za-z]:`)
	topLevelKeys    = []string{"manifest_version", "bundle_revision", "schemas"}
	entryKeys       = []string{"name", "path", "sha256", "id", "base_uri", "aliases"}
	draft7Dialects  = []string{"http://json-schema.org/draft-07/schema#", "http://json-schema.org/draft-07/schema"}
)

// setupError is an environment or bundle setup failure. Its message is a
// fixed category and never carries input values or library message text.
type setupError struct{ msg string }

func (e *setupError) Error() string { return e.msg }

func setupFail(msg string) error { return &setupError{msg} }

type schemaEntry struct {
	Name    string
	Path    string
	SHA256  string
	ID      *string
	BaseURI string
	Aliases []string
	doc     any
}

type bundle struct {
	entries []schemaEntry
}

func hasExactKeys(m map[string]any, keys []string) bool {
	if len(m) != len(keys) {
		return false
	}
	for _, k := range keys {
		if _, ok := m[k]; !ok {
			return false
		}
	}
	return true
}

func isAbsoluteURI(value any) bool {
	s, ok := value.(string)
	if !ok || s == "" || s != strings.TrimSpace(s) {
		return false
	}
	u, err := url.Parse(s)
	return err == nil && u.Scheme != "" && u.Host != "" && u.Fragment == ""
}

// bundleFile checks that a manifest path is bundle-relative and that its
// resolved target stays inside the resolved bundle root.
func bundleFile(root string, value any) (string, error) {
	path, ok := value.(string)
	if !ok || path == "" {
		return "", setupFail("manifest path must be a nonempty string")
	}
	if strings.ContainsAny(path, "\\\x00") || strings.HasPrefix(path, "/") || drivePattern.MatchString(path) {
		return "", setupFail("manifest path must be bundle-relative")
	}
	for _, part := range strings.Split(path, "/") {
		if part == "" || part == "." || part == ".." {
			return "", setupFail("manifest path must stay inside the bundle")
		}
	}
	resolvedRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", setupFail("bundle root cannot be resolved")
	}
	target, err := filepath.EvalSymlinks(filepath.Join(root, filepath.FromSlash(path)))
	if err != nil {
		return "", setupFail("schema file cannot be read")
	}
	rel, err := filepath.Rel(resolvedRoot, target)
	if err != nil || rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) || filepath.IsAbs(rel) {
		return "", setupFail("manifest path leaves the bundle")
	}
	return target, nil
}

// loadBundle reads <root>/bundle-manifest.json, verifies every rule and
// digest, strictly parses each schema, and audits it. It reads no file that
// the manifest does not list.
func loadBundle(root string) (*bundle, error) {
	raw, err := os.ReadFile(filepath.Join(root, manifestName))
	if err != nil {
		return nil, setupFail("bundle manifest is missing")
	}
	tree, err := parseStrict(raw)
	if err != nil {
		return nil, setupFail("bundle manifest is not strict JSON")
	}
	manifest, ok := tree.(map[string]any)
	if !ok || !hasExactKeys(manifest, topLevelKeys) {
		return nil, setupFail("bundle manifest has the wrong top-level shape")
	}
	if manifest["manifest_version"] != manifestVersion {
		return nil, setupFail("unsupported manifest_version")
	}
	if revision, ok := manifest["bundle_revision"].(string); !ok || !revisionPattern.MatchString(revision) {
		return nil, setupFail("bundle_revision is invalid")
	}
	schemas, ok := manifest["schemas"].([]any)
	if !ok || len(schemas) == 0 {
		return nil, setupFail("schemas must be a nonempty array")
	}

	b := &bundle{}
	names := map[string]bool{}
	identifiers := map[string]bool{}
	for _, rawEntry := range schemas {
		entry, ok := rawEntry.(map[string]any)
		if !ok || !hasExactKeys(entry, entryKeys) {
			return nil, setupFail("schema entry has the wrong shape")
		}
		name, ok := entry["name"].(string)
		if !ok || name == "" {
			return nil, setupFail("schema name must be a nonempty string")
		}
		if names[name] {
			return nil, setupFail("duplicate schema name")
		}
		names[name] = true
		target, err := bundleFile(root, entry["path"])
		if err != nil {
			return nil, err
		}
		digest, ok := entry["sha256"].(string)
		if !ok || !digestPattern.MatchString(digest) {
			return nil, setupFail("sha256 must be 64 lowercase hexadecimal characters")
		}
		data, err := os.ReadFile(target)
		if err != nil {
			return nil, setupFail("schema file cannot be read")
		}
		sum := sha256.Sum256(data)
		if hex.EncodeToString(sum[:]) != digest {
			return nil, setupFail("schema digest does not match file bytes")
		}
		if !isAbsoluteURI(entry["base_uri"]) {
			return nil, setupFail("base_uri must be an absolute URI")
		}
		baseURI := entry["base_uri"].(string)
		var id *string
		if entry["id"] != nil {
			s, ok := entry["id"].(string)
			if !ok || s != baseURI {
				return nil, setupFail("base_uri must equal a non-null id")
			}
			id = &s
		}
		rawAliases, ok := entry["aliases"].([]any)
		if !ok {
			return nil, setupFail("aliases must be an array of absolute URIs")
		}
		aliases := []string{}
		for _, alias := range rawAliases {
			if !isAbsoluteURI(alias) {
				return nil, setupFail("aliases must be an array of absolute URIs")
			}
			aliases = append(aliases, alias.(string))
		}
		for _, identifier := range append([]string{baseURI}, aliases...) {
			if identifiers[identifier] {
				return nil, setupFail("identifier collision between bases and aliases")
			}
			identifiers[identifier] = true
		}
		doc, err := parseSchema(data)
		if err != nil {
			return nil, err
		}
		b.entries = append(b.entries, schemaEntry{name, entry["path"].(string), digest, id, baseURI, aliases, doc})
	}
	return b, nil
}

func parseSchema(data []byte) (any, error) {
	doc, err := parseStrict(data)
	var invalid *inputInvalidError
	var refused *numericRefusedError
	switch {
	case errors.As(err, &invalid):
		return nil, setupFail("schema file is not strict JSON")
	case errors.As(err, &refused):
		return nil, setupFail("a numeric resource guard refused a schema file: " + refused.Error())
	case err != nil:
		return nil, setupFail("schema file cannot be decoded")
	}
	switch doc.(type) {
	case map[string]any, bool:
	default:
		return nil, setupFail("schema is not an object or boolean")
	}
	if err := auditSchema(doc); err != nil {
		return nil, err
	}
	return doc, nil
}

// Draft 7 keywords whose values are schemas, plus the $defs container that
// the bundle uses as a reference target.
var (
	singleSubschemaKeys = []string{"additionalItems", "additionalProperties", "contains", "propertyNames", "if", "then", "else", "not", "items"}
	listSubschemaKeys   = []string{"allOf", "anyOf", "oneOf", "items"}
	mapSubschemaKeys    = []string{"properties", "patternProperties", "definitions", "$defs", "dependencies"}
)

// auditSchema walks every schema position in a resource before compilation.
// It refuses any regular expression outside the audited list, multipleOf,
// any format except date-time, and any dialect except Draft 7. Values of
// data keywords such as enum, const, default, and examples are not schemas
// and are not walked, so a property named "pattern" stays data. A schema
// reached only through $ref is audited by auditVocabulary during compilation.
func auditSchema(node any) error {
	obj, ok := node.(map[string]any)
	if !ok {
		return nil
	}
	if err := auditKeywords(obj); err != nil {
		return err
	}
	for _, key := range singleSubschemaKeys {
		if err := auditSchema(obj[key]); err != nil {
			return err
		}
	}
	for _, key := range listSubschemaKeys {
		list, _ := obj[key].([]any)
		for _, item := range list {
			if err := auditSchema(item); err != nil {
				return err
			}
		}
	}
	for _, key := range mapSubschemaKeys {
		members, _ := obj[key].(map[string]any)
		for _, name := range slices.Sorted(maps.Keys(members)) {
			if err := auditSchema(members[name]); err != nil {
				return err
			}
		}
	}
	return nil
}

// auditKeywords checks the keywords of one schema object.
func auditKeywords(obj map[string]any) error {
	if value, ok := obj["$schema"]; ok {
		if s, isString := value.(string); !isString || !slices.Contains(draft7Dialects, s) {
			return setupFail("only the Draft 7 dialect is configured")
		}
	}
	if value, ok := obj["pattern"]; ok {
		if s, isString := value.(string); !isString || !isAllowedPattern(s) {
			return setupFail("schema regular expression is not in the audited list")
		}
	}
	if value, ok := obj["patternProperties"]; ok {
		properties, isMap := value.(map[string]any)
		if !isMap {
			return setupFail("patternProperties is not an object")
		}
		for expression := range properties {
			if !isAllowedPattern(expression) {
				return setupFail("schema regular expression is not in the audited list")
			}
		}
	}
	if _, ok := obj["multipleOf"]; ok {
		return setupFail("multipleOf is refused at setup")
	}
	if value, ok := obj["format"]; ok && value != "date-time" {
		return setupFail("only the date-time format is configured")
	}
	return nil
}

// auditVocabulary runs auditKeywords on every schema object the compiler
// compiles, including a target reached only through $ref at a location the
// static walk does not visit. Draft 7 always applies a registered
// vocabulary. It adds no validation behavior.
var auditVocabulary = &jsonschema.Vocabulary{
	URL: "https://schemas.oasis.invalid/conformance/audit-vocabulary",
	Compile: func(_ *jsonschema.CompilerContext, obj map[string]any) (jsonschema.SchemaExt, error) {
		return nil, auditKeywords(obj)
	},
}
