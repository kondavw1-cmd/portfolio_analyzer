portfolio_analyzer/
├── config/
│   ├── __init__.py
│   └── settings.py          # Global constants, sector index mappings, and configurations
├── data/
│   └── tradebook-DIZ015-EQ.csv # Place your Zerodha tradebook CSV here
├── src/
│   ├── __init__.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── nifty_fetcher.py # Nifty 750 universe dynamic fetching & fallback logic
│   │   └── market_data.py   # yfinance historical data downloads & chunking engine
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── metrics.py       # Risk/return metrics, alpha, beta, Sharpe, and ATH calculations
│   │   └── scoring.py       # Grading matrices, review scoring, and action assignment
│   ├── trading/
│   │   ├── __init__.py
│   │   ├── charges.py       # Zerodha brokerage, taxes, and regulatory charges calculator
│   │   └── tradebook.py     # FIFO trade matching, closed, and open/partial journal processors
│   └── utils/
│       ├── __init__.py
│       └── helpers.py       # Corporate calendar parsing, market cap tiering, and date formatters
├── main.py                  # Master orchestration script
├── requirements.txt         # Project dependencies
└── README.md                # Documentation