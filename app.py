from pathlib import Path
import traceback
import asyncio
import uvicorn
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from mcp_client import weather_mcp_search, forecast_mcp_search


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Weather Agent",
    description="AI-Powered Weather Agent using MCP + OpenWeatherMap",
    version="1.0.0"
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)


class WeatherRequest(BaseModel):
    city: str


def parse_weather(raw) -> dict:
    """Extract current weather fields from MCP response."""
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and "text" in item:
                import json
                try:
                    data = json.loads(item["text"])
                    if isinstance(data, dict) and "temperature_c" in data:
                        return data
                except Exception:
                    pass
            elif hasattr(item, "content"):
                import json
                try:
                    data = json.loads(str(item.content))
                    if isinstance(data, dict) and "temperature_c" in data:
                        return data
                except Exception:
                    pass
    return {}


def parse_forecast(raw) -> list:
    """Extract forecast list from MCP response."""
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and "text" in item:
                import json
                try:
                    data = json.loads(item["text"])
                    if isinstance(data, dict) and "forecast" in data:
                        return data["forecast"]
                except Exception:
                    pass
            elif hasattr(item, "content"):
                import json
                try:
                    data = json.loads(str(item.content))
                    if isinstance(data, dict) and "forecast" in data:
                        return data["forecast"]
                except Exception:
                    pass
    return []


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@app.post("/api/weather")
async def get_weather(request_data: WeatherRequest):
    city = request_data.city.strip()
    if not city:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "City name cannot be empty."}
        )

    try:
        weather_raw, forecast_raw = await asyncio.gather(
            weather_mcp_search(city),
            forecast_mcp_search(city),
        )

        weather = parse_weather(weather_raw)
        forecast = parse_forecast(forecast_raw)

        if not weather:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"City '{city}' not found or weather unavailable."}
            )

        return JSONResponse(content={
            "success": True,
            "weather": weather,
            "forecast": forecast,
        })

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Weather Agent API is running"}


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )