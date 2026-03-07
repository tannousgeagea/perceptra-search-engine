# examples/curl_examples.sh

#!/bin/bash

API_KEY="ise_your_api_key_here"
BASE_URL="http://localhost:8000/api"

# 1. Upload Video
echo "=== Uploading Video ==="
curl -X POST "${BASE_URL}/upload/video" \
  -H "X-API-Key: ${API_KEY}" \
  -F "file=@sample_video.mp4" \
  -F "plant_site=Plant_A" \
  -F "recorded_at=2024-03-05T10:30:00" \
  -F "shift=morning" \
  -F 'tags=[{"name":"quality-check","color":"#FF5733"}]'

echo -e "\n\n"

# 2. Upload Image
echo "=== Uploading Image ==="
curl -X POST "${BASE_URL}/upload/image" \
  -H "X-API-Key: ${API_KEY}" \
  -F "file=@sample_image.jpg" \
  -F "plant_site=Plant_B" \
  -F "captured_at=2024-03-05T14:15:00" \
  -F "shift=afternoon" \
  -F 'tags=[{"name":"defect","color":"#FFA500"}]'

echo -e "\n\n"

# 3. Create Detection
echo "=== Creating Detection ==="
curl -X POST "${BASE_URL}/upload/detection" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "image_id": 1,
    "bbox_x": 0.25,
    "bbox_y": 0.35,
    "bbox_width": 0.15,
    "bbox_height": 0.20,
    "bbox_format": "normalized",
    "label": "metal_scrap",
    "confidence": 0.95,
    "tags": [
      {"name": "verified", "color": "#00FF00"}
    ]
  }'

echo -e "\n\n"

# 4. Bulk Create Detections
echo "=== Creating Bulk Detections ==="
curl -X POST "${BASE_URL}/upload/detections/bulk" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "detections": [
      {
        "image_id": 1,
        "bbox_x": 0.1, "bbox_y": 0.1,
        "bbox_width": 0.2, "bbox_height": 0.2,
        "bbox_format": "normalized",
        "label": "fiber",
        "confidence": 0.88
      },
      {
        "image_id": 1,
        "bbox_x": 0.5, "bbox_y": 0.5,
        "bbox_width": 0.15, "bbox_height": 0.15,
        "bbox_format": "normalized",
        "label": "burn_mark",
        "confidence": 0.92
      }
    ]
  }'