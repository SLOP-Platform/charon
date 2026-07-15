# Task: identify the root cause of a bug

A user reports: "When I send a request with a very long system prompt
(> 10,000 tokens), the gateway returns a 500 with `UpstreamProviderError`
about 30% of the time. Shorter prompts are reliable."

You are writing the "root cause" section of a bug investigation. The
relevant code is `router.py` (you don't have the full source here, but
you can reason from the symptoms).

Write your analysis to `answer.txt` covering:

1. ONE plausible root cause (a specific mechanism, not "something is
   wrong upstream"). The root cause should be testable — a developer
   should be able to confirm or rule it out by reading the code or
   adding a log line.
2. ONE concrete way to verify the hypothesis (what to log, what to
   check, or what minimal test to add).
3. ONE concrete fix direction (not "rewrite the router" — a specific
   change).

Format: plain text, three clearly separated points (numbered, headings,
or blank lines). Length: 3–8 sentences total. The grader checks the
three required points are present, not the prose quality.
