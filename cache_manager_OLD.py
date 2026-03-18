#!/usr/bin/env python3
"""
Cache Management Utility (UPDATED with URL encoding fix)
Demonstrates various ways to interact with requests-cache
"""

import requests_cache
from requests import Request
from datetime import datetime, timedelta
import json
from pathlib import Path
from urllib.parse import quote, unquote


def show_cache_info(cache_name="http_cache"):
    """Display cache information"""
    session = requests_cache.CachedSession(cache_name)

    print("\n" + "=" * 70)
    print(f"CACHE INFORMATION: {cache_name}")
    print("=" * 70)

    cache_file = Path(f"{cache_name}.sqlite")
    if cache_file.exists():
        size_bytes = cache_file.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        print(f"📁 File: {cache_file.absolute()}")
        print(f"💾 Size: {size_mb:.2f} MB ({size_bytes:,} bytes)")
    else:
        print(f"⚠️  Cache file not found: {cache_file}")
        return

    print(f"📊 Total entries: {len(session.cache.responses)}")
    print(f"🔗 Unique URLs: {len(session.cache.urls())}")
    print("=" * 70 + "\n")


def list_cached_urls(cache_name="http_cache", limit=10, decode=True):
    """List cached URLs with details"""
    session = requests_cache.CachedSession(cache_name)

    from urllib.parse import urlparse, parse_qs

    print(f"\n📋 CACHED URLS (showing first {limit}):\n")

    for i, (url, response) in enumerate(
        list(session.cache.responses.items())[:limit], 1
    ):
        created = (
            response.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if response.created_at
            else "Unknown"
        )
        expires = (
            response.expires.strftime("%Y-%m-%d %H:%M:%S")
            if response.expires
            else "Never"
        )
        size_kb = len(response.content) / 1024

        # Show decoded query params if requested
        display_url = url
        if decode:
            try:
                parsed = urlparse(url)
                if parsed.query:
                    params = parse_qs(parsed.query)
                    decoded_query = "&".join(
                        f"{k}={unquote(v[0])}" for k, v in params.items()
                    )
                    display_url = (
                        f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{decoded_query}"
                        if parsed.scheme
                        else f"{parsed.path}?{decoded_query}"
                    )
            except:
                pass

        print(f"{i}. {display_url}")
        if decode and url != display_url:
            print(f"   (stored as: {url})")
        print(f"   Status: {response.status_code} | Size: {size_kb:.1f} KB")
        print(f"   Created: {created}")
        print(f"   Expires: {expires}")
        print()


def search_cache(cache_name="http_cache", pattern=""):
    """
    Search for URLs matching pattern (FIXED - handles URL encoding in query params only)

    Properly handles cases where query parameters are encoded:
    - Cache stores: /page?uri=%2Fgeneral-conference%2F2025%2F10%2F58oaks
    - You search for: /page?uri=/general-conference/2025/10/58oaks
    """
    session = requests_cache.CachedSession(cache_name)

    from urllib.parse import urlparse, parse_qs, urlencode

    print(f"\n🔍 SEARCHING FOR: '{pattern}'")

    # Normalize search pattern
    search_lower = pattern.lower()

    # Also try parsing as URL to decode query params
    search_variations = [search_lower]
    try:
        parsed = urlparse(pattern)
        if parsed.query:
            # Decode query parameters
            params = parse_qs(parsed.query)
            # Reconstruct with decoded values
            decoded_query = "&".join(f"{k}={unquote(v[0])}" for k, v in params.items())
            search_variations.append(f"{parsed.path}?{decoded_query}".lower())
    except:
        pass

    matches = []

    for url in session.cache.urls():
        url_lower = url.lower()

        # Try to decode query parameters in cached URL
        url_variations = [url_lower]
        try:
            parsed = urlparse(url)
            if parsed.query:
                params = parse_qs(parsed.query)
                decoded_query = "&".join(
                    f"{k}={unquote(v[0])}" for k, v in params.items()
                )
                url_variations.append(f"{parsed.path}?{decoded_query}".lower())
        except:
            pass

        # Check if any variation of search matches any variation of URL
        for search_var in search_variations:
            for url_var in url_variations:
                if search_var in url_var or search_lower in url_lower:
                    matches.append(url)
                    break
            if url in matches:
                break

    if matches:
        print(f"✓ Found {len(matches)} match(es):\n")
        for i, url in enumerate(matches, 1):
            # Show decoded query params if present
            display_url = url
            try:
                parsed = urlparse(url)
                if parsed.query:
                    params = parse_qs(parsed.query)
                    decoded_query = "&".join(
                        f"{k}={unquote(v[0])}" for k, v in params.items()
                    )
                    display_url = (
                        f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{decoded_query}"
                        if parsed.scheme
                        else f"{parsed.path}?{decoded_query}"
                    )
            except:
                pass

            print(f"{i}. {url}")
            if url != display_url:
                print(f"   Decoded params: {display_url}")

        print(f"\n✓ Total: {len(matches)} match(es)")
    else:
        print("✗ No matches found")


