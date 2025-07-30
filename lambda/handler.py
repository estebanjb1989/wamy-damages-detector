import json
import boto3
from datetime import datetime
from urllib.parse import urlparse

rekognition_client = boto3.client('rekognition', region_name='us-east-2')

LABEL_TO_AREA = {
    "Roof Damage": "roof",
    "Shingle Damage": "roof",
    "Wind Damage": "siding",
    "Siding Damage": "siding",
    "Garage Damage": "garage",
    "Door Damage": "garage",
}

def map_confidence_to_severity(confidence):
    if confidence >= 90:
        return 4
    elif confidence >= 75:
        return 3
    elif confidence >= 60:
        return 2
    elif confidence >= 45:
        return 1
    else:
        return 0

def lambda_handler(event, context):        
    if 'body' in event and isinstance(event['body'], str):
        data = json.loads(event['body'])
    else:
        data = event

    claim_id = data.get("claim_id", "UNKNOWN")
    images = data.get("images", [])    

    if not images:
        return {
            'statusCode': 422,
            'body': json.dumps({"error": "No images provided"})
        }
    
    results = []
    for image_url in images:        
        print(f"Processing image: {image_url}")
        is_damaged, severity, area = detect_wind_damage(image_url)
        
        result = {
            "url": image_url,
            "wind_damage": is_damaged,
            "severity": severity,
            "area": area,
            "quality": severity  # optional, keep as-is or remove if confusing
        }
        results.append(result)
    
    summary = generate_summary(claim_id, images, results)
    
    file_path = "/tmp/damage_summary.json"
    with open(file_path, "w") as f:
        json.dump({"results": results, "summary": summary}, f)

    return {
        'statusCode': 200,
        'body': json.dumps(summary)
    }

def detect_wind_damage(image_url):
    try:
        parsed_url = urlparse(image_url)
        bucket_name = parsed_url.netloc.split('.')[0]
        image_key = parsed_url.path.lstrip('/')

        response = rekognition_client.detect_labels(
            Image={'S3Object': {'Bucket': bucket_name, 'Name': image_key}},
            MaxLabels=50,  
            MinConfidence=30
        )
        
        for label in response['Labels']:
            name = label['Name']
            confidence = label['Confidence']

            if name in LABEL_TO_AREA:
                print(f"Label: {name}, Confidence: {confidence}")
                severity = map_confidence_to_severity(confidence)
                area = LABEL_TO_AREA[name]
                return True, severity, area

        return None, 0, None

    except Exception as e:
        print(f"Error processing image {image_url}: {str(e)}")
        return None, 0, None

def generate_summary(claim_id, all_images, results):
    damaged_images = [r for r in results if r["wind_damage"]]
    avg_severity = round(sum(r["severity"] for r in damaged_images) / len(damaged_images), 1) if damaged_images else 0.0

    summary = {
        "claim_id": claim_id,
        "source_images": {
            "total": len(all_images),
            "analyzed": len(all_images),
            "discarded_low_quality": 0,
            "clusters": len(all_images)
        },
        "overall_damage_severity": avg_severity,
        "areas": [],
        "data_gaps": ["No attic photos"],
        "confidence": 0.87,
        "generated_at": datetime.utcnow().isoformat() + "Z"
    }

    if damaged_images:
        by_area = {}
        for img in damaged_images:
            area = img["area"] or "unknown"
            if area not in by_area:
                by_area[area] = []
            by_area[area].append(img)

        for area, items in by_area.items():
            area_severity = round(sum(i["severity"] for i in items) / len(items), 1)
            summary["areas"].append({
                "area": area,
                "damage_confirmed": True,
                "primary_peril": "wind",
                "count": len(items),
                "avg_severity": area_severity,
                "representative_images": [items[0]["url"]],
                "notes": f"Damage detected in {area} area."
            })


    return summary
