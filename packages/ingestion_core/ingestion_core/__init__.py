"""Shared email-ingestion core: adapter interface, concrete parsers, sender verification.

Pure Python with no database or AWS dependencies, so the API (admin reprocess) and the
ingestion Lambda can both import it and always run the same parser code.
"""
