import sqlite3
import pandas as pd
import requests


def fetch_json(url):
  response = requests.get(url, timeout=10)
  response.raise_for_status()
  return response.json()


def run_pipeline():
  # 1. EXTRACT BOTH ENDPOINTS
  try:
    raw_users = fetch_json("https://jsonplaceholder.typicode.com/users")
    raw_posts = fetch_json("https://jsonplaceholder.typicode.com/posts")
  except requests.exceptions.RequestException as e:
    print(f"Extraction failed: {e}")
    return

  # 2. TRANSFORM INTO TWO CLEAN DATAFRAMES
  users_df = pd.DataFrame([{
      "user_id": u["id"],
      "name": u["name"],
      "city": u["address"]["city"],
  } for u in raw_users])

  posts_df = pd.DataFrame([{
      "post_id": p["id"],
      "user_id": p["userId"],
      "title": p["title"].strip().title(),
      "word_count": len(p["body"].split()),
  } for p in raw_posts])

  # 3. LOAD BOTH TABLES INTO SQLITE
  conn = sqlite3.connect("company_data.db")
  users_df.to_sql("users", conn, if_exists="replace", index=False)
  posts_df.to_sql("posts", conn, if_exists="replace", index=False)

  # QUERY A: JOIN + AGGREGATION
  query_join = """
        SELECT 
            u.user_id,
            u.name,
            u.city,
            COUNT(p.post_id) AS total_posts,
            ROUND(AVG(p.word_count), 1) AS avg_word_count
        FROM users u
        INNER JOIN posts p ON u.user_id = p.user_id
        GROUP BY u.user_id, u.name, u.city
        ORDER BY avg_word_count DESC;
    """
  print("--- Query A: User Post Summary (INNER JOIN) ---")
  print(pd.read_sql_query(query_join, conn))

  # QUERY B: CTE + WINDOW FUNCTION (Top #1 longest post per user)
  query_window = """
        WITH RankedPosts AS (
            SELECT 
                u.name,
                u.city,
                p.post_id,
                p.word_count,
                ROW_NUMBER() OVER (
                    PARTITION BY p.user_id 
                    ORDER BY p.word_count DESC, p.post_id ASC
                ) AS post_rank
            FROM posts p
            INNER JOIN users u ON p.user_id = u.user_id
        )
        SELECT name, city, post_id, word_count, post_rank
        FROM RankedPosts
        WHERE post_rank <= 2
        ORDER BY word_count DESC;
    """
  print("\n--- Query B: Longest Post Per User (Window Function) ---")
  print(pd.read_sql_query(query_window, conn))

  conn.close()


if __name__ == "__main__":
  run_pipeline()