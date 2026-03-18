-- One-off migration to add decompressed/projection columns to talkbody
-- Run this once before running the backfill scripts to avoid IDE/schema warnings.
-- Safe to run multiple times: each statement is wrapped to skip if the column exists.

-- SQLite (older versions) do not support ALTER TABLE ... ADD COLUMN IF NOT EXISTS,
-- so we emulate it using PRAGMA table_info and a conditional.

-- Add TextRaw
WITH cols AS (
  SELECT name FROM pragma_table_info('talkbody')
)
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM cols WHERE name = 'TextRaw') THEN
  (SELECT sql FROM (
     SELECT 'ALTER TABLE talkbody ADD COLUMN TextRaw TEXT' AS sql
  ))
END;

-- Add TextSimple
WITH cols AS (
  SELECT name FROM pragma_table_info('talkbody')
)
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM cols WHERE name = 'TextSimple') THEN
  (SELECT sql FROM (
     SELECT 'ALTER TABLE talkbody ADD COLUMN TextSimple TEXT' AS sql
  ))
END;

-- Add TextMinimal
WITH cols AS (
  SELECT name FROM pragma_table_info('talkbody')
)
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM cols WHERE name = 'TextMinimal') THEN
  (SELECT sql FROM (
     SELECT 'ALTER TABLE talkbody ADD COLUMN TextMinimal TEXT' AS sql
  ))
END;

-- Add TextEnhanced
WITH cols AS (
  SELECT name FROM pragma_table_info('talkbody')
)
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM cols WHERE name = 'TextEnhanced') THEN
  (SELECT sql FROM (
     SELECT 'ALTER TABLE talkbody ADD COLUMN TextEnhanced TEXT' AS sql
  ))
END;

-- NOTE: Some SQLite shells won't automatically execute the returned SQL strings.
-- If using the default sqlite3 CLI, simply run the four ALTER TABLE statements below instead:
--   ALTER TABLE talkbody ADD COLUMN TextRaw TEXT;
--   ALTER TABLE talkbody ADD COLUMN TextSimple TEXT;
--   ALTER TABLE talkbody ADD COLUMN TextMinimal TEXT;
--   ALTER TABLE talkbody ADD COLUMN TextEnhanced TEXT;
