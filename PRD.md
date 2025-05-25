**Product Requirements Document (PRD)**

**Project Title:** Telegram to MT5 Auto-Trading Bot with Master-Slave Architecture (Codename: GoldMirror)

**Prepared by:** Dapo Ajuwon
**Last Updated:** 2025-05-24

---

### 1. Objective

Build an intelligent automated trading system that:

* Parses scalp signals from a Telegram channel.
* Places trades on a MetaTrader 5 (MT5) terminal (Master).
* Replicates these trades on multiple Slave terminals.
* Supports dynamic trade management including SL-to-BE and multi-TP handling.
* Can evolve into a SaaS with modular design and risk protections.

---

### 2. Scope

* Telegram signal parsing (including partial signals and message edits)
* Confidence scoring to filter valid trades
* Trade execution via MT5 Python API on Master terminal
* Publishing of structured trade events by Master
* Slave terminals replicate all Master trades and updates in real-time
* Trade tracking (open, modify SL, close)
* SL-to-BE automation after TP1 is hit
* Daily loss protection, cooldown logic, and max trade filters

---

### 3. System Architecture

**Components:**

1. **Telegram Listener (Telethon)**

   * Parses new and edited messages
   * Applies regex-based and semantic filtering
   * Implements Lark grammar for structured signal parsing
   * Supports confidence scoring for signal validation

2. **Signal Classifier**

   * Assigns confidence score to each message
   * Filters swing trades, ambiguous alerts, etc.
   * Implements NLP fallback for unstructured messages
   * Validates price relationships and risk management notes

3. **Trade Manager (Master)**

   * Executes trades via MT5 Python API
   * Splits trade into 4/5 legs (TP1 to TP4/5)
   * Risk: 0.25% per trade
   * Publishes trade events to Redis or lightweight queue
   * Applies cooldown and daily SL cutoff logic
   * Supports simulation mode for testing
   * Implements position tracking and modification history

4. **Trade Event Bus**

   * Redis Pub/Sub or alternative
   * Carries `new_trade`, `modify_sl`, `close_trade`, `pause` events
   * Supports trade ID matching and update syncs

5. **Slave Executor**

   * Subscribes to Redis
   * Mirrors trades on own MT5 terminal
   * Optional: scale volumes (1:1, 0.5x, etc.)
   * Supports trade ID matching and update syncs

6. **Trade Tracker**

   * Monitors TP1 hits on Master
   * Triggers SL-to-BE for remaining positions
   * Communicates SL/TP updates downstream
   * Tracks position modifications and partial closes
   * Maintains daily trading statistics

7. **Notification Bot**

   * Alerts user via Telegram on trade actions and errors
   * Optionally accepts control commands (pause/resume/status)
   * Provides rich formatted trade updates

8. **Risk & Compliance Engine**

   * Avoids entries during news events (FOMC, NFP)
   * Limits trading after 2 consecutive SLs
   * Enforces max daily loss
   * Implements economic calendar integration
   * Supports configurable news impact filtering
   * Provides pre/post news trading buffers
   * Tracks daily statistics including drawdown

9. **Database Layer**
   * PostgreSQL for persistent storage
   * Implements data models for:
     - Trading signals and their states
     - Trade executions and modifications
     - Position tracking and history
     - Daily statistics and performance metrics
     - Risk management parameters
     - News events and impact tracking
   * Provides data integrity and consistency
   * Enables historical analysis and reporting
   * Supports audit trail for compliance

---

### 4. Features

#### 4.1 Signal Processing

* Parse and merge partial messages (e.g., SL comes first)
* Handle message edits (e.g., TP levels updated later)
* Store temporary cache of incomplete signals per symbol
* Implement Lark grammar for structured signal parsing
* Support confidence scoring based on signal components
* Validate price relationships and risk management notes

#### 4.2 Trade Execution

* Execute up to 4 micro-trades per signal
* Each micro-trade targets TP1–TP4 respectively
* Lot size based on 0.25% total risk allocation
* Support simulation mode for testing
* Track position modifications and partial closes
* Maintain detailed trade history

#### 4.3 Master-Slave Replication

* Master publishes structured trade events
* Slaves subscribe and mirror trades with minimal latency
* All trade actions (open, SL modification, close) synced
* Support for trade ID matching and update synchronization

#### 4.4 Trade Management

* Detect TP1 hit based on live price feed
* Automatically move SL of TP2–TP4 trades to break-even
* Track position modifications and partial closes
* Maintain daily trading statistics
* Support rich formatted trade updates

#### 4.5 Hosting & Infrastructure

* Initially hosted on Windows VPS
* MT5 terminal + Python scripts run on same server
* Slave bots run on their own VPS or local environments
* Redis server for internal messaging

#### 4.6 SaaS Potential

* Multi-user modular design
* Optional local MT5 bridge for user-run setups
* Subscription-ready with scalable trade routing

#### 4.7 Risk Management

