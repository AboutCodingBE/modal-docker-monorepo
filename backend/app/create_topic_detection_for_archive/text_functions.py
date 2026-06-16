import re
import nltk
from nltk.corpus import stopwords

# Check if stopwords are downloaded
try:
    stopwords.words("dutch")  # Check English stopwords as indicator
except LookupError:
    nltk.download("stopwords")  # Download stopwords only if not available


def remove_stopwords(text, language):
    """
    Removes stopwords from the given text.

    :param text: A string containing words separated by commas (e.g., "[word1, word2, word3]").
    :param language: The language for stopwords, defaults to "dutch".
    :return: A string with stopwords removed.
    """

    lang_map = {
        "en": "english",
        "nl": "dutch",
        "de": "german",
        "fr": "french",
        "es": "spanish",
        "it": "italian",
    }

    # Default to "dutch" if language isn't found in lang_map
    language = lang_map.get(language.lower(), "dutch")


    # Get the stopwords for the specified language
    stopwords_set = set(stopwords.words(language))

    # Split words by any whitespace or commas if brackets not provided
    words = text.replace("[", "").replace("]", "").replace(",", " ").split()
    # print("words",words)

    # Filter out stopwords and return the cleaned string
    cleaned_words = [
        word.strip() for word in words if word.strip().lower() not in stopwords_set
    ]

    return " ".join(cleaned_words)

def remove_numbers(text):
    return re.sub(r" \d+ ", " ", text)