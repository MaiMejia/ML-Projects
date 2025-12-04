
# --- SYSTEM AND EMAIL LIBRARIES ---
import os
import sys
import time
import warnings
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Tuple, Optional

# --- CORE LIBRARIES ---
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# --- TRADING/TA LIBRARIES ---
import yfinance as yf
import pandas_ta
import requests # For Telegram alerts and general API calls

# --- GOOGLE SHEETS LIBRARIES (Updated for AWS) ---
import gspread
from gspread import service_account
import json

warnings.filterwarnings('ignore') # Suppress Pandas/library warnings


# ==============================================================================
# 1. CONFIGURATION & CREDENTIALS (READ FROM ENVIRONMENT VARIABLES)
# ==============================================================================
# IMPORTANT: These environment variables must be set on your AWS server!
# Set the GMAIL and TELEGRAM credentials later for reporting/alerts.

# Local Data Configuration
CSV_FILE_PATH = 'btc_final_merged_data.csv' 
WORKSHEET_NAME = 'Sheet1'                         # <<< UPDATE THIS: The specific tab/worksheet name

# Bot Execution Parameters
##CHECK_INTERVAL_SECONDS = 60 * 5  # Check the market and GSheet data every 5 minutes
CHECK_INTERVAL_SECONDS = 60 * 60 * 24  # Check the market and GSheet data every 24 hours

# --- NEW: PERSISTENCE FILE PATHS ---
PORTFOLIO_STATE_FILE = 'portfolio_state.json'
TRADE_LOG_FILE = 'weekly_trade_log.csv'

# --- EMAIL CONFIGURATION (Read from Environment Variables) ---
EMAIL_SENDER = os.environ.get("GMAIL_USER")
EMAIL_PASSWORD = os.environ.get("GMAIL_PASS")
EMAIL_RECIPIENT = "@gmail.com"                       # <<< UPDATE THIS TO YOUR EMAIL
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587 # Standard port for STARTTLS (encrypted connection)

# ==============================================================================
# 2. DATA ACQUISITION FUNCTION (Local CSV)
# ==============================================================================
def get_gsheet_data() -> pd.DataFrame:
    """Reads data from a local CSV file stored on the AWS server."""
    global CSV_FILE_PATH

    try:
        # Use a standard Pandas read_csv call for local file access
        df = pd.read_csv(CSV_FILE_PATH)

        # REQUIRED: Convert your Date/Time column to actual datetime objects and set index
        # NOTE: If your column is named 'timestamp' or 'date', update 'Date' below
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Data loaded from local CSV. Rows: {len(df)}")
        return df

    except FileNotFoundError:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ FATAL Error: Local CSV file '{CSV_FILE_PATH}' not found. Waiting...")
        return pd.DataFrame()
    except Exception as e:
        # If the file is found but structured wrong
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ FATAL Error reading CSV data: {e}")
        return pd.DataFrame()

## -------------------------------------------------------- ##
# ------------- CONFIGURATION   -------
## -------------------------------------------------------- ##
TICKER = 'BTC-USD'
HISTORY_START_DATE = '2023-01-01' # Fetch the last 2 years of data
HISTORY_INTERVAL = '1d'

# Financial Parameters
STARTING_BUDGET = 100000.0 # Configurable initial budget
COMMISSION_RATE = 0.002
RISK_FREE_RATE_ANNUAL = 0.04
DCA_AMOUNT_DAILY = 100.0   # Base daily accumulation amount
ATR_MULTIPLIER = 3.0       # Stop-loss risk factor for tactical trades

# Strategy Parameters (TA-Based Rules)
RSI_OVERSOLD_THRESHOLD = 30 # Threshold for potential "Value/Range" accumulation
RSI_OVERBOUGHT_THRESHOLD = 70 # Threshold for potential "Swing" profit-taking
SWING_TRADE_ALLOCATION_MAX = 0.60 # Max percentage of budget for active trades


## ---------------------------------------------------------------- ##
# SIMPLIFIED RULE-BASED ADAPTIVE MULTIPLIER
# --- Focuses only on MACD Trend and FGI Extremes ---
## ---------------------------------------------------------------- ##

