#!/usr/bin/env python3
"""
app.py — flask entrypoint for arxiv digest
compatible with flask cli and vercel/wsgi deploy.
"""
import os, sys, traceback
from pathlib import Path

# ----------------------------------------------------------
# ensure consistent import path (avoids duplicate module loading)
# ----------------------------------------------------------
pkg_root = Path(__file__).resolve().parent.parent
if str(pkg_root) not in sys.path:
    sys.path.insert(0, str(pkg_root))

print("app.py loaded", file=sys.stderr)
print("ENV VARS LOADED:", list(os.environ.keys()), file=sys.stderr)

# ----------------------------------------------------------
# application factory import + error guard
# ----------------------------------------------------------
try:
    # use the absolute import - not relative
    from webapp import create_app

    app = create_app()
    application = app  # for vercel / wsgi compatibility

    # ==========================================================
    # DEBUG: print all registered SQLAlchemy model classes (2.x API)
    # ==========================================================
    from shared.db import db

    print("\n=== SQLAlchemy registered model classes ===", file=sys.stderr)
    try:
        for mapper in db.Model.registry.mappers:
            cls = mapper.class_
            print(f"{cls.__name__:25s} -> {cls.__module__}", file=sys.stderr)
    except Exception as e:
        print("debug registry print failed:", e, file=sys.stderr)
    print("===========================================\n", file=sys.stderr)

except Exception:
    print("=== SERVERLESS STARTUP CRASH ===", file=sys.stderr)
    traceback.print_exc()
    raise
