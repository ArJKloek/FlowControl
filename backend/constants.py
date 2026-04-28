from pathlib import Path


# -----------------------------
# Paths And Files
# -----------------------------

# Project root directory (one level above backend/)
BASE_DIR = Path(__file__).resolve().parents[1]

# Location of Qt .ui files loaded by dialogs and windows
UI_DIR = BASE_DIR / "ui"

# Location of icon assets compiled into resources
ICON_DIR = BASE_DIR / "icon"

# Directory where runtime telemetry CSV logs are written
LOG_DIR = BASE_DIR / "Data"

# JSON file name for persisted per-serial-number gas factors
GAS_FACTORS_FILE = "gas_factors.json"


# -----------------------------
# Timing And Polling (ms)
# -----------------------------

# Generic polling interval used for periodic backend refresh loops (milliseconds)
POLL_INTERVAL_MS = 500

# Period between averaged telemetry log writes (milliseconds)
LOG_INTERVAL_MS = 300_000

# Interval for queued setpoint updates while user interacts with controls (milliseconds)
SETPOINT_POLL_INTERVAL_MS = 1000

# UI refresh cadence for setpoint/measure percentage indicators (milliseconds)
MEASURE_PERCENT_POLL_INTERVAL_MS = 750

# Debounce delay for user interactions before sending writes to the bus (milliseconds)
INTERACTION_POLL_SUSPEND_MS = 150

# Worker queue processing timer tick (milliseconds)
TELEMETRY_QUEUE_TICK_MS = 200

# Default status message auto-clear timeout in dialogs (milliseconds)
STATUS_MESSAGE_TIMEOUT_MS = 3000

# Longer timeout for communication/port error status messages (milliseconds)
PORT_ERROR_STATUS_TIMEOUT_MS = 10000


# -----------------------------
# UI Thresholds
# -----------------------------

# Ignore tiny percentage display changes below this threshold to reduce UI jitter
MEASURE_PERCENT_UI_EPSILON = 0.2

# Ignore tiny flow-value display changes below this threshold to reduce UI jitter
MEASURE_FLOW_UI_EPSILON = 1e-3


# -----------------------------
# Derived/Helper Values
# -----------------------------

# Time conversion helper used for interval calculations
SECONDS_PER_MINUTE = 60

# Default log interval used by UI controls and worker setup (minutes)
DEFAULT_LOG_INTERVAL_MIN = LOG_INTERVAL_MS // (SECONDS_PER_MINUTE * 1000)