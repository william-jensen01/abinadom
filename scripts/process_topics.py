"""
Topic data fetcher.

Loads topic URIs from topics.json, fetches each topic's data from the
Church of Jesus Christ API, and extracts talk entries with metadata.

Usage:
    pipenv run py scripts/process_topics.py
"""

import json
import requests
from typing import List, Dict, Any


def load_topics(filename: str = 'topics.json') -> List[Dict]:
    """Load topics from JSON file."""
    with open(filename, 'r') as f:
        return json.load(f)


def fetch_topic_data(base_url: str, uri: str) -> Dict[str, Any]:
    """Fetch data from API for a given topic URI."""
    url = f"{base_url}{uri}"
    response = requests.get(url)
    response.raise_for_status()  # Raise an error for bad status codes
    return response.json()


def extract_entries(api_data: Dict[str, Any]) -> List[Dict]:
    """Extract all entries from collection.sections in API response."""
    entries = []
    
    # Navigate to collection.sections
    if 'collection' in api_data and 'sections' in api_data['collection']:
        sections = api_data['collection']['sections']
        
        # Loop through each section and collect entries
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
            # Fetch API data for this topic
            api_data = fetch_topic_data(base_url, topic_uri)
            
            # Extract entries from sections
            entries = extract_entries(api_data)
            
            # Add to results
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


def save_results(results: List[Dict], output_file: str = 'results.json'):
    """Save results to a JSON file."""
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_file}")


def main():
    # Configuration
    BASE_URL = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/dynamic?lang=eng&uri=/general-conference/topics"  # Replace with your actual base URL
    TOPICS_FILE = "topics.json"
    OUTPUT_FILE = "results.json"
    
    # Load topics
    print("Loading topics...")
    topics = load_topics(TOPICS_FILE)
    print(f"Loaded {len(topics)} topics\n")
    
    # Process all topics
    results = process_topics(topics, BASE_URL)
    
    # Save results
    save_results(results, OUTPUT_FILE)
    
    # Print summary
    print("\nSummary:")
    for result in results:
        print(f"  {result['topic']}: {len(result['entries'])} entries")


if __name__ == "__main__":
    main()
