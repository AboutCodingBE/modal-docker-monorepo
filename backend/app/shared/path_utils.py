def normalize_path(path: str) -> str:
    """Converteert OS-specifieke padseparators naar POSIX-stijl (/) voor
    consistente opslag en vergelijking, ongeacht bron-OS."""
    return path.replace("\\", "/")