def get_rule_based_multiplier(current_data: pd.Series, combined_action: str) -> float:
    """
    Generates a simplified contextual risk multiplier (0.0 to 1.5) by checking
    if MACD trend and FGI extremes confirm the combined trading action.
    """

    rsi = current_data['RSI']
    macd_delta = current_data['MACD'] - current_data['MACD_Signal']
    fgi_score = current_data['FGI_Score']

    # Base Multiplier: Neutral starting point
    multiplier = 1.0

    # Check if the core action is a BUY/LONG
    is_long_action = 'BUY' in combined_action.upper() or 'LONG' in combined_action.upper()

    # If the strategy is FLAT, exit immediately
    if 'FLAT' in combined_action.upper() or 'HOLD' in combined_action.upper():
        return 1.0

    # --- 1. MACD Trend Confirmation (Adds/Subtracts 0.2) ---
    # The MACD delta should align with the trade direction.
    if (is_long_action and macd_delta > 0) or (not is_long_action and macd_delta < 0):
        # Trend Confirms Action
        multiplier += 0.2
    else:
        # Trend Contradicts Action (Trading against momentum is riskier)
        multiplier -= 0.2

    # --- 2. FGI Extreme Sentiment (Adds/Subtracts 0.3) ---
    # We look for contrarian signals (Fear for Buys, Greed for Sells)
    if fgi_score <= 30: # Extreme Fear (Contrarian Buy Signal)
        multiplier += (0.3 if is_long_action else -0.3)
    elif fgi_score >= 70: # Extreme Greed (Contrarian Sell Signal)
        multiplier += (-0.3 if is_long_action else 0.3)

    # --- 3. RSI Over-extension Filter (Adds/Subtracts 0.1) ---
    # Punish the trade if momentum is exhausted (RSI is too high for a Buy, too low for a Sell)
    if (is_long_action and rsi >= 75) or (not is_long_action and rsi <= 25):
        multiplier -= 0.1
    elif (is_long_action and rsi <= 30) or (not is_long_action and rsi >= 70):
        multiplier += 0.1 # Reward entering at oversold/overbought extremes

    # 4. Clamp the output to ensure it stays within the required range
    final_multiplier = max(0.0, min(1.5, multiplier))

    return final_multiplier

# Assign the rule-based function to the name expected by Block 4
get_final_multiplier = get_rule_based_multiplier


## -------------------------------------------------------------- ##
# -----    DATA PERSISTENCE UTILITIES (REQUIRED FOR WEEKLY REPORT) -----
## -------------------------------------------------------------- ##
def save_portfolio_state(portfolio: dict): 
    """Saves the current state of the portfolio to a JSON file."""
    global PORTFOLIO_STATE_FILE
    try:
        with open(PORTFOLIO_STATE_FILE, 'w') as f:
             # <--- UPDATE: Convert date objects to string before saving 
            if isinstance(portfolio.get('last_report_date'), datetime): 
                portfolio['last_report_date'] = portfolio['last_report_date'].strftime('%Y-%m-%d %H:%M:%S') 

            # <--- NEW: Convert processed date to string 
            if isinstance(portfolio.get('last_processed_date'), datetime): 
                portfolio['last_processed_date'] = portfolio['last_processed_date'].strftime('%Y-%m-%d %H:%M:%S')

            json.dump(portfolio, f, indent=4)
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ WARNING: Failed to save portfolio state: {e}")


def log_trade_event(date: datetime, action: str, trade_type: str, qty: float, price: float, fees: float):
    """Appends a new trade record to the trade log CSV."""
    global TRADE_LOG_FILE
    try:
        # Create a new record dictionary
        record = {
            'Date': date.strftime('%Y-%m-%d %H:%M:%S'),
            'Action': action,  # e.g., 'BUY' or 'SELL'
            'Trade_Type': trade_type,  # e.g., 'DCA', 'Swing', 'LLM'
            'Quantity': qty,
            'Price': price,
            'Fees': fees
        }
        
        # Determine if we need to write the header (check if file exists/is empty)
        file_exists = os.path.exists(TRADE_LOG_FILE) and os.path.getsize(TRADE_LOG_FILE) > 0
        
        # Convert record to a DataFrame for easy appending
        new_df = pd.DataFrame([record])
        
        # Append the data to the CSV
        new_df.to_csv(
            TRADE_LOG_FILE, 
            mode='a', 
            header=not file_exists, # Write header only if the file is new/does not exist
            index=False
        )
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ WARNING: Failed to log trade event: {e}")


