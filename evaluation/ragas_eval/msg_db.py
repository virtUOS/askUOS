queries = [
    "How many examiners are required to evaluate the Bachelor- bzw. Masterarbeit? Program Biology",
    "What are the admission requirements for undergraduate programs?",
    "What is the deadline for submitting my application?",
    "Are there any scholarships available for international students?",
    "Can the Bachelor- bzw. Masterarbeit be in a foreign language? Prgram Biology",
]

reference_tool_calls = [
    {
        "name": "examination_regulations",
        "args": {
            "query": "Anzahl der Prüfer für die Bewertung der Bachelor- bzw. Masterarbeit",
            "filter_program_name": "Biologie",
        },
    },
    {
        "name": "custom_university_web_search",
        "args": {
            "query": "Zulassungsvoraussetzungen für Bachelor-Studiengänge an der Universität Osnabrück"
        },
    },
    {
        "name": "custom_university_web_search",
        "args": {"query": "Bewerbungsfristen Universität Osnabrück"},
    },
    {
        "name": "custom_university_web_search",
        "args": {
            "query": "Stipendien für internationale Studierende an der Universität Osnabrück"
        },
    },
    {
        "name": "examination_regulations",
        "args": {
            "query": "Kann die Bachelor- bzw. Masterarbeit in einer Fremdsprache verfasst werden?",
            "filter_program_name": "Biologie",
        },
    },
]
