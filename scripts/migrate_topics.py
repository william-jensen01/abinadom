import sqlite3
import argparse
import sys


class TableMigrator:
    """Migrate topics table from one database to another."""
    
    def __init__(self, source_db: str, target_db: str):
        """
        Initialize the migrator.
        
        Args:
            source_db: Source database path (topic_content.db)
            target_db: Target database path (core.52.db)
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
        try:
            self.source_conn = sqlite3.connect(self.source_db)
            self.source_cursor = self.source_conn.cursor()
        except sqlite3.Error as e:
            print(f"❌ Error connecting to source database: {e}")
            sys.exit(1)
        
        print(f"📂 Connecting to target database: {self.target_db}")
        try:
            self.target_conn = sqlite3.connect(self.target_db)
            self.target_cursor = self.target_conn.cursor()
        except sqlite3.Error as e:
            print(f"❌ Error connecting to target database: {e}")
            sys.exit(1)
        
        print("✅ Database connections established")
    
    def get_table_schema(self, table_name: str) -> str:
        """
        Get the CREATE TABLE statement for a table.
        
        Args:
            table_name: Name of the table
        
        Returns:
            CREATE TABLE SQL statement
        """
        self.source_cursor.execute(f'''
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name=?
        ''', (table_name,))
        
        result = self.source_cursor.fetchone()
        if result:
            return result[0]
        return None
    
    def get_table_indexes(self, table_name: str) -> list:
        """
        Get all index CREATE statements for a table.
        
        Args:
            table_name: Name of the table
        
        Returns:
            List of CREATE INDEX SQL statements
        """
        self.source_cursor.execute(f'''
            SELECT sql FROM sqlite_master 
            WHERE type='index' AND tbl_name=? AND sql IS NOT NULL
        ''', (table_name,))
        
        return [row[0] for row in self.source_cursor.fetchall()]
    
    def table_exists(self, table_name: str) -> bool:
        """
        Check if table exists in target database.
        
        Args:
            table_name: Name of the table
        
        Returns:
            True if table exists, False otherwise
        """
        self.target_cursor.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        ''', (table_name,))
        
        return self.target_cursor.fetchone() is not None
    
    def create_table_in_target(self, table_name: str, drop_if_exists: bool = False):
        """
        Create the table in target database.
        
        Args:
            table_name: Name of the table to create
            drop_if_exists: If True, drop existing table first
        """
        print(f"\n🔨 Creating table: {table_name}")
        
        # Check if table exists
        exists = self.table_exists(table_name)
        
        if exists:
            if drop_if_exists:
                print(f"⚠️  Table '{table_name}' exists in target. Dropping...")
                self.target_cursor.execute(f'DROP TABLE IF EXISTS {table_name}')
                self.target_conn.commit()
            else:
                print(f"⚠️  Table '{table_name}' already exists in target database.")
                response = input("Do you want to drop and recreate it? (yes/no): ")
                if response.lower() in ['yes', 'y']:
                    self.target_cursor.execute(f'DROP TABLE IF EXISTS {table_name}')
                    self.target_conn.commit()
                else:
                    print("Skipping table creation. Will update existing rows.")
                    return
        
        # Get schema from source
        schema = self.get_table_schema(table_name)
        if not schema:
            print(f"❌ Table '{table_name}' not found in source database!")
            sys.exit(1)
        
        # Create table
        self.target_cursor.execute(schema)
        self.target_conn.commit()
        print(f"✅ Table created successfully")
        
        # Create indexes
        indexes = self.get_table_indexes(table_name)
        if indexes:
            print(f"🔨 Creating {len(indexes)} indexes...")
            for index_sql in indexes:
                self.target_cursor.execute(index_sql)
            self.target_conn.commit()
            print(f"✅ Indexes created successfully")
    
    def copy_table_data(self, table_name: str):
        """
        Copy all data from source table to target table.
        
        Args:
            table_name: Name of the table to copy
        """
        print(f"\n📊 Copying data from {table_name}...")
        
        # Get column names
        self.source_cursor.execute(f'PRAGMA table_info({table_name})')
        columns = [row[1] for row in self.source_cursor.fetchall()]
        column_list = ', '.join(columns)
        placeholders = ', '.join(['?' for _ in columns])
        
        # Count rows in source
        self.source_cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
        total_rows = self.source_cursor.fetchone()[0]
        print(f"Total rows to copy: {total_rows}")
        
        # Fetch all data
        self.source_cursor.execute(f'SELECT {column_list} FROM {table_name}')
        rows = self.source_cursor.fetchall()
        
        # Insert into target
        if rows:
            # Use INSERT OR REPLACE to handle potential conflicts
            self.target_cursor.executemany(
                f'INSERT OR REPLACE INTO {table_name} ({column_list}) VALUES ({placeholders})',
                rows
            )
            self.target_conn.commit()
            print(f"✅ Copied {len(rows)} rows successfully")
        else:
            print("⚠️  No rows to copy")
    
    def verify_migration(self, table_name: str):
        """
        Verify the migration was successful.
        
        Args:
            table_name: Name of the table to verify
        """
        print(f"\n🔍 Verifying migration...")
        
        # Count rows in source
        self.source_cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
        source_count = self.source_cursor.fetchone()[0]
        
        # Count rows in target
        self.target_cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
        target_count = self.target_cursor.fetchone()[0]
        
        print(f"Source rows: {source_count}")
        print(f"Target rows: {target_count}")
        
        if source_count == target_count:
            print("✅ Migration verified successfully!")
        else:
            print("⚠️  Warning: Row counts don't match!")
        
        # Show sample data
        print(f"\nSample data from target database:")
        self.target_cursor.execute(f'SELECT * FROM {table_name} LIMIT 3')
        rows = self.target_cursor.fetchall()
        
        # Get column names
        self.target_cursor.execute(f'PRAGMA table_info({table_name})')
        columns = [row[1] for row in self.target_cursor.fetchall()]
        
        for row in rows:
            print(f"  {dict(zip(columns, row))}")
    
    def close(self):
        """Close database connections."""
        if self.source_conn:
            self.source_conn.close()
        if self.target_conn:
            self.target_conn.close()
        print(f"\n✅ Database connections closed")


def main():
    parser = argparse.ArgumentParser(
        description='Migrate topics table from topic_content.db to core.52.db',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Basic usage
  python migrate_topics.py
  
  # Custom database paths
  python migrate_topics.py --source topic_content.db --target core.52.db
  
  # Custom table name
  python migrate_topics.py --table custom_topics
  
  # Force drop and recreate (no prompts)
  python migrate_topics.py --force
        '''
    )
    
    parser.add_argument(
        '--source', '-s',
        type=str,
        default='topic_content.db',
        help='Source database path (default: topic_content.db)'
    )
    
    parser.add_argument(
        '--target', '-t',
        type=str,
        default='core.52.db',
        help='Target database path (default: core.52.db)'
    )
    
    parser.add_argument(
        '--table',
        type=str,
        default='topic',
        help='Table name to migrate (default: topic)'
    )
    
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force drop and recreate table without prompting'
    )
    
    args = parser.parse_args()
    
    print("="*60)
    print("Table Migration Tool")
    print("="*60)
    print(f"Source: {args.source}")
    print(f"Target: {args.target}")
    print(f"Table: {args.table}")
    print("="*60)
    
    # Initialize migrator
    migrator = TableMigrator(
        source_db=args.source,
        target_db=args.target
    )
    
    try:
        # Connect to databases
        migrator.connect_databases()
        
        # Create table in target
        migrator.create_table_in_target(
            table_name=args.table,
            drop_if_exists=args.force
        )
        
        # Copy data
        migrator.copy_table_data(table_name=args.table)
        
        # Verify migration
        migrator.verify_migration(table_name=args.table)
        
        print("\n" + "="*60)
        print("✅ MIGRATION COMPLETE!")
        print("="*60)
        
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
        migrator.close()


if __name__ == "__main__":
    main()