def export_cache_summary(cache_name="http_cache", output_file="cache_summary.json"):
    """Export cache summary to JSON"""
    session = requests_cache.CachedSession(cache_name)

    from urllib.parse import urlparse, parse_qs

    summary = {
        "cache_name": cache_name,
        "exported_at": datetime.now().isoformat(),
        "total_entries": len(session.cache.responses),
        "urls": [],
    }

    for url, response in session.cache.responses.items():
        # Decode query params for display
        url_decoded = url
        try:
            parsed = urlparse(url)
            if parsed.query:
                params = parse_qs(parsed.query)
                decoded_query = "&".join(
                    f"{k}={unquote(v[0])}" for k, v in params.items()
                )
                url_decoded = (
                    f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{decoded_query}"
                    if parsed.scheme
                    else f"{parsed.path}?{decoded_query}"
                )
        except:
            pass

        summary["urls"].append(
            {
                "url": url,
                "url_decoded": url_decoded,
                "status_code": response.status_code,
                "size_bytes": len(response.content),
                "created_at": (
                    response.created_at.isoformat() if response.created_at else None
                ),
                "expires": response.expires.isoformat() if response.expires else None,
            }
        )

    output_path = Path(output_file)
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n✓ Cache summary exported to: {output_path.absolute()}")


def clean_expired(cache_name="http_cache"):
    """Remove expired cache entries"""
    session = requests_cache.CachedSession(cache_name)

    before_count = len(session.cache.responses)
    session.cache.delete_expired()
    after_count = len(session.cache.responses)
    deleted = before_count - after_count

    print(f"\n🧹 CLEANED EXPIRED ENTRIES")
    print(f"   Deleted: {deleted}")
    print(f"   Remaining: {after_count}")


def delete_by_pattern(cache_name="http_cache", pattern=""):
    """Delete URLs matching pattern (handles URL encoding in query params)"""
    session = requests_cache.CachedSession(cache_name)

    from urllib.parse import urlparse, parse_qs

    # Normalize pattern
    pattern_lower = pattern.lower()

    urls_to_delete = []
    for url in session.cache.urls():
        url_lower = url.lower()

        # Check direct match
        if pattern_lower in url_lower:
            urls_to_delete.append(url)
            continue

        # Check with decoded query params
        try:
            parsed = urlparse(url)
            if parsed.query:
                params = parse_qs(parsed.query)
                decoded_query = "&".join(
                    f"{k}={unquote(v[0])}" for k, v in params.items()
                )
                decoded_url = f"{parsed.path}?{decoded_query}".lower()
                if pattern_lower in decoded_url:
                    urls_to_delete.append(url)
        except:
            pass

    if urls_to_delete:
        print(f"\n🗑️  DELETING {len(urls_to_delete)} URL(s) matching '{pattern}':")
        for url in urls_to_delete:
            # Show decoded query params
            display_url = url
            try:
                parsed = urlparse(url)
                if parsed.query:
                    params = parse_qs(parsed.query)
                    decoded_query = "&".join(
                        f"{k}={unquote(v[0])}" for k, v in params.items()
                    )
                    display_url = (
                        f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{decoded_query}"
                        if parsed.scheme
                        else f"{parsed.path}?{decoded_query}"
                    )
            except:
                pass

            print(f"   - {url}")
            if url != display_url:
                print(f"     ({display_url})")

        confirm = input("\nConfirm deletion? (yes/no): ")
        if confirm.lower() == "yes":
            session.cache.delete(urls=urls_to_delete)
            print("✓ Deleted successfully")
        else:
            print("✗ Cancelled")
    else:
        print(f"✗ No URLs found matching '{pattern}'")


