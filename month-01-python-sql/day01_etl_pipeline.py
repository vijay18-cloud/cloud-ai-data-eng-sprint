import csv
import json
import urllib.request

# 1. EXTRACT: Download data from the website
url = "https://jsonplaceholder.typicode.com/posts"
response = urllib.request.urlopen(url)
raw_posts = json.loads(response.read().decode("utf-8"))

cleaned_rows = []

# 2. TRANSFORM: Loop through every post and clean it
for post in raw_posts:
  # Check if userId is 5 or less (skip if greater than 5)
  if post["userId"] <= 5:
    post_id = post["id"]
    user_id = post["userId"]

    # Clean the title: strip spaces and make Title Case
    clean_title = post["title"].strip().title()

    # Count how many words are in post["body"]
    word_count = len(post["body"].split())

    # Add this cleaned row to our list
    cleaned_rows.append([post_id, user_id, clean_title, word_count])

# 3. LOAD: Save into a CSV file
with open("cleaned_posts.csv", mode="w", newline="", encoding="utf-8") as file:
  writer = csv.writer(file)
  # Write the header row first
  writer.writerow(["post_id", "user_id", "title", "word_count"])
  # Write all the cleaned rows
  writer.writerows(cleaned_rows)

print(f"Success! Saved {len(cleaned_rows)} cleaned posts to cleaned_posts.csv")