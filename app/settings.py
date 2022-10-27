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
    """

    api_key_length: int = 20
    subset_size: int = 10
