import csv
import json
import os
import logging
import re
from datetime import datetime

# Replace with the path to your folder of CSV files
csv_dir = "/home/ivob/Downloads/datahff/Pangolin/help_yZfXYb1kB6"

def infer_name_from_filename(filename):
    """
    Infers the name for the DiscussionForumPosting from the CSV filename.
    Converts 'my_file_name.csv' to 'My File Name'.
    """
    base = os.path.splitext(filename)[0]
    # Replace non-alphanumeric characters with spaces, then title case each word
    # and join with spaces for readability.
    words = re.findall(r'\w+', base)
    return ' '.join(word.capitalize() for word in words)

def slugify_filename(filename):
    """
    Creates a URL-friendly slug from the filename.
    e.g., 'Auth for specific URL!_page_1.csv' -> 'auth-for-specific-url-page-1'
    """
    base = os.path.splitext(filename)[0]
    slug = re.sub(r'[^\w\s-]', '', base).strip().lower()
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.exists(csv_dir):
        logging.error(f"Directory {csv_dir} does not exist. Please check the path.")
        return

    processed_dir = os.path.join(csv_dir, "processed")
    os.makedirs(processed_dir, exist_ok=True)
    logging.info(f"Output directory for processed files: {processed_dir}")

    total_csv_files_processed = 0
    total_jsonl_documents_generated = 0

    # Discord fixed guild ID from your example
    discord_guild_id = "1325658630518865980" 
    discord_channels_base_url = "https://discord.com/channels/"

    for filename in os.listdir(csv_dir):
        if filename.endswith(".csv"):
            filepath = os.path.join(csv_dir, filename)
            
            jsonl_output_lines = [] # To store lines for the .jsonl file

            try:
                with open(filepath, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    
                    if not reader.fieldnames:
                        logging.warning(f"Skipping {filename}: No headers found in the CSV file.")
                        continue

                    rows = list(reader) # Read all rows into a list

                    if not rows:
                        logging.info(f"No valid rows found in {filename}.")
                        continue

                    # --- Process the main DiscussionForumPosting (thread) ---
                    first_row = rows[0]
                    thread_channel_id = first_row.get("channel_id")
                    
                    if thread_channel_id:
                        thread_url = f"{discord_channels_base_url}{discord_guild_id}/{thread_channel_id}"
                    else:
                        thread_slug = slugify_filename(filename)
                        thread_url = f"https://example.com/forum/thread/{thread_slug}"
                        logging.warning(f"No 'channel_id' found in the first row of {filename}. Using fallback thread URL: {thread_url}")

                    thread_name = infer_name_from_filename(filename)
                    thread_article_body = first_row.get("content") or ""
                    thread_description = thread_article_body if thread_article_body else f"Discussion thread: {thread_name}"
                    
                    thread_date_created = None
                    if first_row.get("timestamp"):
                        try:
                            thread_date_created = datetime.fromisoformat(first_row["timestamp"].replace('Z', '+00:00')).isoformat()
                        except ValueError:
                            if first_row.get("date"):
                                try:
                                    thread_date_created = datetime.fromisoformat(first_row["date"].replace('Z', '+00:00')).isoformat()
                                except ValueError:
                                    pass

                    discussion_forum_posting_json_ld = {
                        "@context": "http://schema.org/", 
                        "@type": "DiscussionForumPosting",
                        "@id": thread_url, 
                        "name": thread_name, 
                        "url": thread_url,
                        "articleBody": thread_article_body,
                        "description": thread_description,
                        "dateCreated": thread_date_created,
                        # No 'comment' array here, comments will be separate documents
                    }
                    # Add the thread itself as a document to the JSONL output
                    jsonl_output_lines.append(f"{thread_url}\t{json.dumps(discussion_forum_posting_json_ld, ensure_ascii=False)}")
                    total_jsonl_documents_generated += 1


                    # --- Process each row as a Comment ---
                    for row_num, row in enumerate(rows, start=1):
                        try:
                            comment_id = row.get("id")
                            
                            # Construct comment URL: base_thread_url/comment_id
                            if comment_id and thread_channel_id: 
                                comment_url = f"{discord_channels_base_url}{discord_guild_id}/{thread_channel_id}/{comment_id}"
                            else:
                                comment_url = f"{thread_url}#comment-{slugify_filename(filename)}-{row_num}"
                                logging.warning(f"Row {row_num} in {filename} missing 'id' or 'channel_id'. Using fallback comment URL: {comment_url}")

                            comment_text = row.get("content") or ""

                            comment_date_created = None
                            if row.get("timestamp"):
                                try:
                                    comment_date_created = datetime.fromisoformat(row["timestamp"].replace('Z', '+00:00')).isoformat()
                                except ValueError:
                                    logging.warning(f"Could not parse timestamp '{row.get('timestamp')}' for comment in row {row_num} of {filename}.")
                                    if row.get("date"):
                                        try:
                                            comment_date_created = datetime.fromisoformat(row["date"].replace('Z', '+00:00')).isoformat()
                                        except ValueError:
                                            logging.warning(f"Could not parse date '{row.get('date')}' for comment in row {row_num} of {filename}.")

                            comment_author_name = row.get("author.global_name") or row.get("author.username") or "Anonymous"

                            comment_json_ld = {
                                "@context": "http://schema.org/", 
                                "@type": "Comment",
                                "@id": comment_url, 
                                "text": comment_text,
                                "dateCreated": comment_date_created,
                                "author": {
                                    "@type": "Person",
                                    "name": comment_author_name
                                },
                                "url": comment_url,
                                # Link the comment back to its parent DiscussionForumPosting
                                "parentItem": {
                                    "@type": "DiscussionForumPosting",
                                    "@id": thread_url
                                }
                            }
                            # Add the comment as a document to the JSONL output
                            jsonl_output_lines.append(f"{comment_url}\t{json.dumps(comment_json_ld, ensure_ascii=False)}")
                            total_jsonl_documents_generated += 1 

                        except Exception as e:
                            logging.error(f"Error processing row {row_num} in {filename} as comment: {e}. Skipping row.")
                            continue

                if not jsonl_output_lines:
                    logging.info(f"No valid documents generated for {filename}.")
                    continue

                out_jsonl_filename = filename.replace(".csv", ".jsonl")
                outpath = os.path.join(processed_dir, out_jsonl_filename)
                
                with open(outpath, "w", encoding="utf-8") as f:
                    for line in jsonl_output_lines:
                        f.write(line + "\n")

                logging.info(f"Processed {filename} → {len(jsonl_output_lines)} documents saved to {out_jsonl_filename}.")
                total_csv_files_processed += 1
                break
            
            except FileNotFoundError:
                logging.error(f"File not found: {filepath}. Skipping.")
            except Exception as e:
                logging.error(f"An unexpected error occurred while processing {filename}: {e}")

    logging.info(f"Finished processing. Total CSV files processed: {total_csv_files_processed}.")
    logging.info(f"Total JSONL documents generated: {total_jsonl_documents_generated}.")

if __name__ == "__main__":
    main()