def get_cached_request(
    cache_name="http_cache", url_pattern="", show_content=True, max_content_length=1000
):
    """
    Retrieve and display cached request/response for a specific URL

    Args:
        cache_name: Name of the cache
        url_pattern: URL or path fragment to find
        show_content: Whether to display response content
        max_content_length: Maximum characters of content to display

    Returns:
        Response object if found, None otherwise
    """
    session = requests_cache.CachedSession(cache_name)

    from urllib.parse import urlparse, parse_qs

    print(f"\n🔍 SEARCHING FOR: '{url_pattern}'")
    print()

    req = Request("GET", url_pattern)
    prep = session.prepare_request(req)

    # 2. Compute the cache key
    cache_key = session.cache.create_key(prep)

    print("Cache key:", cache_key)

    # 3. Retrieve the cached response
    cached_response = session.cache.get_response(cache_key)

    if cached_response:
        print("Found cached response!")
        print(cached_response.text)
    else:
        print("No cached response for that URL")

    cached_response = session.cache.contains(url=url_pattern)
    print(cached_response)
    if not cached_response:
        print(f"⚠️  No cached request found for: {url_pattern}")
        return None

    cache_key = session.cache.create_key(session._normalize_request("GET", url))
    if not cache_key:
        print(f"⚠️  No cache key found for: {url}")
        return None

    print(f"✓ Found cached request: {url_pattern}, key: {cache_key}")

    done = session.cache.get_response(cache_key)
    print(done)
    return done

    matches = []
    pattern_lower = url_pattern.lower()

    # Find all matching URLs
    for url in session.cache.urls():
        url_lower = url.lower()

        # Check direct match
        if pattern_lower in url_lower:
            matches.append(url)
            continue

        # Check with decoded query params
        try:
            parsed = urlparse(url)
            if parsed.query:
                params = parse_qs(parsed.query)
                decoded_query = "&".join(
                    f"{k}={unquote(v[0])}" for k, v in params.items()
                )
                decoded_url = f"{parsed.path}?{decoded_query}".lower()
                if pattern_lower in decoded_url:
                    matches.append(url)
        except:
            pass

    if not matches:
        print("✗ No cached requests found matching that pattern")
        return None

    if len(matches) > 1:
        print(f"⚠️  Found {len(matches)} matches. Showing first match:")
        for i, url in enumerate(matches[:5], 1):
            # Show decoded query params
            display_url = url
            try:
                parsed = urlparse(url)
                if parsed.query:
                    params = parse_qs(parsed.query)
                    decoded_query = "&".join(
                        f"{k}={unquote(v[0])}" for k, v in params.items()
                    )
                    display_url = (
                        f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{decoded_query}"
                        if parsed.scheme
                        else f"{parsed.path}?{decoded_query}"
                    )
            except:
                pass
            print(f"   {i}. {display_url}")
        print()

    # Get the first match
    url = matches[0]
    response = session.cache.responses.get(url)

    if not response:
        print("✗ Could not retrieve cached response")
        return None

    # Display request details
    print("=" * 70)
    print("CACHED REQUEST DETAILS")
    print("=" * 70)

    print(f"\n📍 URL:")
    print(f"   {url}")

    # Show decoded query params if present
    try:
        parsed = urlparse(url)
        if parsed.query:
            params = parse_qs(parsed.query)
            decoded_query = "&".join(f"{k}={unquote(v[0])}" for k, v in params.items())
            display_url = (
                f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{decoded_query}"
                if parsed.scheme
                else f"{parsed.path}?{decoded_query}"
            )
            if url != display_url:
                print(f"   Decoded params: {display_url}")
    except:
        pass

    print(f"\n📅 Cache Info:")
    print(f"   Created:  {response.created_at if response.created_at else 'Unknown'}")
    print(f"   Expires:  {response.expires if response.expires else 'Never'}")
    print(f"   From cache: {response.from_cache}")

    print(f"\n📊 Response:")
    print(f"   Status:   {response.status_code}")
    print(f"   Reason:   {response.reason}")
    print(
        f"   Size:     {len(response.content):,} bytes ({len(response.content)/1024:.1f} KB)"
    )

    print(f"\n📋 Response Headers:")
    for key, value in response.headers.items():
        print(f"   {key}: {value}")

    if show_content:
        print(f"\n📄 Response Content:")
        print("-" * 70)

        content = response.text
        if len(content) > max_content_length:
            print(content[:max_content_length])
            print(
                f"\n... (truncated, showing first {max_content_length} of {len(content)} characters)"
            )
        else:
            print(content)
        print("-" * 70)

    print("\n" + "=" * 70)

    return response


