from setuptools import setup, find_packages

# Read README with explicit UTF-8 encoding
with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="goldmirror",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "python-dotenv>=1.0.0",
        "structlog>=23.1.0",
        "pyyaml>=6.0.1",
        "pydantic>=2.5.2",
        "telethon>=1.34.0",
        "MetaTrader5>=5.0.49; platform_system == 'Windows' or (platform_system == 'Darwin' and platform_machine == 'x86_64')",
        "pandas>=2.1.3",
        "numpy>=1.26.2",
        "rich>=13.7.0",
    ],
    python_requires=">=3.9",
    author="We3rdbot",
    description="Telegram to MT5 Signal Automation",
    long_description=long_description,
    long_description_content_type="text/markdown",
) 