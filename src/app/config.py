from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "CONSUMA_"}

    default_iterations: int = 50_000
    max_workers: int = 4
    max_queue_size: int = 1000
    callback_timeout: int = 10
    callback_max_retries: int = 5
    rate_limit_requests: int = 500
    rate_limit_window: int = 60
    allow_private_callbacks: bool = False
    database_path: str = "requests.db"


settings = Settings()
