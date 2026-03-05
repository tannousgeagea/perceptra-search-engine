# examples/search_examples.py

"""
Example usage of the search API endpoints.
"""

import requests
from pathlib import Path

BASE_URL = "http://localhost:8000/api/v1"
HEADERS = {
    "Authorization": "Bearer YOUR_TOKEN",
    "X-Tenant-ID": "YOUR_TENANT_ID"
}


def search_by_image_example():
    """Search by uploading an image."""
    url = f"{BASE_URL}/search/image"
    
    # Prepare image file
    image_path = Path("defect_sample.jpg")
    
    with open(image_path, 'rb') as f:
        files = {'file': ('defect.jpg', f, 'image/jpeg')}
        
        # Search parameters
        params = {
            'top_k': 10,
            'score_threshold': 0.7,
            'search_type': 'detections'
        }
        
        response = requests.post(url, files=files, params=params, headers=HEADERS)
    
    if response.status_code == 200:
        results = response.json()
        print(f"Found {results['total_results']} results")
        print(f"Execution time: {results['execution_time_ms']}ms")
        
        for detection in results['detection_results']:
            print(f"- {detection['label']} (score: {detection['similarity_score']:.3f})")
    else:
        print(f"Error: {response.status_code}")
        print(response.json())


def search_by_text_example():
    """Search by text query."""
    url = f"{BASE_URL}/search/text"
    
    payload = {
        "query": "metal scrap on fabric",
        "top_k": 10,
        "search_type": "detections",
        "filters": {
            "plant_site": "Plant_A",
            "min_confidence": 0.8
        }
    }
    
    response = requests.post(url, json=payload, headers=HEADERS)
    
    if response.status_code == 200:
        results = response.json()
        print(f"Found {results['total_results']} results for: '{payload['query']}'")
        
        for detection in results['detection_results']:
            print(
                f"- {detection['label']} at {detection['plant_site']} "
                f"(similarity: {detection['similarity_score']:.3f})"
            )


def search_hybrid_example():
    """Hybrid search with image and text."""
    url = f"{BASE_URL}/search/hybrid"
    
    image_path = Path("defect_sample.jpg")
    
    with open(image_path, 'rb') as f:
        files = {'file': ('defect.jpg', f, 'image/jpeg')}
        
        # Hybrid search parameters
        params = {
            'query': 'burned edge',
            'text_weight': 0.3,  # 30% text, 70% image
            'top_k': 10,
            'search_type': 'detections'
        }
        
        response = requests.post(url, files=files, params=params, headers=HEADERS)
    
    if response.status_code == 200:
        results = response.json()
        print(f"Hybrid search found {results['total_results']} results")


def search_similar_example():
    """Find similar detections to a given one."""
    url = f"{BASE_URL}/search/similar"
    
    payload = {
        "item_id": 123,  # Detection ID
        "item_type": "detection",
        "top_k": 10,
        "score_threshold": 0.6
    }
    
    response = requests.post(url, json=payload, headers=HEADERS)
    
    if response.status_code == 200:
        results = response.json()
        print(f"Found {results['total_results']} similar detections")


def get_search_history_example():
    """Get search history."""
    url = f"{BASE_URL}/search/history"
    
    params = {'limit': 10}
    response = requests.get(url, params=params, headers=HEADERS)
    
    if response.status_code == 200:
        history = response.json()
        print(f"Recent searches ({len(history)}):")
        
        for item in history:
            print(
                f"- {item['query_type']}: {item['query_text'] or 'N/A'} "
                f"({item['results_count']} results, {item['execution_time_ms']}ms)"
            )


def get_search_stats_example():
    """Get search statistics."""
    url = f"{BASE_URL}/search/stats"
    
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        stats = response.json()
        print(f"Total searches: {stats['total_searches']}")
        print(f"Searches today: {stats['searches_today']}")
        print(f"Avg execution time: {stats['avg_execution_time_ms']:.2f}ms")


if __name__ == "__main__":
    print("=== Image Search ===")
    search_by_image_example()
    
    print("\n=== Text Search ===")
    search_by_text_example()
    
    print("\n=== Hybrid Search ===")
    search_hybrid_example()
    
    print("\n=== Similarity Search ===")
    search_similar_example()
    
    print("\n=== Search History ===")
    get_search_history_example()
    
    print("\n=== Search Stats ===")
    get_search_stats_example()