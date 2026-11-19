from datetime import datetime, timedelta, timezone
import logging
import sqlite3
import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)


def fetch_json(url: str) -> list:
  response = requests.get(url, timeout=10)
  response.raise_for_status()
  return response.json()


def build_star_schema():
  conn = sqlite3.connect("company_data.db")
  cursor = conn.cursor()

  # 1. EXTRACT RAW SOURCE DATA
  logging.info("Extracting source users and posts...")
  raw_users = fetch_json("https://jsonplaceholder.typicode.com/users")
  raw_posts = fetch_json("https://jsonplaceholder.typicode.com/posts")

  # 2. CREATE DIMENSION TABLES (With Warehouse Surrogate Keys)
  cursor.execute("DROP TABLE IF EXISTS dim_users;")
  cursor.execute("DROP TABLE IF EXISTS dim_date;")
  cursor.execute("DROP TABLE IF EXISTS fact_posts;")

  cursor.execute("""
        CREATE TABLE dim_users (
            user_sk INTEGER PRIMARY KEY AUTOINCREMENT,
            source_user_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            email_domain TEXT,
            city TEXT,
            company_name TEXT
        );
    """)

  cursor.execute("""
        CREATE TABLE dim_date (
            date_sk INTEGER PRIMARY KEY,
            full_date TEXT NOT NULL,
            day_name TEXT NOT NULL,
            is_weekend INTEGER NOT NULL
        );
    """)

  # 3. CREATE FACT TABLE (Foreign Keys + Quantitative Metrics)
  cursor.execute("""
        CREATE TABLE fact_posts (
            post_sk INTEGER PRIMARY KEY AUTOINCREMENT,
            source_post_id INTEGER UNIQUE NOT NULL,
            user_sk INTEGER NOT NULL,
            date_sk INTEGER NOT NULL,
            word_count INTEGER NOT NULL,
            title_char_length INTEGER NOT NULL,
            FOREIGN KEY (user_sk) REFERENCES dim_users(user_sk),
            FOREIGN KEY (date_sk) REFERENCES dim_date(date_sk)
        );
    """)

  # 4. POPULATE dim_users
  user_rows = [(
      u["id"],
      u["name"].strip(),
      u["email"].split("@")[-1].lower(),
      u["address"]["city"].strip(),
      u["company"]["name"].strip(),
  ) for u in raw_users]
  cursor.executemany(
      """
        INSERT INTO dim_users (source_user_id, full_name, email_domain, city, company_name)
        VALUES (?, ?, ?, ?, ?);
    """,
      user_rows,
  )

  # 5. POPULATE dim_date (Last 7 days for realistic time-series slicing)
  base_date = datetime(2026, 11, 13, tzinfo=timezone.utc)
  date_rows = []
  for i in range(7):
    dt = base_date + timedelta(days=i)
    date_sk = int(dt.strftime("%Y%m%d"))  # Standard warehouse key: 20261113
    day_name = dt.strftime("%A")
    is_weekend = 1 if dt.weekday() >= 5 else 0
    date_rows.append((date_sk, dt.strftime("%Y-%m-%d"), day_name, is_weekend))

  cursor.executemany(
      """
        INSERT INTO dim_date (date_sk, full_date, day_name, is_weekend)
        VALUES (?, ?, ?, ?);
    """,
      date_rows,
  )

  # 6. MAP NATURAL KEYS TO SURROGATE KEYS & LOAD fact_posts
  user_key_map = dict(
      cursor.execute("SELECT source_user_id, user_sk FROM dim_users;").fetchall()
  )

  fact_rows = []
  for idx, p in enumerate(raw_posts):
    user_sk = user_key_map[p["userId"]]
    # Distribute posts deterministically across the 7 dates
    date_sk = date_rows[idx % len(date_rows)][0]
    word_count = len(p["body"].split())
    title_len = len(p["title"].strip())
    fact_rows.append((p["id"], user_sk, date_sk, word_count, title_len))

  cursor.executemany(
      """
        INSERT INTO fact_posts (source_post_id, user_sk, date_sk, word_count, title_char_length)
        VALUES (?, ?, ?, ?, ?);
    """,
      fact_rows,
  )
  conn.commit()
  logging.info(
      f"Star Schema built: {len(user_rows)} dim_users, {len(date_rows)} dim_date, {len(fact_rows)} fact_posts."
  )

  # 7. STAR SCHEMA BI QUERY (Fact joined to 2 Dimensions)
  bi_query = """
     SELECT 
         CASE WHEN d.is_weekend = 1 THEN 'Weekend' ELSE 'Weekday' END AS day_type,
         COUNT(f.post_sk) AS total_posts,
         SUM(f.word_count) AS total_words,
         ROUND(AVG(f.word_count), 1) AS avg_words
     FROM fact_posts f
     INNER JOIN dim_date d ON f.date_sk = d.date_sk
     GROUP BY day_type
     ORDER BY total_posts DESC;
 """
  print("\n--- Star Schema BI Report: Top Content Output by Day & Company ---")
  print(pd.read_sql_query(bi_query, conn))
  conn.close()


if __name__ == "__main__":
  build_star_schema()