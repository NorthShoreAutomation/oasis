package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

func assertSetupFailed(t *testing.T, result Result) {
	t.Helper()
	if result.AdapterStatus != statusSetupFailed || result.Structural != structuralNotRun {
		t.Fatalf("want setup-failed/not-run, got %+v", result)
	}
	if result.Limitation == nil || *result.Limitation == "" {
		t.Fatal("setup failure has no limitation")
	}
	if len(result.Errors) != 0 {
		t.Fatalf("setup failure has errors %v", result.Errors)
	}
}

func assertComplete(t *testing.T, result Result, valid bool) {
	t.Helper()
	want := structuralInvalid
	if valid {
		want = structuralValid
	}
	if result.AdapterStatus != statusComplete || result.Structural != want {
		t.Fatalf("want complete/%s, got %+v", want, result)
	}
}

func TestRepositoryBundlesCompileInBothModes(t *testing.T) {
	for _, root := range []string{frozenRoot, currentRoot} {
		for _, mode := range formatModes {
			a, err := newAdapter(root, mode)
			if err != nil {
				t.Fatalf("%s %s: %v", root, mode, err)
			}
			for _, entry := range a.bundle.entries {
				if _, err := a.schema(entry.Name); err != nil {
					t.Fatalf("%s %s %s: %v", root, mode, entry.Name, err)
				}
			}
		}
	}
}

func TestUnknownSchemaNameFailsSetup(t *testing.T) {
	assertSetupFailed(t, validateBytes(currentRoot, "nope.schema.json", modeRequired, []byte("{}")))
}

func TestSetupFailureOutranksInvalidInput(t *testing.T) {
	assertSetupFailed(t, validateBytes(currentRoot, "nope.schema.json", modeRequired, []byte("{")))
	assertSetupFailed(t, validateBytes(t.TempDir(), "t.schema.json", modeRequired, []byte("{")))
}

func TestManifestRules(t *testing.T) {
	mutations := map[string]func(m map[string]any, entry map[string]any){
		"wrong digest":        func(_ map[string]any, e map[string]any) { e["sha256"] = strings.Repeat("0", 64) },
		"uppercase digest":    func(_ map[string]any, e map[string]any) { e["sha256"] = strings.ToUpper(e["sha256"].(string)) },
		"absolute path":       func(_ map[string]any, e map[string]any) { e["path"] = "/etc/passwd" },
		"parent traversal":    func(_ map[string]any, e map[string]any) { e["path"] = "../t.schema.json" },
		"inner traversal":     func(_ map[string]any, e map[string]any) { e["path"] = "a/../t.schema.json" },
		"dot segment":         func(_ map[string]any, e map[string]any) { e["path"] = "./t.schema.json" },
		"backslash":           func(_ map[string]any, e map[string]any) { e["path"] = `a\t.schema.json` },
		"drive letter":        func(_ map[string]any, e map[string]any) { e["path"] = "C:t.schema.json" },
		"missing file":        func(_ map[string]any, e map[string]any) { e["path"] = "missing.schema.json" },
		"relative base":       func(_ map[string]any, e map[string]any) { e["base_uri"] = "t.schema.json" },
		"base with fragment":  func(_ map[string]any, e map[string]any) { e["base_uri"] = "https://a.invalid/t.json#x" },
		"id differs":          func(_ map[string]any, e map[string]any) { e["id"] = "https://a.invalid/other.json" },
		"relative alias":      func(_ map[string]any, e map[string]any) { e["aliases"] = []any{"x.json"} },
		"alias equals base":   func(_ map[string]any, e map[string]any) { e["aliases"] = []any{e["base_uri"]} },
		"extra entry key":     func(_ map[string]any, e map[string]any) { e["extra"] = true },
		"empty name":          func(_ map[string]any, e map[string]any) { e["name"] = "" },
		"wrong version":       func(m map[string]any, _ map[string]any) { m["manifest_version"] = "2.0.0" },
		"bad revision":        func(m map[string]any, _ map[string]any) { m["bundle_revision"] = "../x" },
		"extra top key":       func(m map[string]any, _ map[string]any) { m["extra"] = 1 },
		"empty schema list":   func(m map[string]any, _ map[string]any) { m["schemas"] = []any{} },
		"duplicate name":      func(m map[string]any, e map[string]any) { m["schemas"] = []any{e, cloneEntry(e, "other")} },
		"duplicate base":      func(m map[string]any, e map[string]any) { m["schemas"] = []any{e, dupBase(e)} },
		"missing entry field": func(_ map[string]any, e map[string]any) { delete(e, "aliases") },
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			root := makeBundle(t, map[string]string{"t.schema.json": `{"type": "object"}`})
			manifest := readManifest(t, root)
			entry := manifest["schemas"].([]any)[0].(map[string]any)
			mutate(manifest, entry)
			writeManifest(t, root, manifest)
			assertSetupFailed(t, validateBytes(root, "t.schema.json", modeRequired, []byte("{}")))
		})
	}
}

