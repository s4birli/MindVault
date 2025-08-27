# tests/test_agent_search.py
"""
Tests for the agent framework search functionality.
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add the api directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

from api.main import app

client = TestClient(app)


class TestAgentSearch:
    """Test cases for the agent search functionality."""
    
    def test_hmrc_email_search_intent_detection(self):
        """Test that HMRC email queries are correctly identified and processed."""
        response = client.post(
            "/agent/act",
            json={"text": "HMRC'den gelen en son email neydi?"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that the intent was correctly identified
        assert data["intent"] == "search.latest_from"
        
        # Check that parameters were correctly extracted
        assert data["params_used"] is not None
        assert data["params_used"]["sender"] == "hmrc"
        assert data["params_used"]["limit"] == 1
        assert data["params_used"]["language"] == "tr"
        
        # Check that result is structured correctly
        assert "result" in data
        assert data["result"] is not None
        assert "items" in data["result"]
        assert isinstance(data["result"]["items"], list)
    
    def test_hmrc_email_search_with_custom_params(self):
        """Test HMRC email search with custom parameters."""
        response = client.post(
            "/agent/act",
            json={
                "text": "show me hmrc email",
                "params": {"limit": 3}
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that the intent was correctly identified
        assert data["intent"] == "search.latest_from"
        
        # Check that custom limit parameter was used (overrides default)
        assert data["params_used"]["limit"] == 3
        # But other defaults should remain
        assert data["params_used"]["sender"] == "hmrc"
        assert data["params_used"]["domain"] == "hmrc.gov.uk"
        
        # Check result structure
        assert "result" in data
        assert "items" in data["result"]
        assert isinstance(data["result"]["items"], list)
    
    def test_no_matching_agent_fallback(self):
        """Test that unrecognized queries return appropriate fallback message."""
        response = client.post(
            "/agent/act",
            json={"text": "nonsense query"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that no intent was detected
        assert data["intent"] is None
        assert data["params_used"] is None
        
        # Check fallback message
        assert "result" in data
        assert "message" in data["result"]
        assert "No matching agent" in data["result"]["message"]
    
    def test_agent_endpoint_structure(self):
        """Test that agent responses have the correct structure."""
        response = client.post(
            "/agent/act",
            json={"text": "latest email from HMRC"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields are present
        required_fields = ["intent", "params_used", "result"]
        for field in required_fields:
            assert field in data
        
        # If intent is found, check result structure
        if data["intent"] is not None:
            assert "items" in data["result"]
            
            # Check each item has expected structure (if any items exist)
            for item in data["result"]["items"]:
                expected_item_fields = ["id", "title", "ts", "provider", "url"]
                for field in expected_item_fields:
                    assert field in item
                
                # Check types
                assert isinstance(item["id"], str)
                # title, ts, provider, url can be None
                if item["title"] is not None:
                    assert isinstance(item["title"], str)
                if item["ts"] is not None:
                    assert isinstance(item["ts"], str)  # ISO format string
                if item["provider"] is not None:
                    assert isinstance(item["provider"], str)
                if item["url"] is not None:
                    assert isinstance(item["url"], str)
    
    def test_domain_based_search(self):
        """Test domain-based email search."""
        response = client.post(
            "/agent/act",
            json={"text": "latest email from wearedjr.com"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check intent and parameters
        assert data["intent"] == "search.latest_from"
        assert data["params_used"]["domain"] == "wearedjr.com"
        assert data["params_used"]["limit"] == 1
        assert data["params_used"]["language"] == "en"
        
        # Check result structure
        assert "result" in data
        assert "items" in data["result"]
        assert isinstance(data["result"]["items"], list)
    
    def test_date_window_search(self):
        """Test date window functionality."""
        response = client.post(
            "/agent/act",
            json={"text": "last 3 days emails"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that date_from parameter was added
        assert data["intent"] == "search.latest_from"
        assert "date_from" in data["params_used"]
        assert data["params_used"]["language"] == "en"
        
        # Check result structure
        assert "result" in data
        assert "items" in data["result"]
    
    def test_request_with_optional_fields(self):
        """Test request with optional thread_id and confirm fields."""
        response = client.post(
            "/agent/act",
            json={
                "text": "latest email from HMRC",
                "thread_id": "test-thread-123",
                "confirm": True
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # The agent should still work with optional fields
        assert data["intent"] == "search.latest_from"
        assert "result" in data
