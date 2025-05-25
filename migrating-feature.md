# Feature Request: Migrate Signal Parsing from Regex to Lark

## 📌 Title
Migrate Telegram Signal Parsing from Regex to Lark Parser for Robustness and Maintainability

## 🧩 Background
The current signal parsing system uses regex to extract trading signals from Telegram messages. While fast to implement, regex has proven brittle for:
- Handling message edits or partial signals (e.g., SL comes first, TP later)
- Supporting slight variations in wording or formatting (e.g., `TP1`, `Tp2`, `TakeProfit3`)
- Ensuring safe parsing of real-money trades in edge cases

To improve long-term robustness and flexibility, we will migrate the parser to use the [Lark parsing library](https://github.com/lark-parser/lark).

## ✅ Goal
Replace existing regex-based signal parser with a Lark-based parser and transformer that produces structured trade data for the trade execution engine.

## 🧪 Example Inputs
### Sample 1
"""
XAUUSD buy now 
Enter 3232
SL 3220
TP1 3235
TP2 3239
TP3 3255
TP4 3333.50 (1000)

Again it’s still risky so I’m trying once again 

Max 0.25%
"""

### Sample 2
"""
XAUUSD Buy now 
Enter 3187
SL 3176 (100pips) 
TP1 3190
TP2 3195
TP3 3200
TP4 3205
"""

### Sample 3
"""
XAUUSD buy now
Enter 3173
SL 3163 (100)
TP1 3177
Tp2 3180
Tp3 3190
TP4 3373 (2000)

Max 0.25% risk
Don’t let one trade ruin weeks of profits

TP5 3477
"""

## 📘 Proposed Solution
1. **Add Lark grammar file** (`signal.lark`) to define expected token structure:
   ```ebnf
   signal: symbol direction? entry? sl? tp+ risk_note? COMMENT*
   symbol: /[A-Z]{3,6}/
   direction: "buy"i | "sell"i
   entry: ("Enter"i | "Entry"i) NUMBER
   sl: "SL"i NUMBER /\(\d+(pips)?\)/?
   tp: /TP\d?/i NUMBER /\(\d+(pips)?\)/?
   risk_note: /Max .*?%/
   COMMENT: /.+/
   ```

2. **Create transformer class** to convert parse tree into a structured dict:
   ```python
   {
     "symbol": "XAUUSD",
     "direction": "buy",
     "entry": 3173.0,
     "sl": 3163.0,
     "tp": [3177.0, 3180.0, 3190.0, 3373.0, 3477.0],
     "risk": "Max 0.25%"
   }
   ```

3. **Replace current regex parsing module** with a Lark-based parser + transformer call
   - If parse fails, fallback to regex or flag as `low_confidence`

4. **Write unit tests** to ensure all current signal formats are correctly parsed

## ✅ Deliverables
- `signal.lark` grammar file
- `SignalTransformer` class
- Refactored `SignalParser` module using Lark
- Unit tests covering >10 realistic signal formats

## 📈 Benefits
- Easier to maintain as message format evolves
- Supports partial message handling more gracefully
- More reliable for high-stakes signal parsing in automation
- Ready for multilingual expansion or DSL support in future

---
Please coordinate with the existing `SignalQueue` and `SignalValidator` to ensure output structure is consistent. Fallback mode for regex will be removed after the Lark module passes all tests.

Assignee: NLP / Parsing Team
Priority: HIGH (Blocking Master Trade Consistency)
Tags: `parsing`, `telethon`, `lark`, `migration`, `accuracy`
