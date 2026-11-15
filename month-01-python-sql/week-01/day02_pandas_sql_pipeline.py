import sqlite3
import pandas as pd
import requests


def run_pipeline():
  url = "https://jsonplaceholder.typicode.com/users"

  # 1. EXTRACT (with error handling)
  try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    raw_users = response.json()
  except requests.exceptions.RequestException as e:
    print(f"API Extraction Failed: {e}")
    return

  # 2. TRANSFORM (flatten nested JSON & clean with Pandas)
  records = []
  for user in raw_users:
    clean_email = user["email"].strip().lower()
    domain = clean_email.split("@")[-1]
    city = user["address"]["city"]

    records.append({
        "user_id": user["id"],
        "name": user["name"],
        "username": user["username"],
        "email": clean_email,
        "email_domain": domain,
        "city": city,
    })

  df = pd.DataFrame(records)
  print("--- Cleaned DataFrame Preview ---")
  print(df.head())

  # 3. LOAD (save into SQLite database & run SQL query)
  conn = sqlite3.connect("company_data.db")
  df.to_sql("users", conn, if_exists="replace", index=False)

  query = """
        SELECT city, email_domain, COUNT(*) AS total_users
        FROM users
        GROUP BY city, email_domain
        ORDER BY total_users DESC;
    """
  sql_result = pd.read_sql_query(query, conn)
  conn.close()

  print("\n--- SQL Query Result (Users per City) ---")
  print(sql_result)


if __name__ == "__main__":
  run_pipeline()