## -------------------------------------------------------------- ##
# ----- Dynamic Trading Strategy: CORE EXECUTION FUNCTIONS (MODIFIES PORTFOLIO) -----
## -------------------------------------------------------------- ##


def execute_dca_buy(row, portfolio: dict) -> bool:
    """Executes a daily DCA buy and modifies the portfolio state."""
    global DCA_AMOUNT_DAILY, COMMISSION_RATE, RSI_OVERSOLD_THRESHOLD

    current_close = row['Close']
    dca_amount = DCA_AMOUNT_DAILY

    # Conditional DCA: Increase buy size during accumulation periods
    if row['RSI'] < RSI_OVERSOLD_THRESHOLD:
        dca_amount *= 1.5

    if portfolio['cash'] >= dca_amount:
        commission = dca_amount * COMMISSION_RATE
        buy_qty = (dca_amount - commission) / current_close

        # Update portfolio directly
        portfolio['cash'] -= dca_amount
        portfolio['btc_qty'] += buy_qty
       
       #  -- LOG TRADE --
        log_trade_event(row.name, 'BUY', 'DCA', buy_qty, current_close, commission)
        
        return True
    return False


def open_tactical_trade(row, portfolio: dict, allocation_pct: float) -> bool:
    """Opens a tactical position and modifies the portfolio state."""
    global ATR_MULTIPLIER, COMMISSION_RATE

    if portfolio.get('swing_qty', 0.0) > 0:
        return False

    trade_budget = portfolio['cash'] * allocation_pct

    if trade_budget > 0:
        entry_price = row['Close']
        commission = trade_budget * COMMISSION_RATE
        buy_qty = (trade_budget - commission) / entry_price

        # ATR Stop Loss Calculation
        stop_loss_level = entry_price - (row['ATR'] * ATR_MULTIPLIER)

        # Update portfolio directly
        portfolio['cash'] -= trade_budget
        portfolio['btc_qty'] += buy_qty
        portfolio['swing_qty'] = buy_qty
        portfolio['swing_entry_price'] = entry_price
        portfolio['stop_loss_level'] = stop_loss_level
        
        # ----- LOG TRADE ---
        log_trade_event(row.name, 'BUY', 'Swing', buy_qty, entry_price, commission)

        return True
    return False


def close_tactical_trade(row, portfolio: dict, final_action: str) -> bool:
    """Determines and executes the parameters for closing the tactical trade (SL or TP)."""
    global COMMISSION_RATE

    if portfolio.get('swing_qty', 0.0) == 0.0:
        return False

    btc_to_sell = portfolio['swing_qty']
    current_close = row['Close']
    entry_price = portfolio['swing_entry_price']

    exit_price = 0.0
    exit_type = '' # Initialize exit_type for logging

    # Condition 1: STOP-LOSS CHECK (Risk Management Override)
    if current_close < portfolio['stop_loss_level']:
        exit_price = portfolio['stop_loss_level']
        exit_type = 'SwingSL' # Set log type for Stop-Loss

    # Condition 2: PROFIT-TAKE CHECK (Strategy Driven)
    elif current_close >= entry_price * 1.05:
      exit_price = current_close
      exit_type = 'SwingTP' # Set log type for Take-Profit

    else:
        return False # No exit condition met

    # Execute Sale
    sale_usd = btc_to_sell * exit_price
    commission = sale_usd * COMMISSION_RATE

    # Update portfolio directly
    portfolio['cash'] += sale_usd - commission
    portfolio['btc_qty'] -= btc_to_sell

    # ----- LOG TRADE (ADDED LOGIC) ---
    log_trade_event(row.name, 'SELL', exit_type, btc_to_sell, exit_price, commission)

    # Reset swing trade variables
    portfolio['swing_qty'] = 0.0
    portfolio['swing_entry_price'] = 0.0
    portfolio['stop_loss_level'] = 0.0

    return True


## -------------------------------------------------------------- ##
# COMBINED STRATEGY (MASTER DECIDER AND EXECUTOR)
# --- Updated: Removed dependency on 'decide_strategy' and integrated TA logic ---
## -------------------------------------------------------------- ##