def save_cached_response(cache_name="http_cache", url_pattern="", output_file=None):
    """
    Save cached response content to a file

    Args:
        cache_name: Name of the cache
        url_pattern: URL or path fragment to find
        output_file: Output filename (auto-generated if None)

    Returns:
        Path to saved file if successful, None otherwise
    """
    session = requests_cache.CachedSession(cache_name)

    from urllib.parse import urlparse, parse_qs

    pattern_lower = url_pattern.lower()

    # Find matching URL
    for url in session.cache.urls():
        url_lower = url.lower()

        # Check direct match
        if pattern_lower in url_lower:
            response = session.cache.responses.get(url)
        else:
            # Check with decoded query params
            try:
                parsed = urlparse(url)
                if parsed.query:
                    params = parse_qs(parsed.query)
                    decoded_query = "&".join(
                        f"{k}={unquote(v[0])}" for k, v in params.items()
                    )
                    decoded_url = f"{parsed.path}?{decoded_query}".lower()
                    if pattern_lower in decoded_url:
                        response = session.cache.responses.get(url)
                    else:
                        continue
                else:
                    continue
            except:
                continue

        if response:
            # Auto-generate filename if not provided
            if not output_file:
                # Try to determine file extension from content-type
                content_type = response.headers.get("content-type", "")

                if "json" in content_type:
                    ext = "json"
                elif "html" in content_type:
                    ext = "html"
                elif "xml" in content_type:
                    ext = "xml"
                else:
                    ext = "txt"

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = f"cached_response_{timestamp}.{ext}"

            # Save content
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(response.text)

            # Show decoded query params in output
            display_url = url
            try:
                parsed = urlparse(url)
                if parsed.query:
                    params = parse_qs(parsed.query)
                    decoded_query = "&".join(
                        f"{k}={unquote(v[0])}" for k, v in params.items()
                    )
                    display_url = (
                        f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{decoded_query}"
                        if parsed.scheme
                        else f"{parsed.path}?{decoded_query}"
                    )
            except:
                pass

            print(f"\n✓ Saved response to: {output_file}")
            print(f"   URL: {display_url}")
            print(f"   Size: {len(response.content):,} bytes")

            return output_file

    print(f"\n✗ No cached request found for: {url_pattern}")
    return None


def clear_all_cache(cache_name="http_cache"):
    """Clear entire cache"""
    session = requests_cache.CachedSession(cache_name)

    count = len(session.cache.responses)
    print(f"\n⚠️  WARNING: This will delete all {count} cached entries")
    confirm = input("Are you sure? (yes/no): ")

    if confirm.lower() == "yes":
        session.cache.clear()
        print("✓ Cache cleared successfully")
    else:
        print("✗ Cancelled")


