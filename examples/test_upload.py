# examples/test_uploads.py

"""
Complete test suite for upload endpoints.
Tests video, image, and detection uploads with various scenarios.
"""

from os import getenv  as env
from os.path import join as path_join
import requests
from pathlib import Path
import json
from datetime import datetime
import time

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
API_KEY = env("API_KEY")
HEADERS = {
    "X-API-Key": API_KEY
}

# Test data paths
TEST_DATA_DIR = Path("test_data")
TEST_VIDEO_PATH = TEST_DATA_DIR / "sample_video.mp4"
TEST_IMAGE_PATH = TEST_DATA_DIR / "sample_image.jpg"


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'


def print_success(message):
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")


def print_error(message):
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")


def print_info(message):
    print(f"{Colors.BLUE}ℹ {message}{Colors.RESET}")


def print_warning(message):
    print(f"{Colors.YELLOW}⚠ {message}{Colors.RESET}")


def test_video_upload():
    """Test video upload endpoint."""
    print("\n" + "="*60)
    print("TEST 1: Video Upload")
    print("="*60)
    
    if not TEST_VIDEO_PATH.exists():
        print_error(f"Video file not found: {TEST_VIDEO_PATH}")
        print_info("Please place a sample video at test_data/sample_video.mp4")
        return None
    
    url = f"{BASE_URL}/upload/video"
    
    # Prepare form data
    with open(TEST_VIDEO_PATH, 'rb') as video_file:
        files = {
            'file': ('inspection_video.mp4', video_file, 'video/mp4')
        }
        
        data = {
            'plant_site': 'Plant_A',
            'recorded_at': '2024-03-05T10:30:00',
            'shift': 'morning',
            'inspection_line': 'gate03',
            'tags': json.dumps([
                {'name': 'quality-check', 'color': '#FF5733'},
                {'name': 'high-priority', 'color': '#FF0000'}
            ])
        }
        
        print_info(f"Uploading video: {TEST_VIDEO_PATH.name}")
        print_info(f"Plant: {data['plant_site']}, Shift: {data['shift']}")
        
        response = requests.post(url, files=files, data=data, headers=HEADERS)
    
    if response.status_code == 201:
        result = response.json()
        print_success("Video uploaded successfully!")
        print(f"  Message: {result['message']}")
        print(f"  Video ID: {result['id']}")
        print(f"  Video UUID: {result['video_id']}")
        print(f"  Filename: {result['filename']}")
        print(f"  Storage Key: {result['storage_key']}")
        print(f"  Size: {result['file_size_bytes'] / 1024 / 1024:.2f} MB")
        print(f"  Status: {result['status']}")
        print(f"  Tags: {len(result['tags'])} tags")
        for tag in result['tags']:
            print(f"    - {tag['name']} ({tag['color']})")
        return result
    else:
        print_error(f"Upload failed: {response.status_code}")
        print(response.text)
        return None


def test_image_upload():
    """Test image upload endpoint."""
    print("\n" + "="*60)
    print("TEST 2: Image Upload")
    print("="*60)
    
    if not TEST_IMAGE_PATH.exists():
        print_error(f"Image file not found: {TEST_IMAGE_PATH}")
        print_info("Please place a sample image at test_data/sample_image.jpg")
        return None
    
    url = f"{BASE_URL}/upload/image"
    
    # Prepare form data
    with open(TEST_IMAGE_PATH, 'rb') as image_file:
        files = {
            'file': ('defect_image.jpg', image_file, 'image/jpeg')
        }
        
        data = {
            'plant_site': 'Plant_B',
            'captured_at': '2024-03-05T14:15:00',
            'shift': 'afternoon',
            'inspection_line': 'gate03',
            'tags': json.dumps([
                {'name': 'defect', 'description': 'Quality defect', 'color': '#FFA500'}
            ])
        }
        
        print_info(f"Uploading image: {TEST_IMAGE_PATH.name}")
        print_info(f"Plant: {data['plant_site']}, Shift: {data['shift']}")
        
        response = requests.post(url, files=files, data=data, headers=HEADERS)
    
    if response.status_code == 201:
        result = response.json()
        print_success("Image uploaded successfully!")
        print(f"  Message: {result['message']}")
        print(f"  Image ID: {result['id']}")
        print(f"  Image UUID: {result['image_id']}")
        print(f"  Filename: {result['filename']}")
        print(f"  Storage Key: {result['storage_key']}")
        print(f"  Size: {result['file_size_bytes'] / 1024:.2f} KB")
        print(f"  Dimensions: {result['width']}x{result['height']}")
        print(f"  Checksum: {result['checksum'][:16]}...")
        print(f"  Status: {result['status']}")
        print(f"  Tags: {len(result['tags'])} tags")
        return result
    else:
        print_error(f"Upload failed: {response.status_code}")
        print(response.text)
        return None


