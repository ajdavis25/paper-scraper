import os

IGNORE = {"venv", "__pycache__", ".git", ".idea", ".vscode"}

def print_tree(path=".", prefix=""):
    entries = [e for e in os.listdir(path) if e not in IGNORE]
    entries.sort()
    for i, name in enumerate(entries):
        full = os.path.join(path, name)
        connector = "└── " if i == len(entries) - 1 else "├── "
        print(prefix + connector + name)
        if os.path.isdir(full):
            extension = "    " if i == len(entries) - 1 else "│   "
            print_tree(full, prefix + extension)

print("astroph-bot/")
print_tree(".")
