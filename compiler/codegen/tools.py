
__valid_chars = "abcdefghijklmnoprstuvwxyzABCDEFGHIJKLMNOPRSTUVWXYZ0123456789_"
def mangle_name(symbol: str) -> str:
    return ''.join(c if c in __valid_chars else f"Q{ord(c)}q" for c in symbol).replace('Q58qQ58q', 'Q__q')

