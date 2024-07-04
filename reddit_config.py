# Imports Don't edit:
import praw

# Configuration Settings:

# This should match the title in praw.ini or if you have multiple entries in praw.ini pick which one you want to use here.
reddit = praw.Reddit("reddit_login") 

# Your Moderator Username without the u/
moderator_name = "yourmoderatorname"

backup_directory = "Backups"

# List of subreddits to exclude from subreddit list
excluded_subreddits = ['somesubname', 'AnotherSubname', 'AnotherSubEtc']