def test_image_upload_from_video():
    """Test uploading an image that's a frame from a video."""
    print("\n" + "="*60)
    print("TEST 3: Image Upload (Video Frame)")
    print("="*60)
    
    # First, upload a video to get video_id
    video_result = test_video_upload()
    
    if not video_result:
        print_warning("Skipping video frame test - video upload failed")
        return None
    
    if not TEST_IMAGE_PATH.exists():
        print_error(f"Image file not found: {TEST_IMAGE_PATH}")
        return None
    
    url = f"{BASE_URL}/upload/image"
    
    # Upload image as a video frame
    with open(TEST_IMAGE_PATH, 'rb') as image_file:
        files = {
            'file': ('frame_0001.jpg', image_file, 'image/jpeg')
        }
        
        data = {
            'plant_site': video_result['plant_site'],
            'captured_at': video_result['recorded_at'],
            'shift': video_result['shift'],
            'video_id': str(video_result['id']),
            'frame_number': '1',
        }
        
        print_info(f"Uploading frame from video ID: {video_result['id']}")
        
        response = requests.post(url, files=files, data=data, headers=HEADERS)
    
    if response.status_code == 201:
        result = response.json()
        print_success("Video frame uploaded successfully!")
        print(f"  Image ID: {result['id']}")
        print(f"  Video ID: {result['video_id']}")
        print(f"  Frame Number: {result['frame_number']}")
        return result
    else:
        print_error(f"Upload failed: {response.status_code}")
        print(response.text)
        return None


