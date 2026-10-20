# Hansard output structure and downstream Bedrock processing

This guide describes the current parser's JSON and a proposed consumer for it.

## 1. Files and storage units

Each sitting has one raw file and one processed file.
On AWS, these are S3 keys in the buckets named by `RAW_BUCKET` and `PROCESSED_BUCKET`.
A whole sitting's processed
JSON is one object; `segments` are array elements, not separate S3 objects.

| Object | Purpose |
|---|---|
| Raw JSON | Exact source response, original HTML and all reference metadata |
| Processed JSON | Main input for summarisation: cleaned text and source locators |
| Future summary JSON | Separate consumer output; its existence tracks summary completion |

The processed file marks ingestion completion only. It does not mean that a summary
exists. Keep summary output under another prefix or bucket so it cannot be confused
with `processed/sittings/`.

## 2. Top-level processed document

This is an abbreviated example with one
of the sitting's 152 segments shown and source metadata shortened:

```json
{
  "sitting_id": "2026-10-06",
  "sitting_date": "2026-10-06",
  "source": {
    "public_url": "https://sprs.parl.gov.sg/search/#/fullreport?sittingdate=6-10-2026",
    "raw_key": "raw/sittings/2026-10-06.json",
    "sha256": "<64 hexadecimal characters>"
  },
  "metadata": {
    "parlimentNO": 15,
    "sessionNO": 1,
    "volumeNO": 96,
    "sittingDate": "06-10-2026"
  },
  "collection_counts": {
    "takesSectionVOList": 152,
    "vernacularList": 0
  },
  "supporting_collections": {
    "a2bList": []
  },
  "segment_count": 152,
  "segments": [
    {
      "local_segment_id": "2026-10-06/takesSectionVOList/0014",
      "source_position": {"collection": "takesSectionVOList", "index": 14},
      "title": "Digital Infrastructure Bill",
      "subtitle": null,
      "section_type": "BP",
      "report_type": null,
      "question_number": null,
      "content_text": "Order for Second Reading read.\n\nFurther speech text...",
      "source_record": {"content": "<p>Original HTML...</p>"}
    }
  ],
  "warnings": []
}
```

The real object contains all source metadata and supporting records. The braces and
omissions above illustrate the structure; this is not an exact copy of the sitting.

| Field | Meaning and use |
|---|---|
| `sitting_id` | Local sitting identity, currently identical to the ISO date |
| `sitting_date` | `YYYY-MM-DD`; use for selecting a digest's date range |
| `source.public_url` | Human-facing official full-sitting page |
| `source.raw_key` | Key of the original response; raw bucket is configured separately |
| `source.sha256` | SHA-256 of exact raw bytes; record it with derived summaries |
| `metadata` | SPRS metadata with original names, spellings, formats, and nulls |
| `collection_counts` | Source-list counts; includes supporting/PDF references, not only transcript |
| `supporting_collections` | Supporting or unrecognized lists; excludes vernacular references |
| `segment_count` | Exactly the number of entries in `segments` |
| `segments` | Processed transcript records |
| `warnings` | Known limitations requiring inspection before automatic publication |

Note the source spelling `parlimentNO`, and that `metadata.sittingDate` retains
`DD-MM-YYYY` while top-level `sitting_date` is normalized. Do not substitute
`collection_counts` totals for the transcript count.

The parser begins with bytes, decodes them to a payload dictionary, and extracts
from that dictionary. Bytes let the same parser accept fresh HTTP data or a saved
local/S3 object and calculate the exact-source checksum. A different raw-byte
checksum does not automatically prove a substantive content change.

## 3. Individual segments

| Segment field | Meaning |
|---|---|
| `local_segment_id` | Readable local locator: date / source collection / padded index |
| `source_position.collection` | Original list name |
| `source_position.index` | Zero-based position within that list |
| `title`, `subtitle` | Source heading fields; may be null |
| `section_type`, `report_type` | Source category fields; retain nulls and do not guess missing labels |
| `question_number` | Source question-number value; not necessarily an integer |
| `content_text` | Cleaned text to send to the summariser |
| `source_record` | Complete original record, including HTML and any original IDs/footnotes |

A segment can contain a whole debate and multiple speakers. It is not necessarily
one speech, one question, or a model-sized chunk. Text has paragraph breaks and
labels for clarifications/footnotes, but no structured speaker-turn objects.

Titles are not unique. The two Digital Infrastructure Bill segments at indices
14 and 16 on 6 October are distinct and must both be included. Use local IDs rather
than titles for tracking. A local ID is not an official SPRS topic ID and cannot be
inserted into a public topic URL. Use `source.public_url` for the official source.

The output follows source order within each collection and the parser's collection
order across collections. It does not establish a single chronological order across
all categories. IDs based on source position can shift after source reordering;
revision reconciliation is outside the current ingestion scope.

## 4. Vernacular records and other exclusions

The summary scope is the main transcript in English. `vernacularList` contains
references to separate original-language PDFs. In the saved September sittings,
the main transcript links to these PDFs alongside English speech text.

- Vernacular references remain in raw JSON only.
- Their count remains in `collection_counts.vernacularList`.
- They are absent from `segments`, `segment_count`, and `supporting_collections`.
- The pipeline does not download PDFs or emit missing-text warnings for their references.
- Do not fetch these PDFs as additional summary input under the current scope.

The corrected 9 September output has 168 transcript segments and 12 raw PDF references;
10 September has 147 segments and 4 references. Do not reconstruct the old inflated
totals of 180 and 151. Supporting lists such as attendance and annexure references
also do not belong in the default transcript summarisation prompt.

Do not send the whole processed JSON to a model: `source_record` repeats much of the
speech in HTML, and supporting lists add unrelated material. Send selected metadata,
title, ID, and `content_text` for the segment or chunk being summarised.