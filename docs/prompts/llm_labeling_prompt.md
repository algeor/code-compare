Goal: Label all PR suggestion examples for ML training.
You have access to this dataset folder:
/Users/I551270/Documents/GitHub/pipeline-fl-control-plane/ml/data/processed/pr_suggestion_coverage/dataset/
Input files:
1. Dataset JSONL:
   /Users/I551270/Documents/GitHub/pipeline-fl-control-plane/ml/data/processed/pr_suggestion_coverage/dataset/dataset.jsonl
Each row contains:
- example_id
- pr_url
- suggested_diff
- landed_diff
- repo
- suggestion_source
- deterministic_landed_estimate
- file_overlap_ratio
- changed_line_overlap_ratio
2. Existing label sheet:
   /Users/I551270/Documents/GitHub/pipeline-fl-control-plane/ml/data/processed/pr_suggestion_coverage/dataset/labels.csv
Output files to create/update:
1. Write detailed LLM labels here:
   /Users/I551270/Documents/GitHub/pipeline-fl-control-plane/ml/data/processed/pr_suggestion_coverage/dataset/llm_labels.jsonl
2. Also update labels.csv by filling:
   - label
   - expected_landed_percentage
   - label_notes
Task:
Go through every row in dataset.jsonl.
For each example:
Compare suggested_diff against landed_diff.
Question:
How much of suggested_diff actually landed in landed_diff?
Use exactly one label:
- 0%
  Nothing meaningful from suggested_diff landed.
  Same file path alone is not enough.
- partial
  Some meaningful code/logic landed, but important parts are missing or substantially rewritten.
- mostly
  The main suggested code/logic landed, but with reviewer edits, refactoring, renames, formatting, or small logic changes.
- 100%
  The suggestion landed essentially as-is.
  Trivial whitespace, import ordering, formatting, or nearby context changes are okay.
Rules:
- Inspect suggested_diff first.
- Identify the concrete suggested code/logic.
- Then inspect landed_diff.
- Ignore unrelated changes in landed_diff.
- Same file path alone is not enough.
- Same broad intent alone is not enough.
- If paths changed or files were renamed, count it as landed if the same code/logic landed.
- If suggested_diff is a fake inline-comment diff, compare the added code lines to the landed PR diff.
- If the PR includes the suggestion plus extra unrelated changes, grade only whether the suggestion landed.
- If the final PR solved the same problem with a different implementation, label partial or mostly depending on how much code/logic matches.
- If uncertain between two labels, choose the lower label and set confidence lower.
Percentage guidance:
- 0-10: no meaningful match
- 20-50: partial
- 60-85: mostly
- 90-100: essentially landed as suggested
For each example, write one JSON object to llm_labels.jsonl:
{
"example_id": "...",
"pr_url": "...",
"label": "0% | partial | mostly | 100%",
"expected_landed_percentage": 0,
"reasoning": "Short explanation of what matched and what did not.",
"matched_parts": [
"Concrete code/logic from suggested_diff that appears in landed_diff"
],
"missing_or_changed_parts": [
"Concrete code/logic from suggested_diff that is missing or changed"
],
"confidence": "low | medium | high"
}
Important:
- Do not ask me to label examples manually.
- Do not stop after one example.
- Process all examples in dataset.jsonl.
- Save progress every 20 examples.
- If interrupted, resume from existing llm_labels.jsonl and skip already labeled example_id values.
- At the end, print a summary:
  - total examples
  - labeled examples
  - counts by label
  - low-confidence examples
  - output file paths
