---
name: efiling-document-renamer
description: Read the caption on e-filed court documents and propose standardized filenames with a confidence rating. Use when the user uploads e-filed documents and asks to rename, file, or log them.
---

# E-filing Document Renamer

> Portfolio note: this started as a reusable prompt I wrote for incoming e-filed documents
> at a plaintiff-side personal injury firm. It is packaged here in the skill format.
> It contains no firm data. Python code that applies the same rules is in
> `src/legal_workflows/efiling/`.

The user is a litigation assistant at a plaintiff-side firm, uploading e-filed documents.
For each document, read the caption on the first page and report:

- Plaintiff(s), defendant(s), cause number and court
- Which plaintiff is our client (the firm represents plaintiffs)
- A short description of the document, for example `MOTION FOR CONTINUANCE` or `POP`
- Confidence: `HIGH`, `MEDIUM` or `LOW`

## Filename format

```
[YYYYMMDD] [CLIENT LAST NAME] [CLIENT FIRST NAME] [DESCRIPTION]
```

- ALL CAPS, single spaces, no punctuation or special characters.
- The date has no dashes and keeps leading zeros on the month and day: October 8, 2026 is
  `20261008`, not `2026108`.
- Use the **received date** the user gives you, not the date printed on the document.

## Confidence

- `LOW`: more than one plaintiff, an unclear caption, or you are not sure who our client is.
  Say why. Never guess silently.
- `MEDIUM`: our client is identified, but something is incomplete, such as a missing court or
  a name that only partly matches.
- `HIGH`: one plaintiff, clearly our client, and every field read cleanly.

## Output

A table with the columns: original filename | cause number | new filename | confidence.
Sort it so `LOW` and `MEDIUM` rows come first, then list the reason for each one that
needs review.

## Input the user provides

```
Received dates:
<original filename> <date received>
...
```
