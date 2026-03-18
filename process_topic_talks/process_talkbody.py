import sqlite3
import zlib
import struct
from bs4 import BeautifulSoup
from typing import Optional, Tuple
import argparse
import sys


class TalkBodyProcessor:
    """Process talkbody data and extract reference IDs."""
    
    def __init__(self, source_db: str, target_db: str):
        """
        Initialize the processor.
        
        Args:
            source_db: Path to source database (content.52.db)
            target_db: Path to target database (topic_content.db)
        """
        self.source_db = source_db
        self.target_db = target_db
        self.source_conn = None
        self.target_conn = None
        self.source_cursor = None
        self.target_cursor = None
    
    def connect_databases(self):
        """Connect to both databases."""
        print(f"📂 Connecting to source database: {self.source_db}")
        self.source_conn = sqlite3.connect(self.source_db)
        self.source_cursor = self.source_conn.cursor()
        
        print(f"📂 Connecting to target database: {self.target_db}")
        self.target_conn = sqlite3.connect(self.target_db)
        self.target_cursor = self.target_conn.cursor()
        
        print("✅ Database connections established")
    
    def create_target_table(self, table_name: str = 'talk_content'):
        """
        Create the target table in topic_content.db.
        
        Args:
            table_name: Name of the table to create
        """
        print(f"\n🔨 Creating table: {table_name}")
        
        self.target_cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                talk_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                content_identifier TEXT,
                UNIQUE(talk_id)
            )
        ''')
        
        # Create index on content_identifier for faster lookups
        self.target_cursor.execute(f'''
            CREATE INDEX IF NOT EXISTS idx_{table_name}_content_identifier
            ON {table_name}(content_identifier)
        ''')
        
        # Create index on talk_id
        self.target_cursor.execute(f'''
            CREATE INDEX IF NOT EXISTS idx_{table_name}_talk_id
            ON {table_name}(talk_id)
        ''')
        
        self.target_conn.commit()
        print("✅ Table created successfully")
    
    def decompress_with_length_prefix(self, data: bytes) -> Optional[str]:
        """
        Decompress data with 4-byte length prefix using raw DEFLATE.
        
        Equivalent to PHP's gzinflate(substr($blob, 4))
        - Skip first 4 bytes (length prefix)
        - Decompress using raw DEFLATE (no zlib header/trailer)
        
        Args:
            data: Compressed data with length prefix
        
        Returns:
            Decompressed string or None if decompression fails
        """
        if not data or len(data) < 4:
            return None
        
        try:
            # Skip the first 4 bytes (length prefix)
            compressed_data = data[4:]
            
            # Decompress using raw DEFLATE (gzinflate equivalent)
            # -zlib.MAX_WBITS tells zlib to use raw DEFLATE without headers
            decompressed = zlib.decompress(compressed_data, -zlib.MAX_WBITS)
            
            # Decode to string
            return decompressed.decode('utf-8', errors='ignore')
            
        except Exception as e:
            print(f"    ❌ Decompression error: {str(e)}")
            return None
    
    def extract_data_aid(self, html: str) -> Optional[str]:
        """
        Extract data-aid attribute from h1 tag in HTML.
        
        Args:
            html: HTML string
        
        Returns:
            data-aid value or None if not found
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            h1_tag = soup.find('h1', attrs={'data-aid': True})
            
            if h1_tag and 'data-aid' in h1_tag.attrs:
                return h1_tag['data-aid']
            
            return None
            
        except Exception as e:
            print(f"    ❌ HTML parsing error: {str(e)}")
            return None
    
    def process_talk_body_row(self, talk_id: int, compressed_text: bytes) -> Tuple[Optional[str], Optional[str]]:
        """
        Process a single row from talkbody table.
        
        Args:
            talk_id: TalkID from the source table
            compressed_text: Compressed Text data
        
        Returns:
            Tuple of (decompressed_text, content_identifier)
        """
        # Decompress the text
        decompressed_text = self.decompress_with_length_prefix(compressed_text)
        
        if not decompressed_text:
            return None, None
        
        # Extract data-aid (content_identifier)
        content_identifier = self.extract_data_aid(decompressed_text)
        
        return decompressed_text, content_identifier
    
    def insert_talk_content(self, table_name: str, talk_id: int, text: str, content_identifier: Optional[str]):
        """
        Insert processed data into target table.
        
        Args:
            table_name: Name of the target table
            talk_id: TalkID
            text: Decompressed text
            content_identifier: Extracted data-aid value
        """
        try:
            self.target_cursor.execute(f'''
                INSERT INTO {table_name} (talk_id, text, content_identifier)
                VALUES (?, ?, ?)
                ON CONFLICT(talk_id) DO UPDATE SET
                    text = excluded.text,
                    content_identifier = excluded.content_identifier
            ''', (talk_id, text, content_identifier))
        except sqlite3.Error as e:
            print(f"    ❌ Database insert error for TalkID {talk_id}: {str(e)}")
    
    def process_all_talks(self, table_name: str = 'talk_content'):
        """
        Process all rows from talkbody table.
        
        Args:
            table_name: Name of the target table
        """
        print(f"\n{'='*60}")
        print("Processing talkbody rows")
        print(f"{'='*60}\n")
        
        # Get total count
        self.source_cursor.execute('SELECT COUNT(*) FROM talkbody')
        total_rows = self.source_cursor.fetchone()[0]
        print(f"Total rows to process: {total_rows}\n")
        
        # Fetch all rows
        self.source_cursor.execute('SELECT TalkID, Text FROM talkbody')
        
        processed = 0
        successful = 0
        with_content_identifier = 0
        errors = 0
        
        for talk_id, compressed_text in self.source_cursor.fetchall():
            processed += 1
            
            if processed % 100 == 0:
                print(f"  Processed {processed}/{total_rows} rows...")
            
            # Process the row
            text, content_identifier = self.process_talk_body_row(talk_id, compressed_text)
            
            if text:
                self.insert_talk_content(table_name, talk_id, text, content_identifier)
                successful += 1
                
                if content_identifier:
                    with_content_identifier += 1
            else:
                errors += 1
                print(f"    ❌ Failed to process TalkID: {talk_id}")
        
        # Commit all inserts
        self.target_conn.commit()
        
        print(f"\n{'='*60}")
        print("✅ PROCESSING COMPLETE!")
        print(f"{'='*60}")
        print(f"Total rows processed: {processed}")
        print(f"Successfully decompressed: {successful}")
        print(f"With content_identifier extracted: {with_content_identifier}")
        print(f"Errors: {errors}")
        
        if successful > 0:
            print(f"Reference ID extraction rate: {with_content_identifier/successful*100:.1f}%")
    
    def print_statistics(self, table_name: str = 'talk_content'):
        """Print statistics about the target table."""
        print(f"\n{'='*60}")
        print(f"📊 DATABASE STATISTICS - {table_name}")
        print(f"{'='*60}")
        
        # Total rows
        self.target_cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
        total = self.target_cursor.fetchone()[0]
        print(f"\nTotal rows: {total}")
        
        # Rows with content_identifier
        self.target_cursor.execute(f'SELECT COUNT(*) FROM {table_name} WHERE content_identifier IS NOT NULL')
        with_ref = self.target_cursor.fetchone()[0]
        print(f"Rows with content_identifier: {with_ref}")
        
        # Rows without content_identifier
        print(f"Rows without content_identifier: {total - with_ref}")
        
        if total > 0:
            print(f"Reference ID coverage: {with_ref/total*100:.1f}%")
        
        # Sample data
        print(f"\nSample rows:")
        self.target_cursor.execute(f'''
            SELECT talk_id, content_identifier, LENGTH(text) as text_length
            FROM {table_name}
            LIMIT 5
        ''')
        
        for talk_id, ref_id, text_len in self.target_cursor.fetchall():
            ref_display = ref_id if ref_id else "NULL"
            print(f"  TalkID: {talk_id}, ReferenceID: {ref_display}, Text length: {text_len} chars")
    
    def close(self):
        """Close database connections."""
        if self.source_conn:
            self.source_conn.close()
        if self.target_conn:
            self.target_conn.close()
        print(f"\n✅ Database connections closed")


def main():
    parser = argparse.ArgumentParser(
        description='Process talkbody data from content.52.db and create topic_content.db',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Basic usage with default settings
  python process_talkbody.py
  
  # Custom database paths
  python process_talkbody.py --source my_content.db --target my_output.db
  
  # Custom table name
  python process_talkbody.py --table custom_talk_content
        '''
    )
    
    parser.add_argument(
        '--source', '-s',
        type=str,
        default='content.52.db',
        help='Source database path (default: content.52.db)'
    )
    
    parser.add_argument(
        '--target', '-t',
        type=str,
        default='topic_content.db',
        help='Target database path (default: topic_content.db)'
    )
    
    parser.add_argument(
        '--table',
        type=str,
        default='talk_content',
        help='Target table name (default: talk_content)'
    )
    
    args = parser.parse_args()
    
    print("="*60)
    print("TalkBody Processor")
    print("="*60)
    print(f"Source: {args.source}")
    print(f"Target: {args.target}")
    print(f"Table: {args.table}")
    print("="*60)
    
    # Initialize processor
    processor = TalkBodyProcessor(
        source_db=args.source,
        target_db=args.target
    )
    
    try:
        # Connect to databases
        processor.connect_databases()
        
        # Create target table
        processor.create_target_table(table_name=args.table)
        
        # Process all talks
        processor.process_all_talks(table_name=args.table)
        
        # Print statistics
        processor.print_statistics(table_name=args.table)
        
    except FileNotFoundError as e:
        print(f"\n❌ Error: Database file not found - {str(e)}")
        sys.exit(1)
    except sqlite3.DatabaseError as e:
        print(f"\n❌ Database error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Close connections
        processor.close()
    
    print("\n" + "="*60)
    print("Example queries:")
    print("="*60)
    print(f"sqlite3 {args.target}")
    print(f"  SELECT * FROM {args.table} LIMIT 5;")
    print(f"  SELECT COUNT(*) FROM {args.table} WHERE reference_id IS NOT NULL;")
    print(f"  SELECT talk_id, reference_id FROM {args.table} WHERE reference_id LIKE '%search%';")


if __name__ == "__main__":
    main()
