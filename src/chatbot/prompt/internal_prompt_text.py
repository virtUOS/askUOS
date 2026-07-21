"""Internal-only prompt strings.

Unlike the prompts in `prompts_example/`/`prompts/` (system messages, tool
descriptions the bot exposes to users, etc.), the strings here are
implementation details of the graph's own control flow: a structured-output
field description consumed only by the grading LLM's schema, and an internal
nudge message inserted when the judge node overrides the agent. A university
admin customizing the bot's wording/behavior has no reason to touch these,
so they're deliberately kept in Python source rather than the sysadmin-
facing prompt config -- changing one requires a code change and redeploy,
same as before this whole prompt-externalization effort.

`response_output_description` / `response_sources_description` are not
currently referenced anywhere in the live code (confirmed via repo-wide
search); kept here only for parity with prior behavior, safe to delete in a
future cleanup pass.
"""

from typing import Literal

internal_strings_english = {
    "response_output_description": "The final answer to respond to the user",
    "response_sources_description": (
        "The sources used to generate the answer. The sources should consist "
        "of a list of URLs. Only include the sources if the answer was "
        "extracted from the University of Osnabruek website."
    ),
    "grader_binary_score": "Documents are relevant to the user's question, 'yes' or 'no'",
    "use_tool_msg": (
        "Do not answer questions based on your Training knowledge. Use the "
        "tools at your disposal to obtain the information needed to answer "
        "the user's query."
    ),
}

internal_strings_deutsch = {
    "response_output_description": "Die endgültige Antwort, um dem Benutzer zu antworten",
    "response_sources_description": (
        "Die Quellen, die zur Erstellung der Antwort verwendet wurden. Die "
        "Quellen sollten aus einer Liste von URLs bestehen. Geben Sie die "
        "Quellen nur an, wenn die Antwort von der Website der Universität "
        "Osnabrück stammt."
    ),
    "grader_binary_score": "Relevanzpunktzahl 'ja' oder 'nein'",
    "use_tool_msg": (
        "Beantworten Sie Fragen nicht auf Grundlage Ihres Trainingswissens. "
        "Nutzen Sie die Ihnen zur Verfügung stehenden Tools, um die "
        "Informationen zu erhalten, die Sie zur Beantwortung der "
        "Benutzeranfrage benötigen."
    ),
}


def translate_internal_string(key: str, language: Literal["Deutsch", "English"] = "Deutsch") -> str:
    """Look up an internal (non-admin-configurable) prompt string by language."""
    table = internal_strings_english if language == "English" else internal_strings_deutsch
    return table[key]
