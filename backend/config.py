from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "musicgraph"
    discogs_token: str = ""
    musicbrainz_app: str = "MusicGraph/1.0 (contact@example.com)"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
