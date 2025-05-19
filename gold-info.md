To understand **position size calculation for XAU/USD (Gold/USD pair)**, let’s break it down step by step — specifically tailored to how Gold works differently than standard forex pairs.

---

### 🟨 1. **What is Position Size?**

Position size is the number of **units (lots)** you trade based on:

* Account balance
* Risk tolerance (usually a % of your account)
* Stop loss size (in pips or points)
* Value per pip/point for the instrument

---

### 🟨 2. **Key Facts for XAU/USD (Gold)**

| Parameter        | Value                                                                            |
| ---------------- | -------------------------------------------------------------------------------- |
| **Symbol**       | XAU/USD                                                                          |
| **Standard lot** | 100 oz (ounces)                                                                  |
| **1 pip**        | 0.01 (Gold usually quoted to 2 decimal places, e.g., 1975.50 → 1975.51 is 1 pip) |
| **Pip value**    | \$1 per pip per lot                                                              |

---

### 🟨 3. **Position Size Formula (General)**

$$
\text{Position Size} = \frac{\text{Account Risk}}{\text{Stop Loss in pips} \times \text{Pip Value per lot}}
$$

But with XAU/USD, since **1 lot = 100 oz**, the pip value becomes:

$$
\text{Pip Value} = 1 \text{ USD per pip per standard lot}
$$

So the formula becomes:

$$
\text{Lot Size} = \frac{\text{Account Balance} \times \text{Risk %}}{\text{Stop Loss (in pips)} \times 1}
$$

---

### 🟨 4. **Example Calculation**

#### ✅ Inputs:

* **Account balance** = \$10,000
* **Risk per trade** = 2% → \$200
* **Stop loss** = 50 pips (i.e., \$5 move in price because 1 pip = 0.01)

#### ✅ Formula:

$$
\text{Lot Size} = \frac{200}{50} = 4 \text{ lots}
$$

> So, you can trade **4 standard lots of Gold (XAU/USD)** with a \$5 stop loss if you're risking \$200.

---

### 🟨 5. **Scaling to Mini/Micro Lots**

If you want to trade mini or micro lots:

| Lot Type     | Size   | Pip Value |
| ------------ | ------ | --------- |
| Standard lot | 100 oz | \$1.00    |
| Mini lot     | 10 oz  | \$0.10    |
| Micro lot    | 1 oz   | \$0.01    |

So, if you want to risk \$200 with a 50-pip SL using mini lots:

$$
\text{Lot Size} = \frac{200}{50 \times 0.10} = 40 \text{ mini lots} = 4 standard lots
$$

---

### 🟨 6. **Key Differences for Gold vs Forex**

| Factor         | XAU/USD                 | EUR/USD (Forex)          |
| -------------- | ----------------------- | ------------------------ |
| Lot size       | 100 oz                  | 100,000 units            |
| Pip definition | \$0.01 (1 pip)          | 0.0001 (1 pip)           |
| Pip value      | \$1 per lot per pip     | Varies based on pair     |
| Volatility     | Typically more volatile | Relatively less volatile |

---

### 🟩 Summary

To calculate position size for **XAU/USD**:

1. Decide your account risk (e.g., 2% of balance)
2. Determine your stop loss (in pips, where 1 pip = \$0.01)
3. Use:

   $$
   \text{Lot Size} = \frac{\text{Risk}}{\text{Stop Loss in pips}}
   $$


Here’s a technical reference document you can pass to **Cursor** to help it understand the basics of trading **XAU/USD (Gold)** on **MetaTrader 5**, using data and conventions from the official MT5 documentation and broker standards like Vantage.

---

## 📄 MT5 Trading Basics: XAU/USD (Gold) — Technical Reference for Cursor

### 📍 Instrument Overview

* **Symbol**: `XAUUSD`
* **Asset**: Gold vs US Dollar
* **Market Type**: Spot Commodity (CFD)
* **Execution Type**: Market Order / Pending Order
* **Trading Platform**: MetaTrader 5 (MT5)

---

