import json
import requests
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import time
from threading import Lock
import argparse
import sys


class EntryProcessor:
    """Process entries with multi-threaded API requests."""

    def __init__(self, base_url: str, max_workers: int = 10):
        """
        Initialize the processor.

        Args:
            base_url: Base API URL to append entry URIs to
            max_workers: Maximum number of concurrent threads (default: 10)
        """
        self.base_url = base_url
        self.max_workers = max_workers
        self.lock = Lock()
        self.processed_count = 0
        self.error_count = 0
        self.errors = []  # Store detailed error information

    def load_results(self, filename: str = "results.json") -> List[Dict]:
        """Load results from the first script."""
        with open(filename, "r") as f:
            return json.load(f)

    def find_topic(self, topics: List[Dict], topic_name: str) -> Optional[Dict]:
        """
        Find a specific topic by name (case-insensitive).

        Args:
            topics: List of topic dictionaries
            topic_name: Name of the topic to find

        Returns:
            Topic dictionary if found, None otherwise
        """
        topic_name_lower = topic_name.lower()
        for topic in topics:
            if topic["topic"].lower() == topic_name_lower:
                return topic
        return None

    def fetch_entry_data(self, uri: str) -> Dict[str, Any]:
        """Fetch data from API for a given entry URI."""
        url = f"{self.base_url}{uri}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def extract_data_aid(self, api_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract data-aid from page attributes.

        Navigates to .content.content.body and parses HTML to find h1[data-aid]
        """
        try:
            # Navigate to content.meta.pageAttributes
            if "content" not in api_data:
                raise ValueError("No 'content' key in API response")

            content = api_data["content"]
            if "meta" not in content:
                raise ValueError("No 'meta' key in content object")

            meta = content["meta"]
            if "pageAttributes" not in meta:
                raise ValueError("No 'pageAttributes' key in meta object")

            page_attributes = meta["pageAttributes"]

            data_aid = page_attributes.get("data-aid")
            if data_aid:
                return data_aid

            raise ValueError("No data-aid found in pageAttributes")

        except Exception as e:
            raise Exception(f"Error extracting data-aid: {str(e)}")

    def process_single_entry(
        self, entry: Dict, topic_title: str, entry_index: int
    ) -> Dict:
        """
        Process a single entry and return its data-aid.

        Args:
            entry: Entry dictionary containing uri
            topic_title: Name of the topic this entry belongs to
            entry_index: Index of this entry in the list

        Returns:
            Dictionary with entry info, data-aid, and error details if any
        """
        entry_uri = entry.get("uri", "")
        entry_title = entry.get("title", "Unknown")

        try:
            # Fetch API data
            api_data = self.fetch_entry_data(entry_uri)

            # Extract data-aid
            data_aid = self.extract_data_aid(api_data)

            with self.lock:
                self.processed_count += 1
                if self.processed_count % 10 == 0:
                    print(f"  Processed {self.processed_count} entries...")

            return {
                "index": entry_index,
                "uri": entry_uri,
                "title": entry_title,
                "data_aid": data_aid,
                "success": True,
                "error": None,
            }

        except Exception as e:
            error_msg = str(e)
            with self.lock:
                self.error_count += 1
                self.errors.append(
                    {
                        "topic": topic_title,
                        "index": entry_index,
                        "uri": entry_uri,
                        "title": entry_title,
                        "error": error_msg,
                    }
                )

            print(f"    ❌ Error [{entry_index}] {entry_title}: {error_msg}")

            return {
                "index": entry_index,
                "uri": entry_uri,
                "title": entry_title,
                "data_aid": None,
                "success": False,
                "error": error_msg,
            }

    def process_topic_entries(self, topic: Dict) -> Dict:
        """
        Process all entries for a single topic using multi-threading.

        Args:
            topic: Dictionary with 'topic' and 'entries' keys

        Returns:
            Dictionary with topic name, list of data-aids, and detailed results
        """
        topic_title = topic["topic"]
        entries = topic["entries"]

        print(f"\n{'='*60}")
        print(f"Processing topic: {topic_title}")
        print(f"{'='*60}")
        print(f"Total entries: {len(entries)}")
        print(f"Concurrent workers: {self.max_workers}\n")

        data_aids = []
        all_results = []

        # Reset counters for this topic
        self.processed_count = 0
        self.error_count = 0
        self.errors = []

        # Use ThreadPoolExecutor for concurrent API requests
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks with index
            future_to_entry = {
                executor.submit(self.process_single_entry, entry, topic_title, idx): (
                    entry,
                    idx,
                )
                for idx, entry in enumerate(entries)
            }

            # Collect results as they complete
            for future in as_completed(future_to_entry):
                result = future.result()
                all_results.append(result)

                if result["success"] and result["data_aid"]:
                    data_aids.append(result["data_aid"])

        # Sort results by index to maintain order
        all_results.sort(key=lambda x: x["index"])

        print(f"\n{'='*60}")
        print(f"✅ Completed: {len(data_aids)} data-aids extracted")
        print(f"❌ Errors: {self.error_count}")
        print(f"{'='*60}")

        return {
            "topic": topic_title,
            "data_aids": data_aids,
            "total_entries": len(entries),
            "successful_extractions": len(data_aids),
            "failed_extractions": self.error_count,
            "all_results": all_results,
            "errors": self.errors,
        }

    def process_all_topics(self, topics: List[Dict]) -> List[Dict]:
        """
        Process all topics and their entries.

        Args:
            topics: List of topic dictionaries from results.json

        Returns:
            List of dictionaries with topic names and their data-aids
        """
        results = []
        start_time = time.time()

        for topic in topics:
            topic_result = self.process_topic_entries(topic)
            results.append(topic_result)

        elapsed_time = time.time() - start_time

        total_processed = sum(r["total_entries"] for r in results)
        total_successful = sum(r["successful_extractions"] for r in results)
        total_errors = sum(r["failed_extractions"] for r in results)

        print(f"\n{'='*60}")
        print(f"🎉 PROCESSING COMPLETE!")
        print(f"{'='*60}")
        print(f"Total time: {elapsed_time:.2f} seconds")
        print(f"Total entries processed: {total_processed}")
        print(f"Total successful: {total_successful}")
        print(f"Total errors: {total_errors}")
        if total_processed > 0:
            print(f"Success rate: {total_successful/total_processed*100:.1f}%")
            print(f"Average time per entry: {elapsed_time/total_processed:.2f} seconds")

        return results

    def save_results(self, results: List[Dict], output_file: str = "data_aids.json"):
        """Save results to a JSON file."""
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n💾 Results saved to {output_file}")

    def save_errors(self, results: List[Dict], error_file: str = "errors.json"):
        """Save all errors to a separate file for review."""
        all_errors = []
        for result in results:
            if result.get("errors"):
                all_errors.extend(result["errors"])

        if all_errors:
            with open(error_file, "w") as f:
                json.dump(all_errors, f, indent=2)
            print(f"❌ Error details saved to {error_file}")
        else:
            print(f"✅ No errors to save!")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Process entries from topics and extract data-aid values.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all topics
  python process_entries.py
  
  # Process a specific topic
  python process_entries.py --topic "Priesthood"
  
  # Process a specific topic with custom settings
  python process_entries.py --topic "Priesthood" --workers 20 --input custom_results.json
        """,
    )

    parser.add_argument(
        "--topic",
        "-t",
        type=str,
        help="Specific topic name to process (case-insensitive). If not provided, all topics will be processed.",
    )

    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="results.json",
        help="Input JSON file from process_topics.py (default: results.json)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="data_aids.json",
        help="Output JSON file for results (default: data_aids.json)",
    )

    parser.add_argument(
        "--errors",
        "-e",
        type=str,
        default="errors.json",
        help="Output JSON file for errors (default: errors.json)",
    )

    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=15,
        help="Number of concurrent worker threads (default: 15)",
    )

    parser.add_argument(
        "--base-url",
        "-u",
        type=str,
        default="https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri=",
        help="Base API URL (default: https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri=)",
    )

    return parser.parse_args()


