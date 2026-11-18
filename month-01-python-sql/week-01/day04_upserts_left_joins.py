import sqlite3
import pandas as pd
import requests


def fetch_json(url):
  response = requests.get(url, timeout=10)
  response.raise_for_status()
  return response.json()


def run_pipeline():
  # 1. EXTRACT
  try:
    raw_users = fetch_json("https://jsonplaceholder.typicode.com/users")
    raw_posts = fetch_json("https://jsonplaceholder.typicode.com/posts")
  except requests.exceptions.RequestException as e:
    print(f"Extraction failed: {e}")
    return

  conn = sqlite3.connect("company_data.db")
  cursor = conn.cursor()

  # 2. CREATE TABLES WITH PRIMARY KEYS (Prevents duplicate rows)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users_v2 (
            user_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT
        );
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts_v2 (
            post_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            title TEXT,
            word_count INTEGER
        );
    """)

  # 3. INCREMENTAL UPSERT (INSERT OR REPLACE)
  user_rows = [(u["id"], u["name"], u["address"]["city"]) for u in raw_users]
  # Adding User 11 (Vijay) with 0 posts to demonstrate LEFT JOIN behavior
  user_rows.append((11, "K Vijaykumar", "Chennai"))

  cursor.executemany(
      """
        INSERT OR REPLACE INTO users_v2 (user_id, name, city)
        VALUES (?, ?, ?);
    """,
      user_rows,
  )

  post_rows = [(
      p["id"],
      p["userId"],
      p["title"].strip().title(),
      len(p["body"].split()),
  ) for p in raw_posts]
  cursor.executemany(
      """
        INSERT OR REPLACE INTO posts_v2 (post_id, user_id, title, word_count)
        VALUES (?, ?, ?, ?);
    """,
      post_rows,
  )

  conn.commit()

  # Verify row count stays at 11 even if run multiple times
  total_users = cursor.execute("SELECT COUNT(*) FROM users_v2;").fetchone()[0]
  print(f"Total rows in users_v2 (Idempotent check): {total_users}\n")

  # 4. ANALYTICAL QUERY: LEFT JOIN + COALESCE + CASE WHEN
  query = """
        SELECT 
            u.user_id,
            u.name,
            u.city,
            COUNT(p.post_id) AS total_posts,
            COALESCE(ROUND(AVG(p.word_count), 1), 0) AS avg_word_count,
            CASE 
                WHEN COUNT(p.post_id) = 0 THEN 'Inactive'
                WHEN AVG(p.word_count) >= 27.0 THEN 'Top Performer'
                WHEN AVG(p.word_count) >= 25.0 THEN 'High-Depth Writer'
                ELSE 'Standard Writer'
            END AS writer_tier
        FROM users_v2 u
        LEFT JOIN posts_v2 p ON u.user_id = p.user_id
        GROUP BY u.user_id, u.name, u.city
        ORDER BY total_posts ASC, avg_word_count DESC;
    """
  result_df = pd.read_sql_query(query, conn)
  print("--- User Engagement & Tier Report (LEFT JOIN + CASE WHEN) ---")
  print(result_df)

  conn.close()


if __name__ == "__main__":
  run_pipeline()