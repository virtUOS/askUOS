from src.chatbot.utils.agent_helpers import llm


class VisitedLinks:
    """
    Singleton class to keep track of visited links.
    It maintains a list of links that have been visited.
    Attributes:
        _instance (VisitedLinks): The singleton instance of the class.
        links (list): A list to store visited links.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VisitedLinks, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not self.__dict__:
            self.urls = []

    def clear(self):
        """
        Cleans the list of visited links.
        """
        self.urls = []

    def __call__(self):
        return self.urls


visited_links = VisitedLinks()