def test_detection_upload(image_id: int):
    """Test detection upload endpoint."""
    print("\n" + "="*60)
    print("TEST 4: Detection Upload")
    print("="*60)
    
    url = f"{BASE_URL}/upload/detection"
    
    # Create a single detection
    detection_data = {
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
    
    print_info(f"Creating detection for image ID: {image_id}")
    print_info(f"Label: {detection_data['label']}, Confidence: {detection_data['confidence']}")
    
    response = requests.post(url, json=detection_data, headers=HEADERS)
    
    if response.status_code == 201:
        result = response.json()
        print_success("Detection created successfully!")
        print(f"  Detection ID: {result['id']}")
        print(f"  Detection UUID: {result['detection_id']}")
        print(f"  Label: {result['label']}")
        print(f"  Confidence: {result['confidence']}")
        print(f"  BBox: ({result['bbox_x']}, {result['bbox_y']}, {result['bbox_width']}, {result['bbox_height']})")
        print(f"  Embedding Generated: {result['embedding_generated']}")
        print(f"  Tags: {len(result['tags'])} tags")
        return result
    else:
        print_error(f"Upload failed: {response.status_code}")
        print(response.text)
        return None


def test_bulk_detection_upload(image_id: int):
    """Test bulk detection upload endpoint."""
    print("\n" + "="*60)
    print("TEST 5: Bulk Detection Upload")
    print("="*60)
    
    url = f"{BASE_URL}/upload/detections/bulk"
    
    # Create multiple detections
    bulk_data = {
        'detections': [
            {
                'image_id': image_id,
                'bbox_x': 0.1,
                'bbox_y': 0.1,
                'bbox_width': 0.2,
                'bbox_height': 0.2,
                'bbox_format': 'normalized',
                'label': 'fiber',
                'confidence': 0.88,
                'tags': [{'name': 'minor', 'color': '#FFFF00'}]
            },
            {
                'image_id': image_id,
                'bbox_x': 0.5,
                'bbox_y': 0.5,
                'bbox_width': 0.15,
                'bbox_height': 0.15,
                'bbox_format': 'normalized',
                'label': 'burn_mark',
                'confidence': 0.92,
                'tags': [{'name': 'major', 'color': '#FF6600'}]
            },
            {
                'image_id': image_id,
                'bbox_x': 0.7,
                'bbox_y': 0.3,
                'bbox_width': 0.1,
                'bbox_height': 0.1,
                'bbox_format': 'normalized',
                'label': 'scratch',
                'confidence': 0.85
            }
        ]
    }
    
    print_info(f"Creating {len(bulk_data['detections'])} detections for image ID: {image_id}")
    
    response = requests.post(url, json=bulk_data, headers=HEADERS)
    
    if response.status_code == 201:
        result = response.json()
        print_success("Bulk detections created successfully!")
        print(f"  Total: {result['total']}")
        print(f"  Created: {result['created']}")
        print(f"  Skipped: {result['skipped']}")
        print(f"  Failed: {result['failed']}")
        print(f"  Detection IDs: {result['detection_ids']}")
        if result['errors']:
            print_warning(f"  Errors: {result['errors']}")
        return result
    else:
        print_error(f"Upload failed: {response.status_code}")
        print(json.dumps(response.json(), indent=2))
        return None


def test_invalid_uploads():
    """Test error handling with invalid uploads."""
    print("\n" + "="*60)
    print("TEST 6: Invalid Upload Handling")
    print("="*60)
    
    # Test 1: Invalid file type for video
    print_info("Test 6.1: Upload text file as video")
    url = f"{BASE_URL}/upload/video"
    
    with open(__file__, 'rb') as file:  # Upload this Python script as video
        files = {'file': ('test.py', file, 'text/plain')}
        data = {
            'plant_site': 'Plant_A',
            'recorded_at': '2024-03-05T10:00:00'
        }
        response = requests.post(url, files=files, data=data, headers=HEADERS)
    
    if response.status_code == 400:
        print_success("Correctly rejected invalid video file type")
    else:
        print_error(f"Expected 400, got {response.status_code}")
    
    # Test 2: Invalid datetime format
    print_info("\nTest 6.2: Invalid datetime format")
    if TEST_IMAGE_PATH.exists():
        url = f"{BASE_URL}/upload/image"
        with open(TEST_IMAGE_PATH, 'rb') as image_file:
            files = {'file': ('test.jpg', image_file, 'image/jpeg')}
            data = {
                'plant_site': 'Plant_A',
                'captured_at': 'invalid-date'  # Invalid format
            }
            response = requests.post(url, files=files, data=data, headers=HEADERS)
        
        if response.status_code == 400:
            print_success("Correctly rejected invalid datetime format")
        else:
            print_error(f"Expected 400, got {response.status_code}")
    
    # Test 3: Detection with invalid bbox
    print_info("\nTest 6.3: Detection with invalid bounding box")
    url = f"{BASE_URL}/upload/detection"
    invalid_detection = {
        'image_id': 999999,  # Non-existent image
        'bbox_x': 1.5,  # Invalid normalized coordinate
        'bbox_y': 0.5,
        'bbox_width': 0.2,
        'bbox_height': 0.2,
        'bbox_format': 'normalized',
        'label': 'test',
        'confidence': 0.9
    }
    
    response = requests.post(url, json=invalid_detection, headers=HEADERS)
    
    if response.status_code in [400, 404]:
        print_success("Correctly rejected invalid detection")
    else:
        print_error(f"Expected 400 or 404, got {response.status_code}")


def run_all_tests():
    """Run all upload tests."""
    print("\n" + "="*60)
    print("IMPURITY SEARCH ENGINE - UPLOAD ENDPOINT TESTS")
    print("="*60)
    
    # Ensure test data directory exists
    TEST_DATA_DIR.mkdir(exist_ok=True)
    
    # Test 1: Video Upload
    video_result = test_video_upload()
    
    # Test 2: Image Upload
    image_result = test_image_upload()
    
    # Test 3: Image Upload (Video Frame)
    # This is done inside the test
    
    # Test 4 & 5: Detection Uploads (need an image first)
    if image_result:
        test_detection_upload(image_result['id'])
        test_bulk_detection_upload(image_result['id'])
    else:
        print_warning("Skipping detection tests - no image uploaded")
    
    # Test 6: Invalid uploads
    test_invalid_uploads()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print_success("All tests completed!")
    print_info("Check the output above for individual test results")


if __name__ == "__main__":
    run_all_tests()