func cloneEntry(e map[string]any, suffix string) map[string]any {
	c := map[string]any{}
	for k, v := range e {
		c[k] = v
	}
	c["base_uri"] = e["base_uri"].(string) + suffix
	return c
}

func dupBase(e map[string]any) map[string]any {
	c := cloneEntry(e, "")
	c["name"] = "other"
	return c
}

func TestManifestDuplicateKeyFailsSetup(t *testing.T) {
	root := makeBundle(t, map[string]string{"t.schema.json": `{}`})
	data, _ := os.ReadFile(filepath.Join(root, manifestName))
	text := strings.Replace(string(data), `"manifest_version": "1.0.0",`, `"manifest_version": "1.0.0", "manifest_version": "1.0.0",`, 1)
	os.WriteFile(filepath.Join(root, manifestName), []byte(text), 0o600)
	assertSetupFailed(t, validateBytes(root, "t.schema.json", modeRequired, []byte("{}")))
}

func TestSymlinkOutsideBundleFailsSetup(t *testing.T) {
	outside := t.TempDir()
	os.WriteFile(filepath.Join(outside, "x.json"), []byte(`{}`), 0o600)
	root := makeBundle(t, map[string]string{"t.schema.json": `{}`})
	os.Remove(filepath.Join(root, "t.schema.json"))
	if err := os.Symlink(filepath.Join(outside, "x.json"), filepath.Join(root, "t.schema.json")); err != nil {
		t.Skip("symlinks unavailable")
	}
	manifest := readManifest(t, root)
	manifest["schemas"].([]any)[0].(map[string]any)["sha256"] = "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
	writeManifest(t, root, manifest)
	assertSetupFailed(t, validateBytes(root, "t.schema.json", modeRequired, []byte("{}")))
}

func TestSchemaBytesUseStrictPolicyAndGuards(t *testing.T) {
	for name, schema := range map[string]string{
		"duplicate key":  `{"type": "object", "type": "array"}`,
		"guard":          `{"maximum": 1e10001}`,
		"not an object":  `[]`,
		"malformed json": `{`,
	} {
		t.Run(name, func(t *testing.T) {
			root := makeBundle(t, map[string]string{"t.schema.json": schema})
			assertSetupFailed(t, validateBytes(root, "t.schema.json", modeRequired, []byte("{}")))
		})
	}
}

func TestSchemaAuditRefusesAtSetup(t *testing.T) {
	for name, schema := range map[string]string{
		"unlisted pattern":                `{"properties": {"a": {"pattern": "^a$"}}}`,
		"unlisted pattern property":       `{"patternProperties": {"^y_": {}}}`,
		"pattern under definitions":       `{"definitions": {"d": {"pattern": "[a-z]"}}}`,
		"pattern under $defs":             `{"$defs": {"d": {"pattern": "[a-z]"}}}`,
		"pattern in items array":          `{"items": [{"pattern": "a"}]}`,
		"pattern in dependencies":         `{"dependencies": {"a": {"pattern": "a"}}}`,
		"pattern in if":                   `{"if": {"pattern": "a"}}`,
		"non-string pattern":              `{"pattern": 1}`,
		"unreferenced unlisted in $defs":  `{"$defs": {"x": {"patternProperties": {"^z": {}}}}}`,
		"pattern reached only by $ref":    `{"$ref": "#/x", "x": {"pattern": "^a$"}}`,
		"other format":                    `{"properties": {"a": {"format": "email"}}}`,
		"other format under definitions":  `{"definitions": {"d": {"format": "email"}}}`,
		"format reached only by $ref":     `{"$ref": "#/x", "x": {"format": "email"}}`,
		"multipleOf":                      `{"properties": {"a": {"multipleOf": 0.01}}}`,
		"multipleOf under definitions":    `{"definitions": {"d": {"multipleOf": 2}}}`,
		"multipleOf reached only by $ref": `{"$ref": "#/x", "x": {"multipleOf": 2}}`,
		"other dialect":                   `{"$schema": "https://json-schema.org/draft/2020-12/schema"}`,
		"nested other dialect":            `{"properties": {"a": {"$schema": "http://json-schema.org/draft-04/schema#"}}}`,
		"missing resource":                `{"properties": {"a": {"$ref": "./missing.schema.json"}}}`,
		"missing fragment":                `{"$ref": "#/definitions/Nope"}`,
		"invalid schema for metaschema":   `{"type": 5}`,
	} {
		t.Run(name, func(t *testing.T) {
			root := makeBundle(t, map[string]string{"t.schema.json": schema})
			for _, mode := range formatModes {
				assertSetupFailed(t, validateBytes(root, "t.schema.json", mode, []byte("{}")))
			}
		})
	}
}

