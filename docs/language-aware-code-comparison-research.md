# Language-Aware Code Comparison Research

## Recommendation

Use a layered approach instead of building custom logic for every language.

```text
diff parsing
-> language/file-type detection
-> notebook/code extraction
-> broad lexer tokenization
-> snippet-to-hunk recall metrics
-> optional structural parser metrics
-> supervised calibration on labels
```

For this project, the next practical step is:

1. Add `nbformat` for `.ipynb` extraction.
2. Add `Pygments` as the broad language tokenizer.
3. Keep existing custom tokenizers for Python, JSON, YAML, Markdown, and Dockerfile where they are better tailored.
4. Keep GumTree optional.
5. Add Tree-sitter or difftastic-style structural features later for the highest-volume languages.

## What Established Tools Do

### GitHub Linguist

GitHub Linguist is used by GitHub to detect blob languages, ignore binary or vendored files, suppress generated files in diffs, and generate language breakdown graphs.

Useful pattern for us:

- language detection is a separate layer
- detection uses file extension, filename, heuristics, and `.gitattributes` overrides
- generated and vendored files can be filtered separately

Source: https://github.com/github-linguist/linguist

How to use the idea here:

- Do not manually maintain every language rule forever.
- Use filename/extension mapping first.
- Later, optionally use Linguist output or Linguist-style metadata when repository language detection matters.

### Pygments

Pygments provides lexers for a very large number of languages and file formats. Its docs expose `get_all_lexers()`, returning lexer names, aliases, filename patterns, and MIME types.

Useful pattern for us:

- use a lexer to turn source text into language-aware tokens
- ignore whitespace/comment token types
- normalize identifiers/literals for rename-tolerant matching
- fallback to regex when no lexer is found

Source: https://pygments.org/docs/lexers/

Best fit:

- JavaScript
- TypeScript
- Shell
- PowerShell
- Makefile
- HTML
- CSS
- Groovy
- HCL/Terraform when supported by installed lexer version
- smaller long-tail languages

### Jupyter nbformat

`nbformat` is the reference Python API for working with Jupyter Notebook files.

Useful pattern for us:

- do not compare raw `.ipynb` JSON
- extract code cells
- compare code cell source as code
- optionally include markdown cells separately with markdown tokenization

Source: https://github.com/jupyter/nbformat

Best fit:

- Jupyter Notebook, which is nearly half of the language breakdown.

### Tree-sitter

Tree-sitter is a parser generator and incremental parsing library. Its docs describe it as general enough to parse many programming languages, fast enough for editor use, and robust in the presence of syntax errors.

Useful pattern for us:

- parse supported languages into syntax trees
- compare structural nodes rather than raw lines
- use only where parsers are available and stable

Source: https://tree-sitter.github.io/tree-sitter/

Best fit:

- Python
- JavaScript
- TypeScript
- Bash
- HTML
- CSS
- JSON
- maybe HCL/Terraform through community parsers

### Difftastic

Difftastic is a structural diff tool that parses code with Tree-sitter and compares files based on syntax instead of line-by-line text. It explicitly targets formatting-insensitive diffs.

Useful pattern for us:

- structural comparison is helpful after lexical matching has found a candidate chunk
- it supports both programming languages and structured text formats
- it is better as an optional feature than as the first filter

Source: https://difftastic.wilfred.me.uk/

Best fit:

- diagnostic/evidence feature for supported files
- future replacement or complement for GumTree in some languages

### SourcererCC

SourcererCC is a token-based clone detector for very large code bases. Its workflow tokenizes source code first, then runs clone detection over tokenized files. It supports different granularities such as files, methods, statements, or blocks, and its threshold examples use token similarity.

Useful pattern for us:

- token-based clone detection is a standard approach
- compare at smaller granularity, not whole PR diff blobs
- thresholds should be calibrated on labeled data

Source: https://github.com/Mondego/SourcererCC

