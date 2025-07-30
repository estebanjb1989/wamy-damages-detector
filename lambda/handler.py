import json
import boto3
from datetime import datetime
from urllib.parse import urlparse
from PIL import Image, ImageFilter, ImageStat
import requests
from io import BytesIO
from PIL import Image, ImageStat, ImageFilter
import imagehash

rekognition_client = boto3.client('rekognition', region_name='us-east-2')

def download_image(url):
    response = requests.get(url)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert('RGB')

def get_blur_score(image):
    # Use variance of Laplacian as blur metric
    grayscale = image.convert("L")
    laplacian = grayscale.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(laplacian)
    return stat.var[0]  # Variance of edge image

def get_perceptual_hash(image):
    return imagehash.phash(image)

def deduplicate_and_filter(images, blur_threshold=100, hash_distance_threshold=6):
    grouped = []
    hashes = []
    url_to_image = {}
    
    for url in images:
        try:
            img = download_image(url)
            url_to_image[url] = img
            h = get_perceptual_hash(img)

            found_group = False
            for group in grouped:
                if h - group['hash'] <= hash_distance_threshold:
                    group['candidates'].append((url, get_blur_score(img)))
                    found_group = True
                    break
            
            if not found_group:
                grouped.append({
                    'hash': h,
                    'candidates': [(url, get_blur_score(img))]
                })

        except Exception as e:
            print(f"Error downloading or processing {url}: {e}")
            continue
    
    final_images = []
    discarded_duplicates = []
    for group in grouped:
        candidates = sorted(group['candidates'], key=lambda x: x[1], reverse=True)
        sharpest = candidates[0]
        if sharpest[1] >= blur_threshold:
            final_images.append(sharpest[0])
        for discarded in candidates[1:]:
            discarded_duplicates.append(discarded[0])

    return final_images, discarded_duplicates

def check_image_quality(image_url, blur_threshold=100, dark_threshold=40):
    """
    Returns True if image is good quality (not blurry, not too dark).
    Otherwise False.
    """
    try:
        response = requests.get(image_url)
        image = Image.open(BytesIO(response.content))

        # Check blur
        gray = image.convert('L')
        laplacian = gray.filter(ImageFilter.FIND_EDGES)
        pixels = list(laplacian.getdata())
        mean = sum(pixels) / len(pixels)
        variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)

        if variance < blur_threshold:
            print(f"Image {image_url} discarded for being blurry (variance={variance:.2f})")
            return False

        # Check darkness (average brightness)
        stat = ImageStat.Stat(gray)
        brightness = stat.mean[0]
        if brightness < dark_threshold:
            print(f"Image {image_url} discarded for being too dark (brightness={brightness:.2f})")
            return False

        return True

    except Exception as e:
        print(f"Error checking image quality {image_url}: {str(e)}")
        # If error occurs assume bad quality
        return False


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
    
    # Step 1: Deduplicate and filter blurry
    final_images, duplicates = deduplicate_and_filter(images)
    print(f"Kept {len(final_images)} high-quality images, discarded {len(duplicates)} duplicates")

    results = []
    discarded_low_quality = 0
    discarded_unrelated = 0

    for image_url in images:
        print(f"Processing image: {image_url}")
        
        if not check_image_quality(image_url):
            discarded_low_quality += 1
            results.append({
                "url": image_url,
                "wind_damage": None,
                "severity": 0,
                "area": None,
                "quality": 0,
                "discarded_low_quality": True,
                "discarded_unrelated": False
            })
            continue
        
        is_damaged, severity, area, unrelated = detect_wind_damage(image_url)

        if unrelated:
            discarded_unrelated += 1
            results.append({
                "url": image_url,
                "wind_damage": None,
                "severity": 0,
                "area": None,
                "quality": 0,
                "discarded_low_quality": False,
                "discarded_unrelated": True
            })
            continue
        
        results.append({
            "url": image_url,
            "wind_damage": is_damaged,
            "severity": severity,
            "area": area,
            "quality": severity,
            "discarded_low_quality": False,
            "discarded_unrelated": False
        })
    
    summary = generate_summary(
        claim_id, 
        images, 
        results, 
        discarded_low_quality,
        discarded_unrelated,
        final_images,
        duplicates
    )
    
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
                return True, severity, area, False  # is_damaged, severity, area, unrelated=False

        return None, 0, None, True  # unrelated image

    except Exception as e:
        print(f"Error processing image {image_url}: {str(e)}")
        return None, 0, None, True  # treat errors as unrelated

def generate_summary(
        claim_id, 
        all_images, 
        results, 
        discarded_low_quality, 
        discarded_unrelated,
        final_images,
        duplicates
    ):
    damaged_images = [r for r in results if r["wind_damage"]]
    
    weighted_sum = sum(r["severity"] * r.get("quality", 1) for r in damaged_images)
    total_quality = sum(r.get("quality", 1) for r in damaged_images)
    avg_severity = round(weighted_sum / total_quality, 1) if total_quality else 0.0

    summary = {
        "claim_id": claim_id,
        "source_images": {
            "total": len(all_images),
            "analyzed": len(final_images),
            "discarded_low_quality": discarded_low_quality,
            "discarded_unrelated": discarded_unrelated,
            "discarded_duplicates": len(duplicates),
            "clusters": len(final_images)
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
            confirmed = [i for i in items if i["severity"] >= 2]
            damage_confirmed = len(confirmed) >= 2
            area_severity = round(
                sum(i["severity"] for i in confirmed) / len(confirmed), 1
            ) if confirmed else 0.0

            summary["areas"].append({
                "area": area,
                "damage_confirmed": damage_confirmed,
                "primary_peril": "wind" if damage_confirmed else None,
                "count": len(confirmed),
                "avg_severity": area_severity,
                "representative_images": [i["url"] for i in confirmed[:1]] if confirmed else [],
                "notes": f"Damage {'confirmed' if damage_confirmed else 'not confirmed'} in {area} area."
            })

    return summary


