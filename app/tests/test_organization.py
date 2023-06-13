from .base import BaseTestCase
from fastapi import status
from unittest.mock import patch


class OrganizationsTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()

    def test_create_organization(self):
        new_organization_data = {
            "name": "Test Org 2",
        }
        response = self.client.post("/organizations/", json=new_organization_data)
        assert response.status_code == status.HTTP_201_CREATED
        new_organization = response.json()
        assert new_organization["name"] == new_organization_data["name"]

    @patch("routers.organizations.generate_random_string", return_value="mocked_key")
    def test_create_organization_with_duplicate_api_key(self, mock):
        # Create the first organization with mocked_key
        new_organization_data = {
            "name": "Test Org 2",
        }
        response = self.client.post("/organizations/", json=new_organization_data)
        assert response.status_code == status.HTTP_201_CREATED
        new_organization = response.json()
        assert new_organization["name"] == new_organization_data["name"]
        assert new_organization["key"] == "mocked_key"

        # Try creating a second organization with the same key
        new_organization_data = {
            "name": "Test Org 3",
        }
        response = self.client.post("/organizations/", json=new_organization_data)
        assert response.status_code == status.HTTP_409_CONFLICT
        response = response.json()
        assert response["detail"] == "API key mocked_key already exists"

    def test_authenticate_valid_api_key(self):
        response = self.client.get(
            f"/organizations/authenticate/{self.organization_api_key}"
        )
        organization = response.json()
        assert response.status_code == status.HTTP_200_OK
        assert organization["name"] == self.organization["name"]

    def test_authentication_fails_for_invalid_api_key(self):
        response = self.client.get("/organizations/authenticate/invalid_key")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        response = response.json()
        assert response["detail"] == "org with key invalid_key not found"
