# Test Report Generator

## Overview
The scripts in this directory parse Unity-based C test suites and build an interactive HTML report that summarizes every discovered test case, its metadata, and captured log results. It is intended to be used by firmware developers who need a quick, visual way to review pass/fail statistics and inspect test vectors without opening the original source files.

## Key Features
- Parses Unity tests straight from the source tree using `UnityTestParser`.
- Enriches each test case with structured metadata (group, description, preconditions, vector data).
- Applies execution results from an external log file and highlights mismatches.
- Generates a modern HTML dashboard that includes summary stats, per-group breakdowns, and expandable data sections for Given/Expected vectors.
- Embeds Git information and log provenance to keep reports auditable.

## How to use Unity
- Official docs and source: https://github.com/ThrowTheSwitch/Unity
- Quick steps:
  1. Install Unity as a submodule or vendor the source into your project.
  2. Include `unity.h` in each test file and register tests via `TEST_GROUP` / `TEST`.
  3. Provide a `main()` that calls `UnityMain()` (or reuse `test_main.c` from Unity’s examples).
 
## Requirements
- Python 3.8 or newer.
- Optional: a Unity test log text file to overlay real execution results.

## Quick Start
```bash
python test_report_generator\test_report_generator.py \
    --test-dir test\aes \
    --title "Daily Crypto Regression" \
    --meta-json cfg.json \
    --log-file sample_log.txt
```

### Useful Arguments
| Option | Description |
| ------ | ----------- |
| `--parse` | Only parse tests; skip HTML generation. |
| `--test-dir` | Root directory containing Unity test sources (default: `test`). |
| `--root` | Project root, used for Git metadata lookup. |
| `--title` | Custom title for the HTML report (defaults to `Untitled`). |
| `--meta-json` | JSON file or literal JSON string rendered in the meta section. |
| `--log-file` | Unity test run log; SHA256 and filename appear in the report header. |
| `--show-git-info` | Include Git branch/tag/commit info in the header (enabled by default). |

## Output
- HTML reports are written to `output_report/` with a timestamped filename (e.g., `test_report_20251119_235611.html`).
- Assets are self-contained, so you can archive or share the generated HTML file directly.

## Tips
- Keep `meta.json` small and focused on the most relevant attributes; the layout renders them as cards.
- Long test names automatically expose their full content via the browser tooltip.
- Use the "Parse only" mode during CI to validate test discovery without producing artifacts.

## `meta_json` Rules
- The value passed to `--meta-json` can be either a path to a JSON file or an inline JSON string.
- Accepted shapes:
  - **Object** (`{ "key": "value", ... }`): rendered as one row of meta cards.
  - **Array of objects** (`[{...}, {...}]`): cards are concatenated in the order provided.
- Keys become the card labels (case-insensitive); values are stringified and trimmed.
- Empty strings, `null`, or missing values are skipped.
- Nested objects/arrays are not flattened; prefer top-level primitives for predictable layout.
- Example file:
  ```json
  {
      "build": "SP1-2025.11",
      "device": "S32K311",
      "dev stage": "beta"
  }
  ```

# Unity Test Parsing Rules

## Comment Block Structure
- Place metadata comments immediately above the `TEST(...)` declaration, one per line.
- Each line must follow `// @TAG: value` and should include a space after the colon.

## Supported Tags
| Tag | Description | Required |
| --- | ----------- | -------- |
| `@TEST_ID` | Unique identifier for the test (e.g., `XXX_TEST_001`) | Optional |
| `@PRE_CON` | Comma-separated list of preconditions | Optional |
| `@TEST_DESC` | Human-readable description of the test | Optional |
| `@GIVEN` | Input vectors in `key=value` or `key=[src:path]symbol` form | Optional |
| `@EXPECTED` | Expected outputs using the same format as `@GIVEN` | Optional |

## Detailed Rules
- **Placement**: All tags must appear before the test function declaration to be detected.
- **`@TEST_ID`**: Must be unique per test suite; avoid whitespace to keep CLI/log parsing simple.
- **`@TEST_DESC`**: Provide concise prose; if omitted, the report shows `-`.
- **`@PRE_CON`**: Commas split the items; the generator converts them to `<br/>` so each entry appears on its own line.
- **`@GIVEN` / `@EXPECTED`**:
  - `key=value` is treated as a literal scalar or string.
  - `key=[src:file_path]symbol_name` lets `vector_extractor` resolve actual vector data and show it in the HTML “details” accordion.
  - Items are comma-separated, and surrounding whitespace is trimmed automatically.
- **Missing Values**:
  - Empty values render as `-`.
  - Omitted tags produce blank or `-` entries in the report.
- **Escaping**: All strings are HTML-escaped, preventing injection issues while preserving content.

## `key=[src:path]symbol` Coverage
- The path must be relative to the project root and located under `test/` (e.g., `test/common/test_vector.c`).
- Supported variable forms inside those `.c` files:
  1. `uint8_t name[N] = { 0x00, ... };` → displayed as byte arrays (with automatic line wrapping).
  2. `uint8_t name[N] = "literal";` → exposes both the literal string and hex representation.
  3. `(u)int{8,16,32,64}_t name = VALUE;` → shown as scalar details (raw/dec/hex).
- Only `uint8_t` arrays/strings and fixed-width integer scalars are parsed; structs or other types are ignored.
- Path and symbol must match exactly; otherwise the report shows a “value not found” warning card.

## Example
```c
// @TEST_ID: XXX_TEST_001
// @PRE_CON: 1.Initialize, 2.hsm_state is HSM_READY
// @TEST_DESC: Inject RSA(2048) Key Success
// @GIVEN: key_id=141, modulus=[src:test/common/test_vector.c]test_rsa2048_modulus
// @EXPECTED: return=RET_OK, hsm_state=HSM_READY
TEST(TEST_CRYPTO, Inject_RSA_KEY_PAIR)
{
    ...
}
```

## Troubleshooting
1. **No tests detected**: Ensure `--test-dir` points to the directory containing Unity suites and that they follow the expected naming conventions.
2. **Log mismatch warnings**: The script prints any test IDs found in the log but missing from code, helping you keep test metadata synchronized.
3. **Encoding errors**: Logs are decoded as UTF-8 with `errors='ignore'`; confirm the log file uses UTF-8-compatible encoding.

For further customization, inspect `src/report_generator.py` and the supporting utility modules inside `src/`.
