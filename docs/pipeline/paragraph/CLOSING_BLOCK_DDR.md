No special handling for div.closingBlockContainer, treat as bare text.
Structure: closing (salutation) + one or more signature divs + office div.
Example: "Sincerely yours, Spencer W. Kimball N. Eldon Tanner ... The First Presidency"

**Options considered:**

- New source_type "closing" with newline-preserved formatting (closing\nsigs\noffice)
- Skip entirely (too aggressive — loses completeness)
- Extract as-is via bare fallback (chosen)

**Rationale:**

The text is embedded in ChromaDB where newlines vs spaces don't affect vector similarity. A dedicated source_type adds complexity without meaningful retrieval benefit. The flat "bare" text is complete and correct.

---

Good question. Let me think about this from the ChromaDB/semantic search perspective.

**What ChromaDB cares about:** The text gets embedded for similarity search. The embedding model sees the text as a flat string — newlines vs spaces vs pipes are all just tokens. What matters is:

1. The text is **semantically meaningful** as a standalone chunk
2. The text is **distinguishable** from regular paragraph content (via `source_type` metadata filtering)

**What doesn't matter much:**

- Newline preservation — embeddings don't meaningfully differentiate `\n` from ` `. The "table carve-out" exists for human readability in debug/export, not for embedding quality.
- Pipe vs comma vs newline between signatures — negligible impact on vector similarity.

**What I'm leaning towards:**

**Skip the new source_type.** A closing block isn't something users will semantically search for ("find me the talk signed by Spencer W. Kimball"). It's structural metadata, not content. It's similar to how `should_skip_element` already skips headers and nav — closing blocks are boilerplate.

The strongest option is actually the one we didn't discuss yet: **skip it entirely** via `should_skip_element`. The closing block adds noise to the paragraph list without adding searchable content.

**But** — if you want it preserved for completeness (e.g., Phase 6 metadata extraction might want to know who signed a letter), then the simplest path is:

- Add a `"closing"` source_type handler
- Flatten the text simply (no fancy pipe-joining needed — just `_element_clean_text` which gives `"Sincerely yours, Spencer W. Kimball N. Eldon Tanner Marion G. Romney The First Presidency"`)
- The `source_type: "closing"` tag lets Phase 6 or downstream consumers identify and handle it specially

So: **skip it** if it's noise, or **extract with `source_type: "closing"` + flat text** if downstream phases need it. Which way are you leaning?
