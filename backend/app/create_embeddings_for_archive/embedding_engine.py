def chunk_text(text: str, chunk_size: int) -> list[str]:
    """Splitst tekst op in aaneensluitende, niet-overlappende chunks van `chunk_size` woorden.

    Chunking gebeurt op woorden (whitespace-gescheiden), niet op echte tokens van het
    embeddingmodel — een exacte tokenizer is een externe dependency en zou deze functie
    niet meer puur maken. Woorden zijn een lichte, dependency-vrije benadering.

    Als de laatste chunk minder dan de helft van chunk_size woorden bevat, wordt hij
    samengevoegd met de voorlaatste chunk — een piepklein staartje (bv. 1 woord) krijgt
    zo geen eigen, weinig betekenisvolle embedding. Bij precies 1 chunk in totaal wordt
    nooit samengevoegd (er is geen voorlaatste chunk om mee te mergen).
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    words = text.split()
    word_chunks = [
        words[i:i + chunk_size]
        for i in range(0, len(words), chunk_size)
    ]  # dit groepeert telkens chunk_size woorden => 1 chunk

    if len(word_chunks) > 1 and len(word_chunks[-1]) < chunk_size / 2:
        laatste_chunk = word_chunks.pop()
        word_chunks[-1] = word_chunks[-1] + laatste_chunk

    return [" ".join(chunk) for chunk in word_chunks]