def demo_cache_interaction():
    """Demonstrate cache interaction"""
    cache_name = "demo_cache"

    print("\n" + "=" * 70)
    print("CACHE INTERACTION DEMO")
    print("=" * 70)

    # Create session and make some requests
    session = requests_cache.CachedSession(cache_name, expire_after=timedelta(hours=1))

    # Make some demo requests
    urls = [
        "https://httpbin.org/json",
        "https://httpbin.org/uuid",
        "https://httpbin.org/user-agent",
    ]

    print("\n1️⃣  Making requests...")
    for url in urls:
        response = session.get(url)
        print(
            f"   {url} - Status: {response.status_code} - From cache: {response.from_cache}"
        )

    print("\n2️⃣  Making same requests again (should be cached)...")
    for url in urls:
        response = session.get(url)
        print(
            f"   {url} - Status: {response.status_code} - From cache: {response.from_cache}"
        )

    # Show cache info
    show_cache_info(cache_name)

    # List URLs
    list_cached_urls(cache_name, limit=5)

    # Export summary
    export_cache_summary(cache_name, "demo_cache_summary.json")

    # Clean up
    print("\n🧹 Cleaning up demo cache...")
    session.cache.clear()
    print("✓ Demo complete")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(
            """
Cache Management Utility (Updated with URL encoding fix)
=========================================================

Usage:
    python cache_manager.py <command> [args]

Commands:
    info [cache_name]                    - Show cache information
    list [cache_name] [limit]            - List cached URLs (decoded by default)
    search <cache_name> <pattern>        - Search for URLs (handles encoding)
    get <cache_name> <url_pattern>       - Get and display cached request details
    save <cache_name> <url_pattern> [file] - Save cached response to file
    export [cache_name] [file]           - Export cache summary
    clean [cache_name]                   - Remove expired entries
    delete <cache_name> <pattern>        - Delete URLs by pattern
    clear [cache_name]                   - Clear entire cache
    demo                                 - Run demonstration

Examples:
    python cache_manager.py info http_cache
    python cache_manager.py list http_cache 20
    
    # Search (handles query parameter encoding):
    # If cache has: /page?uri=%2Fgeneral-conference%2F2025%2F10%2F58oaks
    # You can search: /page?uri=/general-conference/2025/10/58oaks
    python cache_manager.py search http_cache "uri=/general-conference"
    
    # Get cached request details:
    python cache_manager.py get http_cache "?uri=/general-conference/2019/10/58oaks"
    
    # Save cached response to file:
    python cache_manager.py save http_cache "/api/data" output.json
    
    python cache_manager.py clean http_cache
    python cache_manager.py demo
        """
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "info":
        cache_name = sys.argv[2] if len(sys.argv) > 2 else "http_cache"
        show_cache_info(cache_name)

    elif command == "list":
        cache_name = sys.argv[2] if len(sys.argv) > 2 else "http_cache"
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        list_cached_urls(cache_name, limit)

    elif command == "search":
        if len(sys.argv) < 4:
            print("Usage: python cache_manager.py search <cache_name> <pattern>")
            sys.exit(1)
        search_cache(sys.argv[2], sys.argv[3])

    elif command == "get":
        if len(sys.argv) < 4:
            print("Usage: python cache_manager.py get <cache_name> <url_pattern>")
            sys.exit(1)
        get_cached_request(sys.argv[2], sys.argv[3])

    elif command == "save":
        if len(sys.argv) < 4:
            print(
                "Usage: python cache_manager.py save <cache_name> <url_pattern> [output_file]"
            )
            sys.exit(1)
        output = sys.argv[4] if len(sys.argv) > 4 else None
        save_cached_response(sys.argv[2], sys.argv[3], output)

    elif command == "export":
        cache_name = sys.argv[2] if len(sys.argv) > 2 else "http_cache"
        output = sys.argv[3] if len(sys.argv) > 3 else "cache_summary.json"
        export_cache_summary(cache_name, output)

    elif command == "delete":
        if len(sys.argv) < 4:
            print("Usage: python cache_manager.py delete <cache_name> <pattern>")
            sys.exit(1)
        delete_by_pattern(sys.argv[2], sys.argv[3])

    elif command == "clear":
        cache_name = sys.argv[2] if len(sys.argv) > 2 else "http_cache"
        clear_all_cache(cache_name)

    elif command == "demo":
        demo_cache_interaction()

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
