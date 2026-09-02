import os 
import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from typing import TypedDict, Annotated
import operator
import uuid
import asyncio
import psycopg
from psycopg.rows import dict_row

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain_groq import ChatGroq
# from tools.tavily_tool import tavily_search
# from tools.flight_tool import search_flights
from mcp_client import tavily_mcp_search, aviation_mcp_call, extract_destination, forecast_mcp_search, weather_mcp_search


def get_database_url():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your Render PostgreSQL External Database URL to .env"
        )

    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")


# =========================
# LLM
# =========================

llm = ChatGroq(
    model="groq/compound-mini",
    api_key=GROQ_API_KEY
)


# =========================
# State
# =========================

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int
    weather_results: str


# =========================
# Flight Agent
# =========================

# def flight_agent(state: TravelState):
#     query = state["user_query"]
#     flight_data = search_flights(query)

#     return {
#         "flight_results": flight_data,
#         "messages": [
#             AIMessage(content="Flight results fetched.")
#         ],
#         "llm_calls": state.get("llm_calls", 0) + 1
#     }




# Flight Tool Router Prompt
FLIGHT_AGENT_PROMPT = """
You are a travel flight expert.

User Query:
{query}

Airport Information:
{airport_data}

Airline Information:
{airline_data}

Generate:

1. Likely departure airport
2. Likely arrival airport
3. Airlines serving this route
4. Typical flight duration
5. Estimated airfare range
6. Peak season pricing warning
7. Booking advice

Return concise travel guidance.
"""




def parse_mcp_output(mcp_res) -> str:
    """Safely convert MCP tool outputs to clean text without raw JSON/metadata blobs."""
    if not mcp_res:
        return ""
    if isinstance(mcp_res, list):
        extracted = []
        for item in mcp_res:
            if isinstance(item, dict) and "text" in item:
                text_content = item["text"]
                try:
                    data = json.loads(text_content)
                    if isinstance(data, dict):
                        if "results" in data and isinstance(data["results"], list):
                            snippets = [
                                f"{r.get('title', '')}: {r.get('content', '')}"
                                for r in data["results"]
                                if isinstance(r, dict)
                            ]
                            extracted.append("\n".join(snippets))
                        elif "forecast" in data and isinstance(data["forecast"], list):
                            fc_list = [
                                f"{f.get('datetime', '')}: {f.get('temperature', '')}°C, {f.get('weather', '')}"
                                for f in data["forecast"]
                                if isinstance(f, dict)
                            ]
                            extracted.append(f"City: {data.get('city', '')}\nForecast:\n" + "\n".join(fc_list))
                        elif "temperature_c" in data:
                            extracted.append(f"City: {data.get('city', '')}, Temp: {data.get('temperature_c', '')}°C, Condition: {data.get('condition', '')}")
                        else:
                            extracted.append(text_content)
                    else:
                        extracted.append(text_content)
                except Exception:
                    extracted.append(text_content)
            elif hasattr(item, "content"):
                extracted.append(str(item.content))
            else:
                extracted.append(str(item))
        return "\n".join(extracted)
    elif hasattr(mcp_res, "content"):
        return str(mcp_res.content)
    return str(mcp_res)


# Flight Agent
def flight_agent(state: TravelState):
    print("\nINSIDE FLIGHT AGENT\n")
    query = state["user_query"]

    try:
        airports = asyncio.run(aviation_mcp_call("list_airports"))
        airlines = asyncio.run(aviation_mcp_call("list_airlines"))

        prompt = FLIGHT_AGENT_PROMPT.format(
            query=query,
            airport_data=parse_mcp_output(airports)[:1000],
            airline_data=parse_mcp_output(airlines)[:1000]
        )

        response = llm.invoke([
            SystemMessage(content="You are an expert travel flight planner."),
            HumanMessage(content=prompt)
        ])

        flight_data = response.content
    except Exception as e:
        print(f"Aviation MCP unavailable ({e}), trying fallback flight tool...")
        try:
            from tools.flight_tool import search_flights
            flight_data = search_flights(query)
        except Exception as err:
            flight_data = f"Flight information: Standard routes available for {query}."

    return {
        "flight_results": str(flight_data)[:1200],
        "messages": [
            AIMessage(content="Flight recommendations generated")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Hotel Agent
# =========================

def hotel_agent(state: TravelState):
    query = f"Best hotels for {state['user_query']}"
    try:
        hotel_raw = asyncio.run(tavily_mcp_search(query))
        hotel_str = parse_mcp_output(hotel_raw)
    except Exception as e:
        print(f"Tavily MCP error: {e}")
        hotel_str = f"Recommended hotels in target location for {state['user_query']}."

    return {
        "hotel_results": hotel_str[:1200],
        "messages": [
            AIMessage(content="Hotel information fetched.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Weather Agent
# =========================

def weather_agent(state: TravelState):
    try:
        city = extract_destination(state["user_query"])
        weather_raw = asyncio.run(weather_mcp_search(city))
        forecast_raw = asyncio.run(forecast_mcp_search(city))

        w_str = parse_mcp_output(weather_raw)
        f_str = parse_mcp_output(forecast_raw)

        res = f"Current Weather:\n{w_str}\n\nForecast:\n{f_str}"
    except Exception as e:
        print(f"Weather MCP error: {e}")
        res = "Weather data currently unavailable."

    return {
        "weather_results": str(res)[:800],
        "messages": [
            AIMessage(content="Weather information fetched")
        ]
    }


# =========================
# Itinerary Agent
# =========================

def itinerary_agent(state: TravelState):
    prompt = f"""
Create a complete travel itinerary.

User Query:
{state['user_query']}

Flight Results:
{str(state.get('flight_results', ''))[:800]}

Hotel Results:
{str(state.get('hotel_results', ''))[:800]}

Weather Results:
{str(state.get('weather_results', ''))[:600]}

Make the itinerary practical, budget-aware, and easy to follow.
"""

    response = llm.invoke([
        SystemMessage(content="You are an expert travel planner."),
        HumanMessage(content=prompt)
    ])

    return {
        "itinerary": response.content,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Final Response Agent
# =========================

def final_agent(state: TravelState):
    final_prompt = f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Flights:
{str(state.get('flight_results', ''))[:800]}

Hotels:
{str(state.get('hotel_results', ''))[:800]}

Weather:
{str(state.get('weather_results', ''))[:600]}

Itinerary:
{str(state.get('itinerary', ''))[:1000]}

Format the final answer beautifully using these sections:

1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Information
5. Day-by-Day Itinerary
6. Estimated Budget
7. Final Recommendations

Important:
- Be clear and practical.
- Mention that live flight API may not provide ticket prices if pricing is unavailable.
- Include weather-based travel advice.
- Keep the response useful for real travel planning.
"""

    response = llm.invoke([
        SystemMessage(content="You are a professional AI travel booking assistant."),
        HumanMessage(content=final_prompt)
    ])

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


# =========================
# Build Graph
# =========================

graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent", weather_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "weather_agent")
graph.add_edge("weather_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)


# =========================
# PostgreSQL Checkpointer
# =========================
DATABASE_URL = get_database_url()

_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)



# =========================
# Function for FastAPI
# =========================

def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = travel_graph.invoke(
        {
            "messages": [
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "weather_results": "",
            "itinerary": "",
            "llm_calls": 0
        },
        config=config
    )

    final_answer = result["messages"][-1].content

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "itinerary": result.get("itinerary", ""),
        "llm_calls": result.get("llm_calls", 0),
    }