### ✅ Minimum & Incremental Trade Volume

| Parameter            | Value            |
| -------------------- | ---------------- |
| **Minimum lot size** | `0.01` lots      |
| **Lot increment**    | `0.01`           |
| **Maximum lot size** | Broker-dependent |

> **Note**: 1 lot = 100 ounces of gold. So 0.01 lot = 1 ounce.

---

### 📉 Common Order Types in MT5

| `type` (int) | Order Type        | Direction | Description                         |
| ------------ | ----------------- | --------- | ----------------------------------- |
| `0`          | `ORDER_TYPE_BUY`  | Buy       | Open long position at market price  |
| `1`          | `ORDER_TYPE_SELL` | Sell      | Open short position at market price |
| `2`–`6`      | Pending orders    | Varies    | Buy Limit, Sell Limit, Stop types   |

Cursor should **use integer enums** as defined in MT5’s Python API when sending orders.

---

### ⚙️ Order Execution Fields

To send a market order in MT5 for XAU/USD, Cursor should fill at least the following fields:

```python
order = {
    'action': mt5.TRADE_ACTION_DEAL,
    'symbol': 'XAUUSD',
    'volume': 0.01,  # Min lot size
    'type': mt5.ORDER_TYPE_BUY or mt5.ORDER_TYPE_SELL,
    'price': mt5.symbol_info_tick('XAUUSD').ask or .bid,
    'sl': None or price,  # Can be added later
    'tp': None or price,
    'deviation': 20,
    'magic': 123456,
    'comment': "AutoTrade",
    'type_time': mt5.ORDER_TIME_GTC,
    'type_filling': mt5.ORDER_FILLING_IOC
}
```

> SL/TP can be omitted at execution and modified **after** order is placed using `order_modify()`.

---

### 📦 Important MT5 Trading Rules for XAU/USD

1. **Price Precision**: Typically 2 decimal places (e.g., `3229.75`)
2. **Spread**: Can vary significantly (e.g., 10–30 points depending on volatility)
3. **Leverage**: Often 1:100 or 1:500 for Gold — beware of risk amplification
4. **Swap Fees**: Overnight positions may incur swap fees (long vs short)
5. **Volatility**: Gold is a fast-moving instrument — set SL/TP appropriately
6. **Trading Hours**:

   * Opens: Sunday 23:00 GMT
   * Closes: Friday 22:00 GMT
   * Closed on major U.S. holidays

---

### 🔁 Modifying Trades After Execution

If SL/TP are not included in the initial order:

* Wait 0.5–1s
* Use `order_get()` or `positions_get()` to get the `ticket`
* Then use `order_modify()` to apply SL/TP

> Cursor should confirm that the position is open before applying modifications.

---

### 🧪 Example: Buying 0.10 Lots of Gold

```python
{
    'symbol': 'XAUUSD',
    'type': 0,
    'volume': 0.10,
    'price': 3228.50,
    'sl': None,
    'tp': None
}
```

---

### 📊 Useful MT5 Python API Calls for Cursor

* `mt5.initialize()` — connect to terminal
* `mt5.order_send(order_dict)` — send order
* `mt5.positions_get(symbol='XAUUSD')` — get open positions
* `mt5.order_check()` — pre-validate order
* `mt5.symbol_info_tick('XAUUSD')` — get current price
* `mt5.order_modify()` — update SL/TP after execution

---

### ✅ Summary Checklist for Cursor

| Step | Description                                                    |
| ---- | -------------------------------------------------------------- |
| ✅    | Use `0.01` as the minimum lot for XAU/USD                      |
| ✅    | Use `ORDER_TYPE_BUY` or `ORDER_TYPE_SELL` (0 or 1)             |
| ✅    | Send order **without SL/TP** if errors occur, and modify after |
| ✅    | Confirm position is open before modification                   |
| ✅    | Avoid hardcoding price — always pull latest tick data          |
| ✅    | Wrap all logic in try/except and log errors clearly            |

---

Let me know if you want this exported as a `.md` file or added to a shared repo structure.

