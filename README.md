# GoldMirror: Telegram to MT5 Signal Automation

Automate your trading by connecting Telegram signals directly to MetaTrader 5 with smart risk management and analytics.

## 🚀 Features

- **Automated Signal Processing**: Parse and validate trading signals from Telegram channels
- **Smart Risk Management**: Configurable risk per trade, breakeven logic, and position sizing
- **MT5 Integration**: Direct execution of trades via MetaTrader 5 Python API
- **Analytics Dashboard**: Track performance, missed trades, and risk metrics
- **Prop Firm Ready**: Built-in compliance with prop firm trading rules

## 📋 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/goldmirror.git
   cd goldmirror
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Copy the example environment file and configure it:
   ```bash
   cp .env.example .env
   ```

## ⚙️ Configuration

1. Set up your Telegram API credentials:
   - Get your API ID and hash from https://my.telegram.org
   - Add them to `.env`

2. Configure MT5 connection:
   - Ensure MetaTrader 5 is installed
   - Add your MT5 credentials to `.env`

3. Adjust trading parameters in `config/config.yaml`:
   - Risk per trade
   - Position sizing
   - Trading hours
   - News filter settings

## 🔧 Usage

1. Start the signal listener:
   ```bash
   python src/main.py
   ```

2. Monitor trades through:
   - Console logs
   - Analytics dashboard (optional)
   - Telegram bot notifications

## 🔒 Security

- Never commit `.env` or `config/secrets.yaml`
- Use environment variables for sensitive data
- Regularly rotate API keys and credentials
- Monitor for unauthorized access

## 🛠️ Development

### Project Structure
```
goldmirror/
├── src/
│   ├── telegram/    # Signal parsing and validation
│   ├── mt5/         # MT5 trading engine
│   ├── risk/        # Risk management logic
│   └── analytics/   # Performance tracking
├── tests/           # Test suite
├── config/          # Configuration files
└── logs/            # Application logs
```

### Running Tests
```bash
pytest --cov=src tests/
```

### Code Style
- Format with Black: `black .`
- Type checking: `mypy src/`
- Linting: `pylint src/`

## 📝 License

MIT License - see LICENSE file for details

## ⚠️ Disclaimer

This software is for educational purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred through the use of this software. 