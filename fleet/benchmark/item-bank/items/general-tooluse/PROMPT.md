# Task: a minimal tool-use task

You have a calculator tool available: `calc(expression: str) -> float`.
You can invoke it by writing a single line in the form:

```
TOOL_CALL: calc(<expression>)
```

The expression MUST be a single arithmetic expression with `+`, `-`,
`*`, `/`, and parentheses. The result must be a single number written
to `answer.txt`.

For the problem: compute `(3 + 4) * 5 - 6 / 2`.

Write the tool call line first, then on a separate line write the
result to `answer.txt`. The grader checks both: the tool-call line is
present and the result is correct (= 32.0).