Best fit:

- validates our current token-recall and best-hunk strategy
- supports the idea of snippet-to-candidate-chunk comparison

### PMD CPD

PMD CPD is a copy-paste detector. Its docs expose language selection and options to ignore literal or identifier differences. That maps directly to Type-2 clone detection.

Useful pattern for us:

- identifier/literal normalization is standard
- tokenization errors should not stop the entire run
- language-specific tokenizers are useful, but not every language needs full AST parsing

Source: https://pmd.github.io/pmd/pmd_userdocs_cpd.html

Best fit:

- supports our identifier-normalized token recall
- supports adding literal-normalized token recall next

### Semgrep

Semgrep is semantic grep for code and supports 30+ languages. It is strong when you know the pattern to search for.

Useful pattern for us:

- great for exact semantic patterns
- not the first choice for generic “did this arbitrary suggestion land?” similarity
- useful later for specific categories of suggestions, such as “added missing timeout”, “added auth check”, or “changed API call”

Source: https://github.com/semgrep/semgrep

Best fit:

- optional specialized detectors, not broad similarity scoring

## Language Plan For This Dataset

| Language/file type | Recommended handling |
|---|---|
| Jupyter Notebook | `nbformat` extraction, then tokenize code cells by cell language |
| Python | existing Python tokenizer, optional AST later |
| JavaScript | Pygments first, Tree-sitter/difftastic later |
| TypeScript | Pygments first, Tree-sitter/difftastic later |
| Shell | Pygments Bash/Shell lexer first, Tree-sitter Bash later if needed |
| Makefile | Pygments Makefile lexer |
| HTML | Pygments first, Tree-sitter HTML later |
| CSS | Pygments first, Tree-sitter CSS later |
| Dockerfile | current custom tokenizer or Pygments Docker lexer |
| HCL/Terraform | Pygments if available, otherwise `python-hcl2` or Tree-sitter HCL later |
| PowerShell | Pygments PowerShell lexer |
| Vue | split/extract template/script/style if practical, otherwise Pygments/Tree-sitter later |
| Groovy/Jenkinsfile | Pygments Groovy lexer |

## Priority From Repository Language Volume

The latest language inventory suggests the implementation should prioritize broad parser/lexer coverage for the largest languages first, not the earlier notebook-heavy assumption.

Top language/file-type volumes:

