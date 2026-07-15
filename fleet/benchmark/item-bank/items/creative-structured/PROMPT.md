# Task: structured creative generation

Generate a SHORT structured product description for a fictional
product. The output MUST follow this exact structure (the grader
parses it as JSON):

```json
{
  "name": "<product name, 1-3 words>",
  "tagline": "<one-sentence tagline, 5-15 words>",
  "audience": "<target audience, 2-6 words>",
  "features": ["<feature 1>", "<feature 2>", "<feature 3>"]
}
```

The product category is: "a developer tool that automates repetitive
coding tasks".

Constraints:
- `name`, `tagline`, `audience` must each be a non-empty string.
- `features` must be a list of EXACTLY 3 items, each a short phrase.
- The whole structure must be valid JSON in `answer.txt`.

Write the JSON (and nothing else) to `answer.txt`.
