import uvicorn

from engines.contracts.settings import get_settings


if __name__ == "__main__":
    settings = get_settings()

    uvicorn.run("app.app:app", host=settings.HOST, port=settings.PORT, reload=True)