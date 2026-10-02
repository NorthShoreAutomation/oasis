package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"maps"
	"os"
	"path/filepath"
	"slices"
	"testing"
)

func sortedKeys(m map[string]string) []string {
	return slices.Sorted(maps.Keys(m))
}

const (
	frozenRoot   = "../baseline"
	currentRoot  = "../../../definitions"
	fixturesRoot = "../fixtures"
)

// makeBundle writes schemas and a bundle manifest into a temporary directory.
func makeBundle(t *testing.T, schemas map[string]string) string {
	t.Helper()
	root := t.TempDir()
	var entries []map[string]any
	for _, name := range sortedKeys(schemas) {
		data := []byte(schemas[name])
		if err := os.WriteFile(filepath.Join(root, name), data, 0o600); err != nil {
			t.Fatal(err)
		}
		sum := sha256.Sum256(data)
		entries = append(entries, map[string]any{
			"name":     name,
			"path":     name,
			"sha256":   hex.EncodeToString(sum[:]),
			"id":       nil,
			"base_uri": "https://schemas.oasis.invalid/bundles/test-1/" + name,
			"aliases":  []string{},
		})
	}
	writeManifest(t, root, map[string]any{
		"manifest_version": "1.0.0",
		"bundle_revision":  "test-1",
		"schemas":          entries,
	})
	return root
}

func writeManifest(t *testing.T, root string, manifest any) {
	t.Helper()
	data, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, manifestName), data, 0o600); err != nil {
		t.Fatal(err)
	}
}

func readManifest(t *testing.T, root string) map[string]any {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(root, manifestName))
	if err != nil {
		t.Fatal(err)
	}
	var manifest map[string]any
	if err := json.Unmarshal(data, &manifest); err != nil {
		t.Fatal(err)
	}
	return manifest
}

func record(t *testing.T, name string) []byte {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(fixturesRoot, "records", name))
	if err != nil {
		t.Fatal(err)
	}
	return data
}
