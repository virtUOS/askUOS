from datetime import date
from typing import Literal


def get_current_date(language: Literal["English", "Deutsch"]) -> str:

    def get_month_name(month_number, language) -> str:
        """
        Returns the month name based on the month number and language.

        Args:
            month_number (int): The month number (1-12).
            language (str): The language for the month name ('English' or 'German').

        Returns:
            str: The month name in the specified language.
        """
        # Define dictionaries for month mappings
        months_english = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December",
        }

        months_german = {
            1: "Januar",
            2: "Februar",
            3: "März",
            4: "April",
            5: "Mai",
            6: "Juni",
            7: "Juli",
            8: "August",
            9: "September",
            10: "Oktober",
            11: "November",
            12: "Dezember",
        }

        # Select the appropriate dictionary based on the language
        if language.lower() == "english":
            months = months_english
        elif language.lower() == "deutsch":
            months = months_german
        else:
            raise ValueError(
                "Unsupported language. Choose either 'english' or 'deutsch'."
            )

        # Return the corresponding month name
        return months.get(month_number)

    current_date = date.today()
    month_name = get_month_name(current_date.month, language=language)
    return f"{month_name} {current_date.day}, {current_date.year}"
