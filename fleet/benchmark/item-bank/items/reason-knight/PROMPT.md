# Task: a constraint-satisfaction reasoning problem

A standard 8x8 chessboard. Place 8 queens on it such that no two queens
attack each other (i.e. no two share a row, column, or diagonal).

Write your solution to `answer.txt` as 8 lines, one per queen, each
line stating the column number (1-8) for the queen on that row
(row 1 through row 8, top to bottom). One integer per line.

Example format:
```
1
5
8
6
3
7
2
4
```
The grader verifies: (a) the 8 column numbers are all distinct, (b) no
two queens are on the same diagonal, and (c) the file has exactly 8
lines.
