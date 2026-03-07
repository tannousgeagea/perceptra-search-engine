# examples/test_image_upload.py

import requests
from pathlib import Path

BASE_URL = "http://localhost:8000/api/v1"
API_KEY = "ise_your_api_key_here"

def upload_image():
    url = f"{BASE_URL}/upload/image"
    
    image_path = Path("sample_image.jpg")
    
    with open(image_path, 'rb') as f:
        files = {'file': ('defect.jpg', f, 'image/jpeg')}
        data = {
            'plant_site': 'Plant_B',
            'captured_at': '2024-03-05T14:15:00',
            'shift': 'afternoon',
            'tags': '[{"name":"defect","color":"#FFA500"}]'
        }
        
        response = requests.post(
            url,
            files=files,
            data=data,
            headers={'X-API-Key': API_KEY}
        )
    
    print(f"Status: {response.status_code}")
    print(response.json())

if __name__ == "__main__":
    upload_image()