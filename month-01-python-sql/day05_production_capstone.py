from datetime import datetime, timezone
import logging
import sqlite3
import pandas as pd
import requests

# 1. CONFIGURE PRODUCTION LOGGING (Console + File)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler("month-01-python-sql/week-01/pipeline.log"),
        logging.StreamHandler(),
    ],
)


def fetch_json(url: str) -> list:
  logging.info(f"Extracting data from {url}")
  response = requests.get(url, timeout=10)
  response.raise_for_status()
  data = response.json()
  logging.info(f"Extracted {len(data)} records successfully.")
  return data


def validate_data(
    df: pd.DataFrame, table_name: str, required_cols: list, pk_col: str
) -> None:
  """Data Quality Gatekeeper: Halts pipeline if critical checks fail."""
  if df.empty:
    raise ValueError(f"DQ FAILED [{table_name}]: DataFrame is empty!")

  missing_cols = [c for c in required_cols if c not in df.columns]
  if missing_cols:
    raise ValueError(
        f"DQ FAILED [{table_name}]: Missing columns {missing_cols}"
    )

  if df[pk_col].isnull().any():
    raise ValueError(
        f"DQ FAILED [{table_name}]: Null values found in Primary Key '{pk_col}'"
    )

  if df[pk_col].duplicated().any():
    raise ValueError(
        f"DQ FAILED [{table_name}]: Duplicate Primary Keys found in '{pk_col}'"
    )

  logging.info(
      f"DQ PASSED [{table_name}]: {len(df)} valid rows, 0 null/duplicate keys."
  )


def run_capstone_pipeline():
  run_start = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
  conn = sqlite3.connect("company_data.db")
  cursor = conn.cursor()

  # Ensure Audit Log Table Exists
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS etl_run_logs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT,
            users_loaded INTEGER,
            posts_loaded INTEGER,
            status TEXT,
            error_message TEXT
        );
    """)

  try:
    # STEP 1: EXTRACT
    raw_users = fetch_json("https://jsonplaceholder.typicode.com/users")
    raw_posts = fetch_json("https://jsonplaceholder.typicode.com/posts")

    # STEP 2: TRANSFORM
    users_df = pd.DataFrame([{
        "user_id": u["id"],
        "name": u["name"].strip(),
        "email_domain": u["email"].split("@")[-1].lower(),
        "city": u["address"]["city"].strip(),
    } for u in raw_users])

    posts_df = pd.DataFrame([{
        "post_id": p["id"],
        "user_id": p["userId"],
        "title": p["title"].strip().title(),
        "word_count": len(p["body"].split()),
    } for p in raw_posts])

    # STEP 3: DATA QUALITY GATEKEEPER
    validate_data(
        users_df,
        "users_prod",
        ["user_id", "name", "email_domain", "city"],
        "user_id",
    )
    validate_data(
        posts_df,
        "posts_prod",
        ["post_id", "user_id", "title", "word_count"],
        "post_id",
    )

    if (posts_df["word_count"] <= 0).any():
      raise ValueError(
          "DQ FAILED [posts_prod]: Found post with 0 or negative word_count!"
      )

    # STEP 4: IDEMPOTENT LOAD (UPSERT)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS users_prod (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email_domain TEXT,
                city TEXT
            );
        """)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts_prod (
                post_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                title TEXT,
                word_count INTEGER
            );
        """)

    cursor.executemany(
        "INSERT OR REPLACE INTO users_prod VALUES (?, ?, ?, ?);",
        users_df.itertuples(index=False, name=None),
    )
    cursor.executemany(
        "INSERT OR REPLACE INTO posts_prod VALUES (?, ?, ?, ?);",
        posts_df.itertuples(index=False, name=None),
    )

    # STEP 5: LOG SUCCESS TO AUDIT TABLE
    cursor.execute(
        """
            INSERT INTO etl_run_logs (run_timestamp, users_loaded, posts_loaded, status, error_message)
            VALUES (?, ?, ?, 'SUCCESS', NULL);
        """,
        (run_start, len(users_df), len(posts_df)),
    )
    conn.commit()
    logging.info("Pipeline completed and committed to SQLite successfully.")

    # DISPLAY AUDIT LOGS
    audit_df = pd.read_sql_query(
        "SELECT * FROM etl_run_logs ORDER BY run_id DESC LIMIT 5;", conn
    )
    print("\n--- Recent Pipeline Audit Logs ---")
    print(audit_df)

  except Exception as e:
    logging.error(f"Pipeline aborted: {e}")
    cursor.execute(
        """
            INSERT INTO etl_run_logs (run_timestamp, users_loaded, posts_loaded, status, error_message)
            VALUES (?, 0, 0, 'FAILED', ?);
        """,
        (run_start, str(e)),
    )
    conn.commit()
  finally:
    conn.close()


if __name__ == "__main__":
  run_capstone_pipeline()