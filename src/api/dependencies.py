from fastapi import Request

from src.chatbot.agents.graph import CampusManagementAgent


def get_agent(request: Request) -> CampusManagementAgent:
    return request.app.state.agent
