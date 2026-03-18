-- Common SQL Queries for Content Database
-- =========================================

-- View all topics
SELECT * FROM topics;

-- View all topics with their reference counts
SELECT 
    t.topic_name,
    t.total_entries,
    t.successful_extractions,
    COUNT(cr.reference_id) as reference_count
FROM topics t
LEFT JOIN content_references cr ON t.topic_id = cr.topic_id
GROUP BY t.topic_id
ORDER BY reference_count DESC;

-- Get all content references for a specific topic
SELECT 
    cr.content_identifier,
    cr.entry_title,
    cr.entry_uri
FROM content_references cr
JOIN topics t ON cr.topic_id = t.topic_id
WHERE t.topic_name = 'Priesthood'
ORDER BY cr.entry_index;

-- Search for a specific content identifier
SELECT 
    t.topic_name,
    cr.content_identifier,
    cr.entry_title,
    cr.entry_uri
FROM content_references cr
JOIN topics t ON cr.topic_id = t.topic_id
WHERE cr.content_identifier = 'your-content-id-here';

-- Find all topics that contain a specific content identifier
SELECT DISTINCT
    t.topic_name,
    t.total_entries
FROM topics t
JOIN content_references cr ON t.topic_id = cr.topic_id
WHERE cr.content_identifier LIKE '%search-term%';

-- Get topics with highest success rates
SELECT 
    topic_name,
    total_entries,
    successful_extractions,
    ROUND(CAST(successful_extractions AS FLOAT) / total_entries * 100, 2) as success_rate
FROM topics
WHERE total_entries > 0
ORDER BY success_rate DESC;

-- Find duplicate content identifiers across topics
SELECT 
    cr.content_identifier,
    COUNT(DISTINCT cr.topic_id) as topic_count,
    GROUP_CONCAT(DISTINCT t.topic_name, ', ') as topics
FROM content_references cr
JOIN topics t ON cr.topic_id = t.topic_id
GROUP BY cr.content_identifier
HAVING topic_count > 1
ORDER BY topic_count DESC;

-- Get all content for a topic with entry details
SELECT 
    cr.entry_index,
    cr.content_identifier,
    cr.entry_title,
    cr.entry_uri,
    cr.extracted_at
FROM content_references cr
JOIN topics t ON cr.topic_id = t.topic_id
WHERE t.topic_name = 'Priesthood'
ORDER BY cr.entry_index;

-- Count content references by topic
SELECT 
    t.topic_name,
    COUNT(cr.reference_id) as content_count
FROM topics t
LEFT JOIN content_references cr ON t.topic_id = cr.topic_id
GROUP BY t.topic_id, t.topic_name
ORDER BY content_count DESC;

-- Find topics updated recently
SELECT 
    topic_name,
    successful_extractions,
    updated_at
FROM topics
ORDER BY updated_at DESC
LIMIT 10;

-- Get topics with no content references (potential errors)
SELECT 
    t.topic_name,
    t.total_entries,
    t.successful_extractions
FROM topics t
LEFT JOIN content_references cr ON t.topic_id = cr.topic_id
GROUP BY t.topic_id
HAVING COUNT(cr.reference_id) = 0;

-- Full join showing topic and all its content
SELECT 
    t.topic_name,
    cr.content_identifier,
    cr.entry_title,
    cr.entry_index,
    cr.extracted_at
FROM topics t
LEFT JOIN content_references cr ON t.topic_id = cr.topic_id
ORDER BY t.topic_name, cr.entry_index;

-- Export content identifiers for a topic as CSV
.mode csv
.output priesthood_content.csv
SELECT 
    cr.content_identifier,
    cr.entry_title,
    cr.entry_uri
FROM content_references cr
JOIN topics t ON cr.topic_id = t.topic_id
WHERE t.topic_name = 'Priesthood'
ORDER BY cr.entry_index;
.output stdout
.mode list
