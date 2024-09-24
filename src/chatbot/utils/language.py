class Language:
    """
    Sets the language used to create the agent executor.
    """

    _instance = None

    def set_language(self, language):
        self.language = language

    def __init_(self):
        raise RuntimeError("Call get_instance() instead")

    @classmethod
    def get_instance(cls, language="Deutsch"):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.set_language(language)
        return cls._instance


config_language = Language.get_instance()
