import pytest
import json
from unittest.mock import patch, MagicMock
from functions import handler

DUMMY_IMAGE_URL = "https://example.com/dummy.jpg"

@pytest.fixture
def image_list():
    return {
        "claim_id": "CLM-2025-00123",
        "images": [DUMMY_IMAGE_URL]
    }

@patch("functions.handler.download_image")
@patch("functions.handler.get_perceptual_hash")
@patch("functions.handler.get_blur_score")
@patch("functions.handler.rekognition_client.detect_labels")
@patch("functions.handler.requests.get")
def test_lambda_handler_good_image(
    mock_requests_get,
    mock_detect_labels,
    mock_blur_score,
    mock_get_hash,
    mock_download_image,
    image_list
):
    # Mock requests.get to return fake image content
    mock_requests_get.return_value.content = b"fake_image_bytes"
    mock_requests_get.return_value.raise_for_status = lambda: None

    # Create a fake PIL image
    from PIL import Image
    image = Image.new("RGB", (100, 100))
    mock_download_image.return_value = image
    mock_get_hash.return_value = 123456789  # Dummy hash
    mock_blur_score.return_value = 150

    # Rekognition mock
    mock_detect_labels.return_value = {
        "Labels": [
            {"Name": "Roof Damage", "Confidence": 95.0}
        ]
    }

    response = handler.lambda_handler({"body": json.dumps(image_list)}, {})
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert "claim_id" in body
    assert body["claim_id"] == "CLM-2025-00123"
    assert "overall_damage_severity" in body
    assert body["overall_damage_severity"] >= 0.0

def test_lambda_handler_no_images():
    response = handler.lambda_handler({"body": json.dumps({"images": []})}, {})
    assert response["statusCode"] == 422