def get_combined_signal_and_execute(current_data: pd.Series, portfolio: dict) -> dict:
    """
    Combines TA (in-line) and Sentiment, applies the Adaptive Multiplier,
    makes the final decision, and executes the trade by modifying the portfolio.
    """
    global SWING_TRADE_ALLOCATION_MAX

    # --- 1. BASE DECISION LOGIC (TA and Sentiment Score Calculation) ---
    # 1.1 Calculate TA Mode In-Line (REPLACEMENT FOR decide_strategy)
    rsi = current_data['RSI']
    macd_delta = current_data['MACD'] - current_data['MACD_Signal']

    if macd_delta > 0 and rsi > 55:
        # Strong Momentum, suggests swinging
        ta_mode = 'SWING_TRADE'
    elif rsi < 50 and rsi > 30 and abs(macd_delta) < 0.1:
        # Low momentum, likely consolidation/range
        ta_mode = 'RANGE_BOUND'
    else:
        ta_mode = 'NEUTRAL'

    # 1.2 Calculate Scores
    fgi_score = current_data['FGI_Score']

    sentiment_score = 0
    if fgi_score <= 24: sentiment_score = 2
    elif fgi_score <= 49: sentiment_score = 1
    elif fgi_score >= 75: sentiment_score = -1

    ta_score = 0
    if ta_mode == 'SWING_TRADE': ta_score = 2
    elif ta_mode == 'RANGE_BOUND': ta_score = 1
    # NEUTRAL ta_mode implicitly gives ta_score = 0

    combined_score = ta_score + sentiment_score

    # 1.3 Determine Final Action and Base Allocation
    if combined_score >= 4:
        final_action = "AGGRESSIVE_BUY"
        base_allocation_pct = SWING_TRADE_ALLOCATION_MAX # Base 100% of max
    elif combined_score >= 2:
        final_action = "MODERATE_BUY"
        base_allocation_pct = SWING_TRADE_ALLOCATION_MAX * 0.5 # Base 50% of max
    elif combined_score <= -1:
        final_action = "AVOID_ENTRY"
        base_allocation_pct = 0.0
    else:
        final_action = "HOLD_DCA_ONLY"
        base_allocation_pct = 0.0

    # --- 2. MULTIPLIER CALCULATION AND APPLICATION ---

    # Only calculate and apply the multiplier if there is a potential BUY action
    if 'BUY' in final_action:
        # Get the adaptive risk multiplier from the stable rule-based function
        risk_multiplier = get_final_multiplier(current_data, final_action)

        # Apply the multiplier to the base trade size
        allocation_pct = base_allocation_pct * risk_multiplier

        # Final safety clamp: Ensure we don't exceed the global max allocation
        allocation_pct = min(allocation_pct, SWING_TRADE_ALLOCATION_MAX)

        # If the multiplier drops the trade size too low, update the action description
        if allocation_pct < SWING_TRADE_ALLOCATION_MAX * 0.1:
             final_action = f"RISK_BLOCKED_{final_action}"
    else:
        allocation_pct = base_allocation_pct
        risk_multiplier = 1.0 # For reporting purposes

    # --- 3. EXECUTION LOGIC ---
    executed_trades = [] # <---  TRACK ALL TRADES ON THIS DAY

    # Use a variable for the action string to pass to execution functions
    current_final_action = final_action

    # A. Execute Exits (Must check this first)
    if close_tactical_trade(current_data, portfolio, current_final_action):
        executed_trades.append("SWING EXIT")

    # B. Execute DCA Buy (Usually runs regardless of tactical signal)
    if execute_dca_buy(current_data, portfolio):
        executed_trades.append("DCA BUY")

    # C. Execute TACTICAL Entry (Driven by the final_action and calculated allocation_pct)
    if 'BUY' in current_final_action and portfolio['swing_qty'] == 0.0 and allocation_pct > 0:
        if open_tactical_trade(current_data, portfolio, allocation_pct):
            executed_trades.append("SWING ENTRY")

    return {
        'final_action': final_action,
        'trade_occurred': len(executed_trades) > 0,
        'executed_trades': executed_trades,
        'ta_mode': ta_mode,
        'fgi_score': fgi_score,
        'multiplier': risk_multiplier,
        'final_allocation_pct': allocation_pct
    }
    