| Rank | Language/file type | Size | Priority | Recommended first handling |
|---:|---|---:|---|---|
| 1 | Go | 117,592,931 | P0 | Pygments now, Tree-sitter/difftastic later |
| 2 | Python | 104,479,533 | P0 | existing Python tokenizer, AST later |
| 3 | C++ | 33,935,046 | P0 | Pygments now, Tree-sitter/difftastic later |
| 4 | Rust | 30,795,425 | P0 | Pygments now, Tree-sitter/difftastic later |
| 5 | Java | 28,836,119 | P0 | Pygments now, Tree-sitter/difftastic or GumTree later |
| 6 | HTML | 21,717,893 | P1 | Pygments now, Tree-sitter HTML later |
| 7 | Groovy | 14,416,061 | P1 | Pygments now |
| 8 | HCL | 12,080,963 | P1 | Pygments if available, otherwise HCL parser later |
| 9 | Jupyter Notebook | 9,880,148 | P1 | `nbformat` extraction |
| 10 | Shell | 6,657,579 | P1 | Pygments Bash/Shell lexer |
| 11 | TypeScript | 4,432,414 | P1 | Pygments now, Tree-sitter later |
| 12 | C | 4,216,709 | P1 | Pygments now, Tree-sitter/difftastic later |
| 13 | JavaScript | 4,114,138 | P1 | Pygments now, Tree-sitter later |
| 14 | Makefile | 3,032,564 | P2 | Pygments Makefile lexer |
| 15 | Dockerfile | 1,652,631 | P2 | current custom tokenizer or Pygments Docker lexer |
| 16 | Smarty | 1,040,197 | P2 | Pygments/template lexer if available, regex fallback |
| 17 | TLA | 615,881 | P2 | Pygments if available, regex fallback |
| 18 | Mustache | 450,550 | P2 | Pygments/template lexer if available, regex fallback |
| 19 | Scala | 421,621 | P2 | Pygments now, Tree-sitter later if needed |
| 20 | Rich Text Format | 317,807 | P3 | usually exclude or text fallback |
| 21 | Cap'n Proto | 263,989 | P3 | Pygments if available, regex fallback |
| 22 | CMake | 260,262 | P3 | Pygments CMake lexer |
| 23 | Vue | 217,941 | P3 | split SFC blocks later, Pygments fallback now |
| 24 | Assembly | 192,706 | P3 | Pygments assembler lexer |
| 25 | Perl | 116,403 | P3 | Pygments Perl lexer |
| 26 | CAP CDS | 99,958 | P3 | regex fallback unless a local lexer/parser exists |
| 27 | CUE | 74,611 | P3 | Pygments if available, regex fallback |
| 28 | CSS | 65,232 | P3 | Pygments CSS lexer |
| 29 | Objective-C | 58,741 | P3 | Pygments Objective-C lexer |
| 30 | just | 57,460 | P3 | regex fallback or small custom tokenizer |
| 31 | PowerShell | 44,839 | P3 | Pygments PowerShell lexer |
| 32 | Scilab | 40,785 | P3 | Pygments if available, regex fallback |
| 33 | Lua | 39,786 | P3 | Pygments Lua lexer |
| 34 | PHP | 38,957 | P3 | Pygments now, Tree-sitter/GumTree later if useful |
| 35 | Open Policy Agent | 25,409 | P3 | regex fallback or Rego lexer/parser if available |
| 36 | MDX | 16,163 | P3 | Markdown/JSX hybrid fallback |
| 37 | Gherkin | 15,321 | P3 | Pygments Gherkin lexer |
| 38 | Inno Setup | 14,609 | P3 | Pygments if available, regex fallback |
| 39 | SCSS | 14,081 | P3 | Pygments SCSS lexer |
| 40 | Jinja | not provided | P3 | Pygments/template lexer if available, regex fallback |

Practical priority:

```text
P0: Go, Python, C++, Rust, Java
P1: HTML, Groovy, HCL, Jupyter Notebook, Shell, TypeScript, C, JavaScript
P2/P3: route through Pygments or fallback unless labels show they matter
```

This means Pygments becomes more valuable than one-off custom tokenizers, because it covers most of the long tail immediately.

## Why Not One Universal AST Tool

There is no painless universal AST for all these files.

Reasons:

- notebooks are containers, not source files
- YAML, JSON, HCL, HTML, CSS, and Markdown are structured text/config, not normal programming languages
- parser availability differs by language
- parser setup can add downloads, native dependencies, or brittle versioning

So the reliable standard pattern is layered fallback:

```text
best available parser/tokenizer
-> broad lexer
-> regex fallback
```

## Proposed Next Implementation

Add two dependencies to the ML environment:

```text
pygments
nbformat
```

Then update tokenization:

```text
.ipynb -> nbformat extract code cells -> tokenize extracted source
known custom formats -> current custom tokenizer
other known languages -> Pygments lexer by filename
unknown -> regex fallback
```

Also add output columns:

```text
language_detector
tokenizer
tokenizer_fallback_reason
extracted_notebook_code_cell_count
```

## Bottom Line

Do not write per-language custom parsers.

Use established layers:

- GitHub Linguist-style detection for file identity
- `nbformat` for notebooks
- Pygments for broad lexical coverage
- Tree-sitter/difftastic for optional structural matching
- clone-detection metrics over candidate hunks
- labels to calibrate thresholds

This gives broad coverage now and a clean path to deeper language support later.
