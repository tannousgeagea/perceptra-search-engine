# examples/test_video_upload.py

import requests
from pathlib import Path

BASE_URL = "http://localhost:8000/api/v1"
API_KEY = "ise_your_api_key_here"

def upload_video():
    url = f"{BASE_URL}/upload/video"
    
    video_path = Path("sample_video.mp4")
    
    with open(video_path, 'rb') as f:
        files = {'file': ('inspection.mp4', f, 'video/mp4')}
        data = {
            'plant_site': 'Plant_A',
            'recorded_at': '2024-03-05T10:30:00',
            'shift': 'morning',
            'tags': '[{"name":"quality-check","color":"#FF5733"}]'
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
    upload_video()