package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"slices"
)

func main() {
	os.Exit(runCLI(os.Args[1:], os.Stdout, os.Stderr))
}

// runCLI prints one result object and returns 0 whenever the adapter ran to
// a status. It returns 2 only for command line usage errors.
func runCLI(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("go-validator", flag.ContinueOnError)
	flags.SetOutput(stderr)
	bundleDir := flags.String("bundle", "", "bundle directory that contains bundle-manifest.json")
	schema := flags.String("schema", "", "schema name from the bundle manifest")
	mode := flags.String("format-mode", "", "required or historical-unchecked")
	input := flags.String("input", "", "input JSON file")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	switch {
	case flags.NArg() != 0:
		fmt.Fprintln(stderr, "go-validator: unexpected positional arguments")
	case *bundleDir == "" || *schema == "" || *mode == "" || *input == "":
		fmt.Fprintln(stderr, "go-validator: --bundle, --schema, --format-mode, and --input are required")
	case !slices.Contains(formatModes, *mode):
		fmt.Fprintln(stderr, "go-validator: --format-mode must be required or historical-unchecked")
	default:
		encoder := json.NewEncoder(stdout)
		encoder.SetEscapeHTML(false)
		if err := encoder.Encode(validateFile(*bundleDir, *schema, *mode, *input)); err != nil {
			fmt.Fprintln(stderr, "go-validator: result cannot be written")
			return 1
		}
		return 0
	}
	flags.Usage()
	return 2
}
