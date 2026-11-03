# Scripture corpus audit

## Real fetch (I2)

- Date: 2026-11-02
- Command: `scripts/fetch_scriptures.py --db db/scripture.db` (resumed once with `--only-missing`)
- Pages stored (`raw_latest` rows): 1812 (6 TOC pages + 1806 linked pages, 0 failed)
- File size: 77,152,256 bytes (74 MiB)
- Duration: about 17 min 12 s (570 s timed-out first chunk + 462 s resume chunk)