* Implement economic calendar integration
* Support configurable news impact filtering
* Provide pre/post news trading buffers
* Track daily statistics including drawdown
* Enforce cooldown periods after losses
* Monitor account balance and position exposure

#### 4.8 Database Persistence

* **Signal Storage**
  * Store all incoming signals with metadata
  * Track signal processing states (pending, validated, executed, rejected)
  * Maintain signal modification history
  * Prevent duplicate signal processing
  * Enable signal replay for testing

* **Trade History**
  * Record all trade executions with full details
  * Track position modifications (SL/TP updates)
  * Store partial close information
  * Maintain trade lifecycle events
  * Support trade reconciliation

* **Performance Tracking**
  * Store daily trading statistics
  * Track win/loss ratios and profit metrics
  * Record drawdown periods
  * Maintain risk exposure history
  * Enable performance analytics

* **Risk Management**
  * Store risk parameters and limits
  * Track daily loss limits and usage
  * Record cooldown periods
  * Maintain news impact history
  * Store market hours exceptions

* **Audit and Compliance**
  * Maintain complete audit trail
  * Track system state changes
  * Record user actions and commands
  * Store error and exception logs
  * Enable compliance reporting

---

### 5. Non-Goals (Phase 1)

* Broker API-only integration (non-MT5)
* Trade trailing or scaling-in strategies
* Complex UI/dashboard (CLI and Telegram bot only)
* Analytics/visual reporting modules
* Complex database migrations or versioning
* Real-time analytics on historical data
* Multi-database support
* Database clustering or replication

---

### 6. Future Roadmap (Post-MVP)

* Web dashboard for trade visibility and analytics
* Multi-timeframe signal support
* Broker diversification (API-based brokers)
* Per-user config for risk and strategy
* SaaS interface with user roles, billing, and stats
* Advanced database features:
  * Data archival and cleanup
  * Automated backup and restore
  * Database performance optimization
  * Real-time analytics integration
  * Multi-region data replication

---

### 7. Risks and Mitigations

| Risk                            | Mitigation                                 |
| ------------------------------- | ------------------------------------------ |
| Telegram message format changes | Use flexible Lark grammar + NLP fallback   |
| MT5 session disconnects         | Add reconnect logic + error alerts         |
| Latency in slave execution      | Use Redis pub/sub and heartbeat monitoring |
| Overload on Redis               | Implement lightweight event schema         |
| Signal volume spikes            | Add signal queue and rate control          |
| News event impact               | Economic calendar integration + buffers    |
| Position tracking errors        | Implement modification history tracking    |
| Simulation vs Live confusion    | Clear mode separation + validation         |
| Database connection loss        | Implement connection pooling + retry logic |
| Data inconsistency             | Use transactions + validation checks       |
| Storage growth                 | Implement data archival + cleanup          |
| Query performance              | Add indexes + query optimization           |
| Data corruption                | Regular backups + integrity checks         |

---

### 8. Acceptance Criteria

* Bot filters and places trades only on valid scalp signals
* Slave accounts mirror trades within 2s latency
* SL is automatically moved to breakeven after TP1
* Trade events are logged with traceable IDs
* Telegram bot reports success/failure of each trade
* Risk limits and cooldown logic enforced per session
* Database successfully stores and retrieves all critical trading data
* No duplicate trades are executed due to signal replay
* Historical data is available for analysis and reporting
* System can recover from database failures
* Audit trail provides complete trading history
* Performance metrics are accurately tracked and stored

### 9. Database Schema Overview

#### Core Tables

1. **Signals**
   * Unique signal ID
   * Telegram message details
   * Parsed signal components
   * Processing state
   * Validation results
   * Timestamps (received, processed, executed)

2. **Trades**
   * Trade ID (linked to signal)
   * Execution details
   * Position information
   * Risk parameters
   * Status tracking
   * Modification history

3. **Positions**
   * Position ID
   * Trade references
   * Current state
   * Modification history
   * Partial close records
   * Performance metrics

4. **Daily Statistics**
   * Date
   * Trading metrics
   * Risk exposure
   * Performance indicators
   * System health data

5. **Risk Management**
   * Risk parameters
   * Limit tracking
   * Cooldown periods
   * News impact records
   * Market hours data

6. **Audit Log**
   * Event ID
   * Event type
   * Timestamp
   * User/System action
   * State changes
   * Error records

#### Key Relationships
* Signals -> Trades (1:many)
* Trades -> Positions (1:many)
* Positions -> Modifications (1:many)
* Daily Stats -> Trades (1:many)
* Risk Management -> Trades (1:many)

#### Indexes and Performance
* Primary keys on all tables
* Foreign key constraints
* Indexes on frequently queried fields
* Composite indexes for common queries
* Partitioning for large tables

#### Data Retention
* Trading data: 1 year
* Audit logs: 2 years
* Performance metrics: 5 years
* Archived data: 10 years

---

**End of Document**
