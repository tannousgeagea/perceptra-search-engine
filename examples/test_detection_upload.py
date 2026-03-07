# examples/test_detection_upload.py

import requests

BASE_URL = "http://localhost:8000/api/v1"
API_KEY = "ise_your_api_key_here"

def create_detection(image_id: int):
    url = f"{BASE_URL}/upload/detection"
    
    detection = {
        'image_id': image_id,
        'bbox_x': 0.25,
        'bbox_y': 0.35,
        'bbox_width': 0.15,
        'bbox_height': 0.20,
        'bbox_format': 'normalized',
        'label': 'metal_scrap',
        'confidence': 0.95,
        'tags': [
            {'name': 'verified', 'color': '#00FF00'},
            {'name': 'critical', 'color': '#FF0000'}
        ]
    }
    
    response = requests.post(
        url,
        json=detection,
        headers={'X-API-Key': API_KEY}
    )
    
    print(f"Status: {response.status_code}")
    print(response.json())

def create_bulk_detections(image_id: int):
    url = f"{BASE_URL}/upload/detections/bulk"
    
    bulk_data = {
        'detections': [
            {
                'image_id': image_id,
                'bbox_x': 0.1, 'bbox_y': 0.1,
                'bbox_width': 0.2, 'bbox_height': 0.2,
                'bbox_format': 'normalized',
                'label': 'fiber',
                'confidence': 0.88
            },
            {
                'image_id': image_id,
                'bbox_x': 0.5, 'bbox_y': 0.5,
                'bbox_width': 0.15, 'bbox_height': 0.15,
                'bbox_format': 'normalized',
                'label': 'burn_mark',
                'confidence': 0.92
            }
        ]
    }
    
    response = requests.post(
        url,
        json=bulk_data,
        headers={'X-API-Key': API_KEY}
    )
    
    print(f"Status: {response.status_code}")
    print(response.json())

if __name__ == "__main__":
    # First upload an image, then use its ID
    IMAGE_ID = 1  # Replace with actual image ID
    
    print("Creating single detection...")
    create_detection(IMAGE_ID)
    
    print("\nCreating bulk detections...")
    create_bulk_detections(IMAGE_ID)