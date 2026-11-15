import csv
import json
import urllib.request

url = "https://jsonplaceholder.typicode.com/posts"
response = urllib.request.urlopen(url)
raw_posts = json.loads(response.read().decode("utf-8"))

cleaned_rows = []

for post in raw_posts:

  if post["userId"] <= 5:
    post_id = post["id"]
    user_id = post["userId"]

    clean_title = post["title"].strip().title()

    
    word_count = len(post["body"].split())


    cleaned_rows.append([post_id, user_id, clean_title, word_count])


with open("cleaned_posts.csv", mode="w", newline="", encoding="utf-8") as file:
  writer = csv.writer(file)
  
  writer.writerow(["post_id", "user_id", "title", "word_count"])
  
  writer.writerows(cleaned_rows)

print(f"Success! Saved {len(cleaned_rows)} cleaned posts to cleaned_posts.csv")