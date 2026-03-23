import json
import sqlite3
import argparse
from typing import List, Dict, Optional


class DatabaseBuilder:
    """Build SQLite database from topics and data-aids."""

    def __init__(self, db_path: str = "topic.db", core_db_path: str = "core.db"):
        """
        Initialize database builder.

        Args:
            db_path: Path to SQLite database file
            core_db_path: Path to core.db for looking up talk IDs
        """
        self.db_path = db_path
        self.core_db_path = core_db_path
        self.conn = None
        self.cursor = None
        self.core_conn = None
        self.core_cursor = None

    def connect(self):
        """Connect to SQLite database."""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        print(f"📁 Connected to database: {self.db_path}")

        # Connect to core.db for talk ID lookups
        try:
            self.core_conn = sqlite3.connect(self.core_db_path)
            self.core_cursor = self.core_conn.cursor()
            print(f"📁  Connected to core database: {self.core_db_path}")
        except sqlite3.Error as e:
            print(f"⚠️  Warning: Could not connect to core database: {e}")
            print(f"    Will proceed without talk_id lookups")
            self.core_conn = None
            self.core_cursor = None

    def create_tables(self):
        """Create database tables."""
        print("🔨 Creating tables...")

        # Topic table
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS topic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                topicId TEXT NOT NULL UNIQUE
            )
        """
        )

        # Content references table (stores the URIs and talk IDs)
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS content_references (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                talk_id INTEGER NOT NULL,
                content_identifier TEXT NOT NULL,
                FOREIGN KEY (topic_id) REFERENCES topic (id),
                UNIQUE(topic_id, content_identifier)
            )
        """
        )

        # Create indexes for better query performance
        self.cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_content_topic 
            ON content_references(topic_id)
        """
        )

        self.cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_content_identifier 
            ON content_references(content_identifier)
        """
        )

        self.cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_talk_id
            ON content_references(talk_id)
            """
        )

        self.cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_topic_id
            ON topic(topicId)
        """
        )

        self.conn.commit()
        print("✅ Tables created successfully")

    def load_json_data(
        self, filename: str = "../process_topic_talks/results.json"
    ) -> List[Dict]:
        """Load data from JSON file."""
        with open(filename, "r") as f:
            return json.load(f)

    def generate_topic_id(self, topic_name: str) -> str:
        """
        Generate a cleaned topicId from topic_name.
        Converts to lowercase and replaces with hypens.

        Args:
            topic_name: Original topic name

        Returns:
            Cleaned topic ID (e.g., "Book of Mormon" -> "book-of-mormon")
        """
        return topic_name.lower().replace(" ", "-")

    def lookup_talk_id(self, uri: str) -> Optional[int]:
        """
        Look up talk_id from core.db using talk_metadata.uri_gc.

        Args:
            uri: URI to look up

        Returns:
            TalkID if found, None otherwise
        """
        if not self.core_cursor:
            return None

        try:
            self.core_cursor.execute(
                """
                SELECT t.ID FROM talk t
                JOIN talk_metadata tm ON t.ID = tm.talk_id
                WHERE tm.uri_gc = ?
            """,
                (uri,),
            )
            result = self.core_cursor.fetchone()
            return result[0] if result else None
        except sqlite3.Error:
            return None

    def insert_topic(self, topic_name: str) -> int:
        """
        Insert or update a topic and return its ID.

        Args:
            topic_name: Name of the topic

        Returns:
            id of the inserted/updated topic
        """
        topic_id = self.generate_topic_id(topic_name)

        # Try to insert, if exists, just ignore
        self.cursor.execute(
            """
            INSERT INTO topic (name, topicId)
            VALUES (?, ?)
            ON CONFLICT(name) DO NOTHING
        """,
            (topic_name, topic_id),
        )

        # Get the id
        self.cursor.execute("SELECT id FROM topic WHERE name = ?", (topic_name,))
        return self.cursor.fetchone()[0]

    def insert_content_reference(self, topic_id: int, uri: str, talk_id: Optional[int]):
        """
        Insert a content reference (data-aid).

        Args:
            topic_id: ID of the topic this content belongs to
            uri: The URI (used as content_identifier)
            talk_id: TalkID from core.db lookup
        """
        try:
            self.cursor.execute(
                """
                INSERT INTO content_references 
                (topic_id, talk_id, content_identifier)
                VALUES (?, ?, ?)
                ON CONFLICT(topic_id, content_identifier) DO NOTHING
            """,
                (
                    topic_id,
                    talk_id,
                    uri,
                ),
            )
        except sqlite3.IntegrityError as e:
            # Duplicate, skip
            print(f"    ⚠️  Integrity error for URI {uri}: {e}")
            pass

    def populate_database(self, data: List[Dict]):
        """
        Populate database from JSON data.

        Args:
            data: List of topic dictionaries with data_aids
        """
        print("\n📊 Populating database...")

        total_topics = 0
        total_references = 0
        total_with_talk_id = 0

        for topic_data in data:
            topic_name = topic_data.get("topic", "Unknown")
            entries = topic_data.get("entries", [])

            print(f"\n  Processing: {topic_name}")
            print(f"    Entries: {len(entries)}")

            # Insert topic
            topic_id = self.insert_topic(topic_name)
            total_topics += 1

            # Insert content references
            entries_with_talk_id = 0
            for entry in entries:
                uri = entry.get("uri", "")
                if not uri:
                    continue

                # Look up talk_id from core.db
                talk_id = self.lookup_talk_id(uri)
                if talk_id:
                    entries_with_talk_id += 1
                    total_with_talk_id += 1

                self.insert_content_reference(
                    topic_id=topic_id, uri=uri, talk_id=talk_id
                )
                total_references += 1

            print(f"    ✅ Added {len(entries)} content references")
            if self.core_cursor:
                print(
                    f"    📊 Found talk_id for {entries_with_talk_id}/{len(entries)} entries"
                )

        self.conn.commit()

        print(f"\n{'='*60}")
        print(f"✅ Database population complete!")
        print(f"{'='*60}")
        print(f"Total topics: {total_topics}")
        print(f"Total content references: {total_references}")

    def print_statistics(self):
        """Print database statistics."""
        print(f"\n{'='*60}")
        print(f"📈 DATABASE STATISTICS")
        print(f"{'='*60}")

        # Total topics
        self.cursor.execute("SELECT COUNT(*) FROM topic")
        total_topics = self.cursor.fetchone()[0]
        print(f"\nTotal topics: {total_topics}")

        # Total content references
        self.cursor.execute("SELECT COUNT(*) FROM content_references")
        total_refs = self.cursor.fetchone()[0]
        print(f"Total content references: {total_refs}")

        # References with talk_id
        self.cursor.execute(
            "SELECT COUNT(*) FROM content_references WHERE talk_id IS NOT NULL"
        )
        with_talk_id = self.cursor.fetchone()[0]
        print(
            f"References with talk_id: {with_talk_id} ({with_talk_id/max(total_refs,1)*100:.1f}%)"
        )

        # References per topic
        print(f"\nContent references by topic:")
        self.cursor.execute(
            """
            SELECT t.name, COUNT(cr.id) as ref_count
            FROM topic t
            LEFT JOIN content_references cr ON t.id = cr.topic_id
            GROUP BY t.id, t.name
            ORDER BY ref_count DESC
        """
        )

        for topic_name, ref_count in self.cursor.fetchall():
            print(f"  {topic_name}: {ref_count} references")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            print(f"\n✅ Database saved: {self.db_path}")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Build SQLite database from topics and content identifiers"
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="../process_topic_talks/results.json",
        help="Input JSON file with topics and data-aids (default: results.json)",
    )
    parser.add_argument(
        "--core-db",
        "-c",
        type=str,
        default="../db/core.db",
        help="Path to core.db (default: ../db/core.db)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="topic.db",
        help="Output SQLite database file (default: topic.db)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop existing tables and recreate (default: update existing)",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    print("=" * 60)
    print("SQLite Database Builder")
    print("=" * 60)

    # Initialize database builder
    db_builder = DatabaseBuilder(db_path=args.output, core_db_path=args.core_db)

    try:
        # Connect to database
        db_builder.connect()

        # Drop tables if recreate flag is set
        if args.recreate:
            print("🗑️  Dropping existing tables...")
            db_builder.cursor.execute("DROP TABLE IF EXISTS content_references")
            db_builder.cursor.execute("DROP TABLE IF EXISTS topic")
            db_builder.conn.commit()

        # Create tables
        db_builder.create_tables()

        # Load JSON data
        print(f"\n📂 Loading data from {args.input}...")
        try:
            data = db_builder.load_json_data(args.input)
            print(f"✅ Loaded {len(data)} topics")
        except FileNotFoundError:
            print(f"❌ Error: File '{args.input}' not found!")
            print("Make sure you've run process_entries.py first.")
            return
        except json.JSONDecodeError:
            print(f"❌ Error: File '{args.input}' is not valid JSON!")
            return

        # Populate database
        db_builder.populate_database(data)

        # Print statistics
        db_builder.print_statistics()

    finally:
        # Close connection
        db_builder.close()

    print("\n" + "=" * 60)
    print("Example queries:")
    print("=" * 60)
    print(f"sqlite3 {args.output}")
    print("  SELECT * FROM topic;")
    print("  SELECT * FROM content_references WHERE topic_id = 1;")
    print("  SELECT t.topic_name, cr.content_identifier")
    print("    FROM topic t")
    print("    JOIN content_references cr ON t.topic_id = cr.topic_id")
    print("    LIMIT 10;")


if __name__ == "__main__":
    main()
