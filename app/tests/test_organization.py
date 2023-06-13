from .base import BaseTestCase
from fastapi import status


class OrganizationsTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()

    def test_create_organization(self):
        new_organization_data = {
            "name": "Test Org 2",
            "location": "Test Location 2",
            "contact": "Test Contact 2",
        }
        response = self.client.post("/organizations/", json=new_organization_data)
        assert response.status_code == status.HTTP_200_OK
        new_organization = response.json()
        assert new_organization["name"] == new_organization_data["name"]

    def test_get_organization_if_key_valid(self):
        response = self.client.get(
            f"/organizations/authenticate/{self.organization['key']}"
        )
        organization = response.json()
        assert organization["_id"] == self.organization_id

    def test_get_organization_returns_error_if_key_invalid(self):
        response = self.client.get("/organizations/authenticate/invalid_key")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        response = response.json()
        assert response["detail"] == "org with key invalid_key not found"