func TestAuditFollowsReferenceIntoAnotherBundleFile(t *testing.T) {
	// The target sits under an unknown keyword of b, so only the reference
	// from a reaches it. Python refuses both keywords there at setup.
	for _, c := range []struct{ target, reason string }{
		{`{"x": {"format": "email"}}`, "Setup failed: only the date-time format is configured."},
		{`{"x": {"multipleOf": 2}}`, "Setup failed: multipleOf is refused at setup."},
	} {
		t.Run(c.reason, func(t *testing.T) {
			root := makeBundle(t, map[string]string{
				"a.schema.json": `{"$ref": "./b.schema.json#/x"}`,
				"b.schema.json": c.target,
			})
			for _, mode := range formatModes {
				result := validateBytes(root, "b.schema.json", mode, []byte("{}"))
				assertSetupFailed(t, result)
				if *result.Limitation != c.reason {
					t.Fatalf("want limitation %q, got %q", c.reason, *result.Limitation)
				}
			}
		})
	}
}

func TestPatternNamedPropertyIsDataNotAssertion(t *testing.T) {
	root := makeBundle(t, map[string]string{"t.schema.json": `{"properties": {"pattern": {"type": "string"}}}`})
	assertComplete(t, validateBytes(root, "t.schema.json", modeRequired, []byte(`{"pattern": "[unclosed"}`)), true)
}

func TestKeywordNamesInPropertiesAndDataAreNotAudited(t *testing.T) {
	root := makeBundle(t, map[string]string{
		"p.schema.json": `{"properties": {"format": {"type": "string"}, "multipleOf": {"type": "string"}}}`,
		"c.schema.json": `{"const": {"format": "email", "multipleOf": 2}}`,
	})
	assertComplete(t, validateBytes(root, "p.schema.json", modeRequired, []byte(`{"format": "email", "multipleOf": "2"}`)), true)
	assertComplete(t, validateBytes(root, "c.schema.json", modeRequired, []byte(`{"format": "email", "multipleOf": 2}`)), true)
}

func TestFileLoaderIsDisabled(t *testing.T) {
	// A default compiler would load this existing file; the adapter must not.
	outside := t.TempDir()
	target := filepath.Join(outside, "other.schema.json")
	if err := os.WriteFile(target, []byte(`{"type": "string"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	ref := "file://" + filepath.ToSlash(target)
	root := makeBundle(t, map[string]string{"t.schema.json": `{"$ref": "` + ref + `"}`})
	assertSetupFailed(t, validateBytes(root, "t.schema.json", modeRequired, []byte(`"s"`)))
}

func TestUnlistedBundleFileIsNotLoaded(t *testing.T) {
	root := makeBundle(t, map[string]string{"t.schema.json": `{"$ref": "other.schema.json"}`})
	os.WriteFile(filepath.Join(root, "other.schema.json"), []byte(`{}`), 0o600)
	assertSetupFailed(t, validateBytes(root, "t.schema.json", modeRequired, []byte("{}")))
}

func TestNetworkReferenceFailsSetupWithoutRequest(t *testing.T) {
	var hits atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		w.Write([]byte(`{}`))
	}))
	defer server.Close()
	for _, ref := range []string{server.URL + "/remote.schema.json", "https://example.invalid/remote.schema.json"} {
		root := makeBundle(t, map[string]string{"t.schema.json": `{"$ref": "` + ref + `"}`})
		for _, mode := range formatModes {
			assertSetupFailed(t, validateBytes(root, "t.schema.json", mode, []byte("{}")))
		}
	}
	if hits.Load() != 0 {
		t.Fatalf("server received %d requests", hits.Load())
	}
}

func TestAliasReferenceResolvesInsideBundle(t *testing.T) {
	root := makeBundle(t, map[string]string{
		"a.schema.json": `{"$ref": "https://alias.oasis.invalid/b.json"}`,
		"b.schema.json": `{"type": "string"}`,
	})
	manifest := readManifest(t, root)
	for _, raw := range manifest["schemas"].([]any) {
		entry := raw.(map[string]any)
		if entry["name"] == "b.schema.json" {
			entry["aliases"] = []any{"https://alias.oasis.invalid/b.json"}
		}
	}
	writeManifest(t, root, manifest)
	assertComplete(t, validateBytes(root, "a.schema.json", modeRequired, []byte(`"s"`)), true)
	assertComplete(t, validateBytes(root, "a.schema.json", modeRequired, []byte(`1`)), false)
}

func TestBatchReferencesResolveOffline(t *testing.T) {
	for _, root := range []string{frozenRoot, currentRoot} {
		for _, c := range []struct{ schema, good, bad string }{
			{"asset_batch_import.schema.json", "minimal-asset_batch_import.json", "missing-required-asset_batch_import.json"},
			{"collection_batch_import.schema.json", "minimal-collection_batch_import.json", "missing-required-collection_batch_import.json"},
		} {
			assertComplete(t, validateBytes(root, c.schema, modeRequired, record(t, c.good)), true)
			assertComplete(t, validateBytes(root, c.schema, modeRequired, record(t, c.bad)), false)
		}
	}
}
