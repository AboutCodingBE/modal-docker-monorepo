def chunk_text(text: str, chunk_size: int) -> list[str]:
    """Splitst tekst op in aaneensluitende, niet-overlappende chunks van `chunk_size` woorden.

    Chunking gebeurt op woorden (whitespace-gescheiden), niet op echte tokens van het
    embeddingmodel — een exacte tokenizer is een externe dependency en zou deze functie
    niet meer puur maken. Woorden zijn een lichte, dependency-vrije benadering.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    words = text.split()
    return [
        " ".join(words[i:i + chunk_size])
        for i in range(0, len(words), chunk_size)
    ]