# ==============================================================================
# TELEGRAM ALERT FUNCTION (Reads from .json file)
# ==============================================================================
def send_telegram_message(message: str):
    """Sends a message to the configured Telegram chat by reading credentials from config.json."""
    
   # ---  Read directly from environment variables ---
    BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    # -----------------------------------------------------------
    
    if not BOT_TOKEN or not CHAT_ID:
        # NOTE: Using print() here is safe as this is run on the server
        print("Telegram environment variables (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID) not found. Skipping alert.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, data=payload, timeout=5)
        response.raise_for_status() # Raise an exception for bad status codes
        # print("Telegram message sent successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send Telegram message: {e}")


# ==============================================================================
# 6. WEEKLY EMAIL REPORTING FUNCTION (Loads data from persisted files)
# ==============================================================================

def analyze_weekly_data() -> Tuple[dict, dict, float, float]:
    """Loads and processes the portfolio state and trade logs for the report."""
    global PORTFOLIO_STATE_FILE, TRADE_LOG_FILE, STARTING_BUDGET
    
    # 2.1 Load Portfolio State
    portfolio = {}
    try:
        with open(PORTFOLIO_STATE_FILE, 'r') as f:
            portfolio = json.load(f)
    except Exception:
        print("⚠️ Warning: Could not load portfolio state. Using initial defaults.")
        portfolio = {'btc_qty': 0.0, 'total_value_usd': STARTING_BUDGET, 'cash': STARTING_BUDGET}

    # 2.2 Analyze Trade Log
    weekly_summary = {
        'total_trades': 0, 
        'DCA': 0, 
        'Swing': 0,  
        'total_fees': 0.0
    }
    
    one_week_ago = datetime.now() - timedelta(days=7)
    current_equity = portfolio.get('total_value_usd', STARTING_BUDGET)
    
    # To calculate P/L, we need the equity value exactly one week ago.
    # We will approximate the previous week's equity using a simplified method.
    # NOTE: In a professional setting, this requires saving a daily/weekly equity snapshot.
    approx_previous_equity = STARTING_BUDGET # Using the initial budget as a simple baseline

    try:
        df_log = pd.read_csv(TRADE_LOG_FILE)
        df_log['Date'] = pd.to_datetime(df_log['Date'])
        
        # Filter for the last week
        df_week = df_log[df_log['Date'] >= one_week_ago].copy()
        
        if not df_week.empty:
            weekly_summary['total_trades'] = len(df_week)
            # Log trades must be properly tagged in your execute functions (DCA, Swing)
            weekly_summary['DCA'] = len(df_week[df_week['Trade_Type'] == 'DCA'])
            weekly_summary['Swing'] = len(df_week[df_week['Trade_Type'].str.contains('Swing', case=False)]) # Covers Swing, SwingSL, SwingTP
            weekly_summary['total_fees'] = df_week['Fees'].sum()
            
    except FileNotFoundError:
        print("⚠️ Warning: Trade log file not found. Summary will be empty.")

    # 2.3 Calculate P/L this week (simplified)
    equity_change_usd = current_equity - approx_previous_equity
    equity_change_pct = (equity_change_usd / approx_previous_equity) * 100 if approx_previous_equity else 0
    
    return portfolio, weekly_summary, equity_change_usd, equity_change_pct


def generate_report_content() -> Tuple[str, str]:
    """Generates the subject and HTML body using analyzed data."""
    
    portfolio, summary, p_l_usd, p_l_pct = analyze_weekly_data()
    
    # Ensure P/L is positive/negative formatted
    p_l_usd_str = f"{p_l_usd:+.2f}"
    p_l_pct_str = f"{p_l_pct:+.2f}%"
    
    report_subject = f"Weekly Trading Bot Report - P/L: {p_l_usd_str} USD ({p_l_pct_str})"
    
    # Format the requested data for the email body
    html_body = f"""\
    <html>
      <body>
        <h2>Weekly Trading Bot Performance Summary</h2>
        <p>Dear User,</p>
        <p>This report covers the past week's activity and the current state of your portfolio as of {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.</p>
        
        <h3>Portfolio Snapshot:</h3>
        <ul>
          <li><strong>Portfolio Value:</strong> ${portfolio['total_value_usd']:,.2f}</li>
          <li><strong>Holdings:</strong> {portfolio['btc_qty']:.2f} BTC, ${portfolio['cash']:,.2f} Cash</li>
        </ul>
        
        <h3>Weekly Metrics:</h3>
        <ul>
          <li><strong>P/L this week:</strong> {p_l_pct_str}, ${p_l_usd_str}</li>
          <li><strong>Total Trades:</strong> {summary['total_trades']} ({summary['DCA']} DCA, {summary['Swing']} swing </li>
          <li><strong>Total Fees Paid:</strong> ${summary['total_fees']:.2f}</li>
        </ul>
        
        <p>This confirms the bot is running on AWS. The next report will be sent next Monday at 9:00 AM.</p>
        <p>Best regards,<br>The Bot.</p>
      </body>
    </html>
    """
    return report_subject, html_body


def send_weekly_email_report():
    """Sends the report email using Gmail's SMTP server."""
    global EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, SMTP_SERVER, SMTP_PORT
    
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("❌ Email credentials (GMAIL_USER/GMAIL_PASS) not set or empty. Cannot send email.")
        return

    subject, body = generate_report_content()
    
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECIPIENT
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # Secure the connection
            server.login(EMAIL_SENDER, EMAIL_PASSWORD) # Login with App Password
            server.send_message(msg)
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Weekly report successfully sent to {EMAIL_RECIPIENT}!")

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ FATAL Error sending email: {e}")



# ==============================================================================
# MAIN EXECUTION LOOP
# ==============================================================================

# Initialize portfolio (must be done only once, outside the loop) 
portfolio = { 
    'cash': STARTING_BUDGET, 
    'btc_qty': 0.0, 
    'swing_qty': 0.0, 
    'swing_entry_price': 0.0, 
    'stop_loss_level': 0.0, 
    'total_value_usd': STARTING_BUDGET, 
    'prev_week_equity': STARTING_BUDGET, # <--- NEW: Initial value for P/L baseline 
    'last_report_date': None, # <--- NEW: Initial value for report date 
    'last_processed_date': datetime(2023, 1, 1) # <--- NEW: Tracks the last day we traded! (Use history start date) 
    }


# --- Check for persisted state on startup ---
try:
    with open(PORTFOLIO_STATE_FILE, 'r') as f:
        loaded_portfolio = json.load(f)
        # Only load keys that are expected to be present to prevent errors
        for key in portfolio:
            if key in loaded_portfolio:
                portfolio[key] = loaded_portfolio[key]
        
        # <--- UPDATE: Convert dates back from string if they were loaded as strings
        if isinstance(portfolio.get('last_report_date'), str):
             portfolio['last_report_date'] = datetime.strptime(portfolio['last_report_date'], '%Y-%m-%d %H:%M:%S')
        
        if isinstance(portfolio.get('last_processed_date'), str): # <--- NEW: Convert processed date back to datetime
             portfolio['last_processed_date'] = datetime.strptime(portfolio['last_processed_date'], '%Y-%m-%d %H:%M:%S')

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💾 Portfolio state loaded from {PORTFOLIO_STATE_FILE}.")
except FileNotFoundError:
    # If file not found, use initial portfolio defined above and save it
    save_portfolio_state(portfolio)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🆕 Initial portfolio created and saved.")
except Exception as e:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Error loading portfolio state: {e}. Using default.")
# --- END NEW CHECK ---


def run_bot():
    """Fetches data, runs strategy, reports, and waits."""
    global CHECK_INTERVAL_SECONDS, portfolio
    
    while True:
        try:
            # 1. DATA ACQUISITION & PREP
            df = get_gsheet_data() 
            
            if df.empty:
                time.sleep(CHECK_INTERVAL_SECONDS)
                continue

            # CRITICAL CHECK: Ensure the DataFrame has the necessary TA columns
            # The strategy logic relies on 'RSI', 'MACD', 'MACD_Signal', 'ATR', and 'FGI_Score'
            required_cols = ['RSI', 'MACD', 'MACD_Signal', 'ATR', 'FGI_Score', 'Close']
            if not all(col in df.columns for col in required_cols):
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🛑 Missing required TA columns. Ensure your GSheet preparation adds: {required_cols}. Waiting...")
                time.sleep(CHECK_INTERVAL_SECONDS)
                continue

          # 🚀 NEW DYNAMIC LOOKBACK LOGIC (Now that data is validated) 🚀
            # This logic runs immediately after validation to set the starting point
            if not df.empty:
                latest_data_date = df.index.max()
                lookback_start_date = latest_data_date - timedelta(days=7)
                portfolio['last_processed_date'] = lookback_start_date
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚙️ Set Lookback Date: {lookback_start_date.strftime('%Y-%m-%d')} (Last 7 days of data)")
            # -------------------------------------------------------------

            # <--- NEW BATCH PROCESSING LOGIC
            last_date = portfolio['last_processed_date']
            new_data_df = df[df.index > last_date]
            trade_occurred_in_batch = False # Flag for batch Telegram alert

            if new_data_df.empty:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💤 No new data since {last_date.strftime('%Y-%m-%d')}. Waiting...")
                time.sleep(CHECK_INTERVAL_SECONDS)
                continue

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚀 Processing {len(new_data_df)} new data points.")

            for index, row in new_data_df.iterrows():

                # 2. RUN STRATEGY AND EXECUTE
                results = get_combined_signal_and_execute(row, portfolio)

                 # Update the last processed date in the portfolio
                portfolio['last_processed_date'] = index # Index is the datetime object for the day
                
                # Update equity for the day's close price and save state after each day is processed
                current_btc_price = row['Close'] # Price from the historical data
                current_equity = portfolio['cash'] + (portfolio['btc_qty'] * current_btc_price)
                portfolio['total_value_usd'] = current_equity
                save_portfolio_state(portfolio) # Save state after each day for recovery

                if results['trade_occurred']:
                    trade_occurred_in_batch = True

                    # Format the list of trades into a readable string
                    trade_list_str = "\n".join([f"- {trade_type}" for trade_type in results['executed_trades']])
                    
                    # Construct ONE detailed message containing ALL trades for this day
                    trade_summary_msg = (
                        f"🤖 *DAILY TRADES EXECUTED!* on {index.strftime('%Y-%m-%d')}\n"
                        f"Executed Trade Events:\n{trade_list_str}\n" # <-- ALL trades in one message
                        f"Final Action: **{results['final_action']}**\n"
                        f"Equity: ${current_equity:.2f} | BTC: {portfolio['btc_qty']:.4f}"
                    )
                    
                    # 🚨 Call the Telegram function here for immediate, per-trade alert
                    send_telegram_message(trade_summary_msg)
                    # ----------------------------------------------------

                print(f"  > [{index.strftime('%Y-%m-%d')}] Action: {results['final_action']} | Equity: ${current_equity:.2f}")
            
            # 3. REPORTING & PERSISTENCE
            status_message = (
                f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- BATCH RESULT ---"
                f"\n📈 Processed {len(new_data_df)} days. Final Action: *{results['final_action']}*"
                f"\n💰 Final Equity: ${current_equity:.2f} | ₿ Total BTC Qty: {portfolio['btc_qty']:.4f}"
            )
            
            print(status_message)
            

        except Exception as e:
            error_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]  UNHANDLED EXCEPTION in main loop: {e}"
            print(error_msg)
            # Send critical error alert
            send_telegram_message(f" CRITICAL ERROR ON AWS BOT:\n{error_msg}")
        
        # 4. WAIT
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]  Waiting {CHECK_INTERVAL_SECONDS // 60} minutes...")
        time.sleep(CHECK_INTERVAL_SECONDS)

 # ==============================================================================
# SCRIPT ENTRY POINT
# ==============================================================================
# Check for a command-line argument to run the emailer
if len(sys.argv) > 1 and sys.argv[1] == 'send_report':
    print("------------------------------------------")
    print("| WEEKLY EMAIL REPORTER STARTING (CRON) |")
    print("------------------------------------------")
    send_weekly_email_report()
else:
    # Run the main bot loop
    print("------------------------------------------")
    print("| BTC TRADING BOT STARTING |")
    print("------------------------------------------")
    # This calls the loop function and starts the 24/7 operation

    # Sends an immediate alert to confirm the main loop has successfully launched
    send_telegram_message("✅ *BOT STARTUP SUCCESSFUL!* Main trading loop initialized and running.")
    # ---------------------------

    run_bot()
