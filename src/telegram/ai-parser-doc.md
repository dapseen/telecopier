Here’s a clear and technical **Feature Request Document (FRD)** for replacing Lark/regex with GPT-3-based AI parsing in your Telegram signal automation system:

---

### 🧩 Feature Request: AI-Based Telegram Signal Parsing Using GPT-3

**Feature Name:**
Replace Lark/Regex Signal Parser with GPT-3 Language Model Integration

**Requested By:**
Adedapo Ajuwon

**Date:**
May 26, 2025

---

### 🎯 Objective

Refactor the existing Telegram signal parsing logic to use **GPT-3.5 Turbo** for interpreting and extracting structured data from trading signal messages. This will **replace the current rule-based approach (Lark or regex)** with a more flexible and robust AI-powered parser.

---

### 🔍 Background

The current signal parsing system uses either Lark grammars or regex patterns to extract trading instructions (e.g., symbol, direction, entry price, SL, TP1–TP4) from Telegram messages. This works only when signals follow a consistent structure.

However, actual signals may include:

* Varying word orders and typos
* Partial updates or edits (e.g., SL-only or TP follow-ups)
* Natural language (e.g., “Buy gold at 3334, SL below 3324, targets 3340–3360”)

As a result, rule-based parsing becomes brittle and hard to scale.

---

### ✅ Goals

* Replace all Lark and regex parsing logic with a **single GPT-3-based parsing engine**
* Parse raw Telegram messages into structured JSON with the following fields:

  ```json
  {
    "symbol": "XAUUSD",
    "direction": "Buy",
    "entry": 3334.0,
    "sl": 3324.0,
    "take_profits": {
      "TP1": 3339.0,
      "TP2": 3345.0,
      "TP3": 3350.0,
      "TP4": 3355.0
    }
  }
  ```
* Ensure resilience to:

  * Typographical variations
  * Incomplete signals (e.g., SL-only or TP3–TP4 later)
  * Natural language inputs

---

### 🛠️ Functional Requirements

1. **Prompt Design**

   * Craft a structured prompt that instructs GPT-3 to extract all relevant trade fields into JSON.
   * Include error-handling instructions for missing or malformed fields.

2. **API Integration**

   * Use OpenAI’s GPT-3.5 API with `gpt-3.5-turbo` model
   * Support environment-based API key configuration

3. **Parser Wrapper**

   * Build a module/class that accepts a raw message and returns parsed JSON
   * Add fallback for invalid outputs or retry with slight prompt variation

4. **Validation**

   * Use Pydantic or schema validator to ensure output conforms to expected structure
   * Mark invalid or incomplete responses for retry/logging


---

### 🔒 Non-Functional Requirements

* Latency per request should not exceed 1 second
* Handle 100+ signals/day without hitting rate limits (consider batching later)
* Secure API key with proper .env management

---

### 📦 Deliverables

* `ai_parser.py` or `signal_parser/ai_gpt_parser.py`
* Prompt stored in codebase for version control
* Integration into existing message processing pipeline

---

### 📈 Benefits

* Future-proof and format-agnostic parsing
* Easier to scale across multiple Telegram channels
* Reduced maintenance vs hardcoded grammar rules
* Can evolve into a paid SaaS feature

---
