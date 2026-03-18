#!/usr/bin/env python3
"""
Cache Manager for requests-cache

This script provides a command-line interface to interact with caches
created by the requests-cache library using its official API.
"""

import argparse
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import re

try:
    from requests_cache import CachedSession
except ImportError:
    print("Error: requests-cache library not found.", file=sys.stderr)
    print("Install with: pip install requests-cache", file=sys.stderr)
    sys.exit(1)


class CacheManager:
    """Manage requests-cache using the official API"""

    def __init__(self, cache_name: str = "http_cache"):
        """Initialize cache manager with cache name"""
        self.cache_name = cache_name
        self.session = CachedSession(cache_name)

    def info(self) -> None:
        """Display cache information"""
        try:
            cache = self.session.cache

            print(f"\n{'='*70}")
            print(f"Cache Information: {self.cache_name}")
            print(f"{'='*70}\n")

            # Get total count
            total_count = cache.count(expired=True)
            print(f"Total cached entries: {total_count}")

            if total_count == 0:
                print("\nCache is empty.")
                return

            # Count valid vs expired
            valid_count = cache.count(expired=False)
            expired_count = total_count - valid_count

            print(f"Valid entries: {valid_count}")
            print(f"Expired entries: {expired_count}")

            # Get database size (SQLite backend)
            db_path = Path(f"{self.cache_name}.sqlite")
            if db_path.exists():
                size_mb = db_path.stat().st_size / (1024 * 1024)
                print(f"\nDatabase size: {size_mb:.2f} MB")

            # Get date range by iterating responses
            all_responses = list(cache.responses.values())
            if all_responses:
                dates = [
                    r.created_at for r in all_responses
                    if hasattr(r, 'created_at') and r.created_at
                ]
                if dates:
                    print(f"\nDate range:")
                    print(f"  Oldest: {min(dates).strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"  Newest: {max(dates).strftime('%Y-%m-%d %H:%M:%S')}")

                # Count by status code
                status_codes = {}
                for response in all_responses:
                    code = response.status_code
                    status_codes[code] = status_codes.get(code, 0) + 1

                if status_codes:
                    print(f"\nStatus code distribution:")
                    for code in sorted(status_codes.keys()):
                        print(f"  {code}: {status_codes[code]} entries")

            print()

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def list_urls(self, limit: int = 20) -> None:
        """List cached URLs"""
        try:
            cache = self.session.cache

            # Get sorted responses (newest first)
            responses = cache.sorted(key='created_at', reversed=True, limit=limit)

            if not responses:
                print("No cached entries found.")
                return

            total_count = cache.count(expired=True)

            print(f"\n{'='*80}")
            print(f"Cached URLs (showing {len(responses)} of {total_count} total)")
            print(f"{'='*80}\n")

            for idx, response in enumerate(responses, 1):
                url = response.url

                # Format creation date
                if hasattr(response, 'created_at') and response.created_at:
                    created = response.created_at.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    created = "N/A"

                # Check expiration status
                if hasattr(response, 'is_expired'):
                    status = "EXPIRED" if response.is_expired else "Valid"
                else:
                    status = "Unknown"

                print(f"{idx}. {url}")
                print(f"   Status: {response.status_code} | Created: {created} | {status}")
                print()

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def search(self, pattern: str) -> None:
        """Search for URLs matching pattern"""
        try:
            cache = self.session.cache

            # Compile regex pattern
            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                print(f"Invalid regex pattern: {e}", file=sys.stderr)
                return

            # Iterate through all responses and filter
            matches = []
            for cache_key, response in cache.responses.items():
                if regex.search(response.url):
                    matches.append((cache_key, response))

            if not matches:
                print(f"No URLs found matching pattern: {pattern}")
                return

            print(f"\n{'='*80}")
            print(f"Found {len(matches)} URL(s) matching '{pattern}'")
            print(f"{'='*80}\n")

            for idx, (cache_key, response) in enumerate(matches, 1):
                if hasattr(response, 'created_at') and response.created_at:
                    created = response.created_at.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    created = "N/A"

                status = "EXPIRED" if (hasattr(response, 'is_expired') and response.is_expired) else "Valid"

                print(f"{idx}. {response.url}")
                print(f"   Cache Key: {cache_key}")
                print(f"   Status: {response.status_code} | Created: {created} | {status}")
                print()

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def get_details(self, url_pattern: str) -> None:
        """Get and display cached request details"""
        try:
            cache = self.session.cache

            # Find matching response
            matches = []
            for cache_key, response in cache.responses.items():
                if url_pattern.lower() in response.url.lower():
                    matches.append((cache_key, response))

            if not matches:
                print(f"No cached entry found for pattern: {url_pattern}")
                return

            if len(matches) > 1:
                print(f"Found {len(matches)} matching entries. Showing first match.")
                print("Use a more specific pattern to narrow down.\n")

            cache_key, response = matches[0]

            print(f"\n{'='*80}")
            print(f"Cache Entry Details")
            print(f"{'='*80}\n")
            print(f"URL: {response.url}")
            print(f"Cache Key: {cache_key}")

            # Show cache metadata
            if hasattr(response, 'from_cache'):
                print(f"From Cache: {response.from_cache}")
            if hasattr(response, 'created_at') and response.created_at:
                print(f"Created: {response.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if hasattr(response, 'expires') and response.expires:
                print(f"Expires: {response.expires.strftime('%Y-%m-%d %H:%M:%S')}")
            if hasattr(response, 'is_expired'):
                print(f"Is Expired: {response.is_expired}")

            print(f"\nStatus Code: {response.status_code}")

            # Show request details
            if hasattr(response, 'request') and response.request:
                print(f"Request Method: {response.request.method}")
                if hasattr(response.request, 'headers'):
                    print(f"\nRequest Headers:")
                    for header, value in response.request.headers.items():
                        print(f"  {header}: {value}")

            # Show response headers
            print(f"\nResponse Headers:")
            for header, value in response.headers.items():
                print(f"  {header}: {value}")

            # Show content info
            content_length = len(response.content) if response.content else 0
            print(f"\nContent Length: {content_length} bytes")

            # Show content preview based on content type
            content_type = response.headers.get('Content-Type', '')

            if 'json' in content_type.lower():
                try:
                    data = response.json()
                    json_str = json.dumps(data, indent=2)
                    print("\nJSON Response Preview:")
                    print(json_str[:1000])
                    if len(json_str) > 1000:
                        print("... (truncated)")
                except:
                    print("\nCould not parse JSON content")

            elif any(t in content_type.lower() for t in ['text', 'html', 'xml']):
                print("\nText Content Preview:")
                text = response.text[:1000] if response.text else "(empty)"
                print(text)
                if response.text and len(response.text) > 1000:
                    print("... (truncated)")

            print()

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def save_response(self, url_pattern: str, output_file: Optional[str] = None) -> None:
        """Save cached response to file"""
        try:
            cache = self.session.cache

            # Find matching response
            matches = []
            for cache_key, response in cache.responses.items():
                if url_pattern.lower() in response.url.lower():
                    matches.append((cache_key, response))

            if not matches:
                print(f"No cached entry found for pattern: {url_pattern}")
                return

            if len(matches) > 1:
                print(f"Found {len(matches)} matching entries. Using first match.")

            _, response = matches[0]

            # Determine output filename
            if not output_file:
                # Create filename from URL
                url_parts = response.url.split('/')
                filename = url_parts[-1] if url_parts[-1] else 'response'
                # Remove query parameters
                filename = filename.split('?')[0]
                filename = re.sub(r'[^\w\-_.]', '_', filename)

                content_type = response.headers.get('Content-Type', '')

                if 'json' in content_type and not filename.endswith('.json'):
                    output_file = f"{filename}.json"
                elif 'html' in content_type and not filename.endswith('.html'):
                    output_file = f"{filename}.html"
                elif 'xml' in content_type and not filename.endswith('.xml'):
                    output_file = f"{filename}.xml"
                else:
                    output_file = filename if filename else "response.bin"

            # Save content
            if response.content:
                with open(output_file, 'wb') as f:
                    f.write(response.content)
                print(f"Response saved to: {output_file}")
                print(f"Size: {len(response.content)} bytes")
            else:
                print("Response has no content to save.")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def export_summary(self, output_file: str = "cache_export.json") -> None:
        """Export cache summary to JSON file"""
        try:
            cache = self.session.cache

            export_data = {
                "cache_name": self.cache_name,
                "exported_at": datetime.now().isoformat(),
                "total_entries": cache.count(expired=True),
                "entries": []
            }

            # Iterate through all responses
            for cache_key, response in cache.responses.items():
                entry = {
                    "cache_key": cache_key,
                    "url": response.url,
                    "status_code": response.status_code,
                }

                if hasattr(response, 'created_at') and response.created_at:
                    entry["created_at"] = response.created_at.isoformat()
                if hasattr(response, 'expires') and response.expires:
                    entry["expires"] = response.expires.isoformat()
                if hasattr(response, 'is_expired'):
                    entry["is_expired"] = response.is_expired
                if hasattr(response, 'request') and response.request:
                    entry["method"] = response.request.method

                # Add selected headers
                entry["content_type"] = response.headers.get('Content-Type', 'unknown')
                entry["content_length"] = len(response.content) if response.content else 0

                export_data["entries"].append(entry)

            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2)

            print(f"Cache summary exported to: {output_file}")
            print(f"Total entries: {export_data['total_entries']}")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def clean_expired(self) -> None:
        """Remove expired cache entries"""
        try:
            cache = self.session.cache

            # Count expired entries before deletion
            expired_count = len(list(cache.filter(valid=False, expired=True)))

            if expired_count == 0:
                print("No expired entries found.")
                return

            print(f"Found {expired_count} expired entries.")

            # Delete expired entries
            deleted = cache.delete(expired=True)

            print(f"Removed {expired_count} expired entries.")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def delete_by_pattern(self, pattern: str) -> None:
        """Delete URLs matching pattern"""
        try:
            cache = self.session.cache

            # Compile regex
            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                print(f"Invalid regex pattern: {e}", file=sys.stderr)
                return

            # Find matching cache keys
            keys_to_delete = []
            matching_urls = []

            for cache_key, response in cache.responses.items():
                if regex.search(response.url):
                    keys_to_delete.append(cache_key)
                    matching_urls.append(response.url)

            if not keys_to_delete:
                print(f"No entries found matching pattern: {pattern}")
                return

            print(f"Found {len(keys_to_delete)} entries to delete:")
            for url in matching_urls[:10]:  # Show first 10
                print(f"  - {url}")
            if len(matching_urls) > 10:
                print(f"  ... and {len(matching_urls) - 10} more")

            response = input("\nContinue? (y/N): ")

            if response.lower() != 'y':
                print("Cancelled.")
                return

            # Delete by cache keys
            cache.delete(*keys_to_delete)
            print(f"Deleted {len(keys_to_delete)} entries.")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def delete_older_than(self, days: int) -> None:
        """Delete entries older than specified days"""
        try:
            cache = self.session.cache

            # Calculate age threshold
            age_threshold = timedelta(days=days)

            # Get count before deletion
            initial_count = cache.count(expired=True)

            print(f"Deleting entries older than {days} days...")

            # Delete old entries
            cache.delete(older_than=age_threshold)

            # Get count after deletion
            remaining = cache.count(expired=True)
            deleted = initial_count - remaining

            print(f"Deleted {deleted} entries.")
            print(f"Remaining entries: {remaining}")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def clear_cache(self) -> None:
        """Clear entire cache"""
        try:
            cache = self.session.cache

            # Get total count
            total = cache.count(expired=True)

            if total == 0:
                print("Cache is already empty.")
                return

            print(f"WARNING: This will delete all {total} cached entries!")
            response = input("Are you sure? (y/N): ")

            if response.lower() != 'y':
                print("Cancelled.")
                return

            cache.clear()
            print(f"Cleared {total} entries from cache.")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def demo(self) -> None:
        """Run demonstration"""
        print("\n" + "="*70)
        print("Cache Manager Demo")
        print("="*70 + "\n")

        print("This script uses the requests-cache API to manage cached HTTP responses.\n")

        print("BASIC COMMANDS:\n")

        print("1. Show cache information:")
        print("   python cache_manager.py info [cache_name]\n")

        print("2. List cached URLs (default: 20):")
        print("   python cache_manager.py list [cache_name] [limit]\n")

        print("3. Search for URLs by pattern:")
        print("   python cache_manager.py search <cache_name> <pattern>\n")

        print("4. Get details of a cached request:")
        print("   python cache_manager.py get <cache_name> <url_pattern>\n")

        print("5. Save a cached response to file:")
        print("   python cache_manager.py save <cache_name> <url_pattern> [file]\n")

        print("MANAGEMENT COMMANDS:\n")

        print("6. Export cache summary to JSON:")
        print("   python cache_manager.py export [cache_name] [output_file]\n")

        print("7. Remove expired entries:")
        print("   python cache_manager.py clean [cache_name]\n")

        print("8. Delete entries by URL pattern:")
        print("   python cache_manager.py delete <cache_name> <pattern>\n")

        print("9. Delete entries older than N days:")
        print("   python cache_manager.py older <cache_name> <days>\n")

        print("10. Clear entire cache:")
        print("    python cache_manager.py clear [cache_name]\n")

        print("EXAMPLES:\n")
        print("  python cache_manager.py info http_cache")
        print("  python cache_manager.py list http_cache 50")
        print("  python cache_manager.py search http_cache 'api/users'")
        print("  python cache_manager.py get http_cache 'example.com'")
        print("  python cache_manager.py save http_cache 'api/data' output.json")
        print("  python cache_manager.py clean http_cache")
        print("  python cache_manager.py delete http_cache 'old-api'")
        print("  python cache_manager.py older http_cache 30")
        print("  python cache_manager.py clear http_cache\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Manage requests-cache databases using the official API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  info [cache_name]                    - Show cache information
  list [cache_name] [limit]            - List cached URLs (default limit: 20)
  search <cache_name> <pattern>        - Search for URLs matching regex pattern
  get <cache_name> <url_pattern>       - Get cached request details
  save <cache_name> <url_pattern> [file] - Save cached response to file
  export [cache_name] [file]           - Export cache summary to JSON
  clean [cache_name]                   - Remove expired entries
  delete <cache_name> <pattern>        - Delete URLs matching pattern
  older <cache_name> <days>            - Delete entries older than N days
  clear [cache_name]                   - Clear entire cache
  demo                                 - Show usage examples

Default cache_name is "http_cache" if not specified.

Examples:
  python cache_manager.py info
  python cache_manager.py list http_cache 50
  python cache_manager.py search http_cache "api/users"
  python cache_manager.py clean http_cache
  python cache_manager.py older http_cache 30
        """
    )

    parser.add_argument('command', help='Command to execute')
    parser.add_argument('args', nargs='*', help='Command arguments')

    args = parser.parse_args()

    # Handle demo command (no cache name needed)
    if args.command == 'demo':
        manager = CacheManager()
        manager.demo()
        return

    # Determine cache name
    cache_name = "http_cache"  # default
    cmd_args = args.args.copy()

    # Commands that accept optional cache_name as first arg
    if cmd_args:
        # For commands that only take cache_name (and maybe one more arg)
        if args.command in ['info', 'list', 'export', 'clean', 'clear']:
            # First arg could be cache name or a parameter
            if args.command == 'list' and cmd_args[0].isdigit():
                # It's a limit, not a cache name
                pass
            else:
                # Assume it's cache name
                cache_name = cmd_args.pop(0)

        # Commands that require additional args (pattern, url, etc.)
        elif args.command in ['search', 'get', 'save', 'delete', 'older']:
            # If we have 2+ args, first is likely cache name
            # If we have 1 arg, it might be the pattern/url (using default cache)
            if len(cmd_args) >= 2:
                cache_name = cmd_args.pop(0)
            elif len(cmd_args) == 1 and args.command == 'older':
                # older requires days number, so single arg is cache name
                cache_name = cmd_args.pop(0)

    manager = CacheManager(cache_name)

    # Execute command
    try:
        if args.command == 'info':
            manager.info()

        elif args.command == 'list':
            limit = int(cmd_args[0]) if cmd_args and cmd_args[0].isdigit() else 20
            manager.list_urls(limit)

        elif args.command == 'search':
            if not cmd_args:
                print("Error: search requires a pattern argument", file=sys.stderr)
                sys.exit(1)
            manager.search(cmd_args[0])

        elif args.command == 'get':
            if not cmd_args:
                print("Error: get requires a URL pattern argument", file=sys.stderr)
                sys.exit(1)
            manager.get_details(cmd_args[0])

        elif args.command == 'save':
            if not cmd_args:
                print("Error: save requires a URL pattern argument", file=sys.stderr)
                sys.exit(1)
            url_pattern = cmd_args[0]
            output_file = cmd_args[1] if len(cmd_args) > 1 else None
            manager.save_response(url_pattern, output_file)

        elif args.command == 'export':
            output_file = cmd_args[0] if cmd_args else "cache_export.json"
            manager.export_summary(output_file)

        elif args.command == 'clean':
            manager.clean_expired()

        elif args.command == 'delete':
            if not cmd_args:
                print("Error: delete requires a pattern argument", file=sys.stderr)
                sys.exit(1)
            manager.delete_by_pattern(cmd_args[0])

        elif args.command == 'older':
            if not cmd_args:
                print("Error: older requires number of days", file=sys.stderr)
                sys.exit(1)
            try:
                days = int(cmd_args[0])
                manager.delete_older_than(days)
            except ValueError:
                print("Error: days must be a number", file=sys.stderr)
                sys.exit(1)

        elif args.command == 'clear':
            manager.clear_cache()

        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            print("Run 'python cache_manager.py demo' to see available commands")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
