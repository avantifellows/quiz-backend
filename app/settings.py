from pydantic import BaseSettings


class Settings(BaseSettings):
    """Custom settings which are used across the app

    Attributes
    ----------
    api_key_length : int
        the length of an organization's api key
    subset_size : int
        the number of questions which collectively can be called a `subset`.
        (read about subset pattern - https://www.notion.so/avantifellows/Database-4cfd0b2c9d6141fd88197649b0593318)
    cms_service_endpoint : str
        base URL of nex-gen-cms (new CMS), e.g. http://localhost:8080, used to fetch
        assembled chapter-test JSON for CMS->quiz ingest.
    cms_service_token : str
        bearer token for the CMS /api/service/* routes (matches CMS_SERVICE_TOKEN there).
    """

    api_key_length: int = 20
    subset_size: int = 10
    cms_service_endpoint: str = ""
    cms_service_token: str = ""