def main():
    # Parse command line arguments
    args = parse_arguments()

    print("=" * 60)
    print("Multi-threaded Entry Processor")
    print("=" * 60)

    # Initialize processor
    processor = EntryProcessor(base_url=args.base_url, max_workers=args.workers)

    # Load topics and entries from first script's output
    print(f"\n📂 Loading data from {args.input}...")
    try:
        all_topics = processor.load_results(args.input)
    except FileNotFoundError:
        print(f"❌ Error: File '{args.input}' not found!")
        print(f"Make sure you've run process_topics.py first.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Error: File '{args.input}' is not valid JSON!")
        sys.exit(1)

    # Filter to specific topic if requested
    if args.topic:
        print(f"🔍 Searching for topic: '{args.topic}'...")
        topic = processor.find_topic(all_topics, args.topic)

        if topic is None:
            print(f"\n❌ Error: Topic '{args.topic}' not found!")
            print(f"\nAvailable topics:")
            for t in all_topics:
                print(f"  - {t['topic']}")
            sys.exit(1)

        topics_to_process = [topic]
        print(f"✅ Found topic: '{topic['topic']}'")
        print(f"   Entries to process: {len(topic['entries'])}")
    else:
        topics_to_process = all_topics
        total_entries = sum(len(topic["entries"]) for topic in topics_to_process)
        print(
            f"📊 Loaded {len(topics_to_process)} topics with {total_entries} total entries"
        )

    print(f"🔧 Using {args.workers} concurrent threads")

    # Process topics
    results = processor.process_all_topics(topics_to_process)

    # Save results
    processor.save_results(results, args.output)
    processor.save_errors(results, args.errors)

    # Print summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY BY TOPIC")
    print("=" * 60)
    for result in results:
        print(f"\n{result['topic']}:")
        print(f"  Total entries: {result['total_entries']}")
        print(f"  ✅ Successful: {result['successful_extractions']}")
        print(f"  ❌ Failed: {result['failed_extractions']}")
        if result["total_entries"] > 0:
            print(
                f"  Success rate: {result['successful_extractions']/result['total_entries']*100:.1f}%"
            )


if __name__ == "__main__":
    main()
