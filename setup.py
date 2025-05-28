"""Setup script for the GoldMirror package."""

from setuptools import setup, find_packages

# Read README with explicit UTF-8 encoding
with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="goldmirror",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "python-dotenv",
        "structlog",
        "sqlalchemy>=2.0.0",
        "asyncpg>=0.29.0",  # PostgreSQL async driver
        "telethon",
        "lark-parser",
        "pyyaml",
        "aiohttp",
        "asyncio",
    ],
    python_requires=">=3.8",
    author="GoldMirror Team",
    description="Telegram to MT5 trading signal automation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Financial and Insurance Industry",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
) 