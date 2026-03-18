import json
import requests
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from threading import Lock
import argparse
import sys


# ============================================================================
# PART 1: Topic Processing (from process_topics.py)
# ============================================================================

def load_topics(filename: str = 'topics.json') -> List[Dict]:
    """Load topics from JSON file."""
    with open(filename, 'r') as f:
        return json.load(f)


def fetch_topic_data(base_url: str, uri: str) -> Dict[str, Any]:
    """Fetch data from API for a given topic URI."""
    url = f"{base_url}{uri}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def extract_entries(api_data: Dict[str, Any]) -> List[Dict]:
    """Extract all entries from collection.sections in API response."""
    entries = []

    if 'collection' in api_data and 'sections' in api_data['collection']:
        sections = api_data['collection']['sections']

        for section in sections:
            if 'entries' in section:
                entries.extend(section['entries'])

    return entries


def process_topics(topics: List[Dict], base_url: str) -> List[Dict[str, Any]]:
    """
    Process all topics and return a list of dictionaries with topic titles and their entries.

    Args:
        topics: List of topic dictionaries from topics.json
        base_url: Base API URL to append the URI to

    Returns:
        List of dictionaries with format: {'topic': title, 'entries': [list of entry objects]}
    """
    results = []

    for topic in topics:
        topic_title = topic.get('title', 'Unknown')
        topic_uri = topic.get('uri', '')

        print(f"Processing topic: {topic_title}")

        try:
            api_data = fetch_topic_data(base_url, topic_uri)
            entries = extract_entries(api_data)

            results.append({
                'topic': topic_title,
                'entries': entries
            })

            print(f"  Found {len(entries)} entries")

        except Exception as e:
            print(f"  Error processing {topic_title}: {str(e)}")
            results.append({
                'topic': topic_title,
                'entries': []
            })

    return results


def save_topic_results(results: List[Dict], output_file: str = 'results.json'):
    """Save topic results to a JSON file."""
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nTopic results saved to {output_file}")


# ============================================================================
# PART 2: Entry Processing (from process_entries.py)
# ============================================================================

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
        self.errors = []

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
            api_data = self.fetch_entry_data(entry_uri)
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
            future_to_entry = {
                executor.submit(self.process_single_entry, entry, topic_title, idx): (
                    entry,
                    idx,
                )
                for idx, entry in enumerate(entries)
            }

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


# ============================================================================
# MAIN: Combined Processing
# ============================================================================

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Combined topic and entry processor - extracts entries from topics and their data-aid values.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all topics and entries
  python process_all.py

  # Process with custom worker count
  python process_all.py --workers 20

  # Use custom input/output files
  python process_all.py --topics custom_topics.json --output custom_results.json
        """,
    )

    parser.add_argument(
        "--topics",
        "-t",
        type=str,
        default="topics.json",
        help="Input JSON file with topics (default: topics.json)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="results.json",
        help="Intermediate output JSON file for topic results (default: results.json)",
    )

    parser.add_argument(
        "--data-aids",
        "-d",
        type=str,
        default="data_aids.json",
        help="Final output JSON file for data-aids (default: data_aids.json)",
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
        help="Number of concurrent worker threads for entry processing (default: 15)",
    )

    parser.add_argument(
        "--topic-base-url",
        type=str,
        default="https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri=/general-conference/topics",
        help="Base API URL for topics",
    )

    parser.add_argument(
        "--entry-base-url",
        type=str,
        default="https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri=",
        help="Base API URL for entries",
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    print("=" * 60)
    print("Combined Topic & Entry Processor")
    print("=" * 60)

    # ========================================================================
    # STEP 1: Process Topics
    # ========================================================================
    print("\n" + "=" * 60)
    print("STEP 1: Processing Topics")
    print("=" * 60)

    print(f"\n📂 Loading topics from {args.topics}...")
    try:
        topics = load_topics(args.topics)
    except FileNotFoundError:
        print(f"❌ Error: File '{args.topics}' not found!")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Error: File '{args.topics}' is not valid JSON!")
        sys.exit(1)

    print(f"✅ Loaded {len(topics)} topics\n")

    # Process all topics to get entries
    topic_results = process_topics(topics, args.topic_base_url)

    # Save intermediate results
    save_topic_results(topic_results, args.output)

    # Print summary
    print("\nTopic Processing Summary:")
    total_entries = sum(len(result['entries']) for result in topic_results)
    print(f"  Total topics: {len(topic_results)}")
    print(f"  Total entries found: {total_entries}")

    # ========================================================================
    # STEP 2: Process Entries
    # ========================================================================
    print("\n" + "=" * 60)
    print("STEP 2: Processing Entries")
    print("=" * 60)

    print(f"\n🔧 Using {args.workers} concurrent threads")

    # Initialize entry processor
    processor = EntryProcessor(base_url=args.entry_base_url, max_workers=args.workers)

    # Process all entries
    entry_results = processor.process_all_topics(topic_results)

    # Save final results
    processor.save_results(entry_results, args.data_aids)
    processor.save_errors(entry_results, args.errors)

    # Print final summary
    print("\n" + "=" * 60)
    print("📊 FINAL SUMMARY BY TOPIC")
    print("=" * 60)
    for result in entry_results:
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