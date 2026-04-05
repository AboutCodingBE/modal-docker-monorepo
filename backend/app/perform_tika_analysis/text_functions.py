from langdetect import detect
import re
import nltk
from nltk.corpus import stopwords

def get_word_count(text):
    """
    Counts the number of words in the given text.
    Args:
        text (str): Input text to count words from
    Returns:
        int: Number of words in the text, or 0 if text is empty
    """
    return len(text.split()) if text else 0

def file_filter(filename):
    """
    Filters out system files and binary/media file types.
    Args:
        filename (str): Name of the file to check
    Returns:
        bool: True if file should be included, False if it should be filtered out
    """
    return not filename.startswith('.') and not filename.endswith(('.exe', '.EXE','.css','.db', '.php', '.dd', '.js', '.json', '.tar', '.zip', '.gz', '.jpg', 'png', '.jpeg', '.tif', '.tiff', '.JPG', '.PNG', '.JPEG', '.TIF', '.TIFF', 'Tiff', '.tar', '.dll', '.DLL', '.cab', '.CAB', '.gz', '.GZ', '.mov', '.MOV', '.mp3', '.MP3', '.avi', '.mp4', '.MP4','.AVI','.cr2', '.CR2', '.psd', '.PSD'))

def file_filter_include(filename):
    """
    Specifically filters for image files, including only common image formats.
    Args:
        filename (str): Name of the file to check
    Returns:
        bool: True if file is an image file, False otherwise
    """
    return not filename.startswith('.') and filename.endswith(('.jpg', '.png', '.jpeg', '.tif', '.tiff', '.JPG', '.PNG', '.JPEG', '.TIF', '.TIFF'))

def path_filter(path):
    """
    Filters out specific tool-related paths.
    Args:
        path (str): File path to check
    Returns:
        bool: True if path should be included, False if it should be filtered out
    """
    filters = ('brunnhilde', 'siegfried', 'metadata')  # Add as many strings as needed
    return not any(filter_str in path for filter_str in filters)

def detect_lang(text):
    """
    Detects the language of the given text.
    Args:
        text (str): Text to analyze
    Returns:
        str: Language code, or 'und' (undefined) if text is empty
    """
    return detect(text) if text else "und"

def normalize_newlines(text):
    """
    Removes excessive empty lines, keeping at most two consecutive empty lines.
    Lines containing only spaces/tabs are considered empty.
    Also strips empty lines from the start and end.

    Args:
        text (str): Text to clean
    Returns:
        str: Cleaned text with at most two consecutive empty lines, or None if processing fails
    """
    try:
        # Normalize all line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Replace lines containing only whitespace with a true empty line
        text = re.sub(r'^[ \t]+$', '', text, flags=re.MULTILINE)

        # Replace 3 or more consecutive newlines with exactly 2 newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Strip empty lines at start and end
        text = text.strip('\n')

        cleaned_text = text
    except Exception:
        cleaned_text = None

    return cleaned_text


# Initialize NLTK stopwords
try:
    stopwords.words("english")  # Check if stopwords are already downloaded
except LookupError:
    nltk.download("stopwords")  # Download stopwords if not available

def remove_stopwords(text, language):
    """
    Removes common words (stopwords) from the given text based on specified language.
    Args:
        text (str): Input text, can be in format "[word1, word2, word3]" or space-separated
        language (str): Two-letter language code (e.g., 'en', 'nl', 'de')
    Returns:
        str: Text with stopwords removed
    """
    # Map of language codes to NLTK language names
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

    # Filter out stopwords and return the cleaned string
    cleaned_words = [
        word.strip() for word in words if word.strip().lower() not in stopwords_set
    ]

    return " ".join(cleaned_words)

def remove_numbers(text):
    """
    Removes standalone numbers from text.
    Args:
        text (str): Input text
    Returns:
        str: Text with standalone numbers removed
    """
    return re.sub(r" \d+ ", " ", text)