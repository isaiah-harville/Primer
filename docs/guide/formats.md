# Supported formats

| Format | Extension | Notes |
| --- | --- | --- |
| PDF | `.pdf` | Text layer and, where needed, text inside images |
| Word | `.docx` | Office Open XML only |
| PowerPoint | `.pptx` | One page number per slide |
| Markdown | `.md`, `.markdown` | Headings become section citations |
| Plain text | `.txt` | |

## What is not supported

**Legacy Office formats** (`.doc`, `.ppt`) are rejected. They need a
converter process Primer does not run, and accepting them would mean failing
them after the upload rather than before it.

**Spreadsheets, images, and audio** are not accepted. A spreadsheet's
meaning usually lives in its structure rather than its prose, and answering
from it well needs different machinery than answering from a document.

## How the format is decided

Primer decides what a file is from its contents, then checks that against
its name. Both have to agree.

Trusting the extension alone would hand the parser a PDF wearing a `.txt`
name. Trusting the contents alone would fill a library with files whose
names promise something they are not. A mismatch is rejected with
`unsupported_content`.

## Text inside images

Slides and scanned reports carry much of their content as pictures. Primer
reads text out of images so that content is searchable.

!!! warning "Recognised text is a transcription"
    Text read from an image is a machine's reading of it, not the document's
    own characters, and it can be subtly wrong in ways that are invisible in
    the result. In testing, an image reading `SCANNED EVIDENCE` was
    transcribed as `SCANNED E EVIDENCE`.

    Primer does not currently mark which passages came from images, so a
    citation cannot tell you that it was transcribed. If exact wording
    matters, check the source. Operators who prefer exactness over coverage
    can switch image reading off; scanned documents are then reported as
    `ocr_required` rather than being indexed approximately.

## Documents with no readable text

A file that parses but yields nothing to index is reported rather than
silently accepted:

- `ocr_required` — there is no text layer, and image reading is switched off.
- `no_text_found` — images were read too, and there was still nothing.

An empty index for a document would otherwise look like success, and the
document would simply never appear in an answer.
