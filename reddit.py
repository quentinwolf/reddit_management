# https://www.reddit.com/r/modhelp/comments/30amco/script_to_clear_all_users_flairs/cpv1n4l/
# https://www.reddit.com/r/redditdev/comments/i0rade/change_users_flair_on_subreddit/fzresun/

'''
# Pip Install Requirements:
alive-progress
'''

import io
import os
import sys
import signal
import traceback

import praw
import prawcore
from prawcore.exceptions import ServerError, Forbidden, TooManyRequests, ResponseException, RequestException

import time
from datetime import datetime
import logging
import csv

import re

from alive_progress import alive_bar
from alive_progress import alive_it
from alive_progress.styles import showtime, Show

import reddit_config  # Import your config.py

class OperationCancelled(Exception):
    pass

class CancelOperation:
    def __enter__(self):
        self.signal_received = False
        self.old_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self.handler)

    def handler(self, sig, frame):
        self.signal_received = True
        print('\nOperation cancelled. Returning to previous menu...')

    def __exit__(self, type, value, traceback):
        signal.signal(signal.SIGINT, self.old_handler)
        if self.signal_received:
            raise OperationCancelled


r = reddit_config.reddit
moderator_name = reddit_config.moderator_name

backup_directory = reddit_config.backup_directory

excluded_subreddits = reddit_config.excluded_subreddits

pickvalidoption = """
-----
Please pick a valid option.
-----
"""

separation = """

--------------------
"""



# Error handler by u/ParkingPsychology https://www.reddit.com/r/redditdev/comments/xtrvb7/praw_how_to_handle/iqupaxz/
def reddit_error_handler(func):
    def inner_function(*args, **kwargs):
        max_retries = 3
        retry_delay = 5
        max_retry_delay = 120

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except ServerError:
                sleep_ServerError = 240
                print(f"reddit_error_handler:\nFunction: {func.__name__}\nError: prawcore.exceptions.ServerError\nReddit may be down. Waiting {sleep_ServerError} seconds.")
                time.sleep(sleep_ServerError)
            except Forbidden:
                sleep_Forbidden = 20
                print(f"reddit_error_handler:\nFunction: {func.__name__}\nError: prawcore.exceptions.Forbidden\nWaiting {sleep_Forbidden} seconds.")
                time.sleep(sleep_Forbidden)
            except TooManyRequests:
                sleep_TooManyRequests = 30
                print(f"reddit_error_handler:\nFunction: {func.__name__}\nError: prawcore.exceptions.TooManyRequests\nWaiting {sleep_TooManyRequests} seconds.")
                time.sleep(sleep_TooManyRequests)
            except ResponseException:
                sleep_ResponseException = 20
                print(f"reddit_error_handler:\nFunction: {func.__name__}\nError: prawcore.exceptions.ResponseException\nWaiting {sleep_ResponseException} seconds.")
                time.sleep(sleep_ResponseException)
            except RequestException:
                sleep_RequestException = 20
                print(f"reddit_error_handler:\nFunction: {func.__name__}\nError: prawcore.exceptions.RequestException\nWaiting {sleep_RequestException} seconds.")
                time.sleep(sleep_RequestException)
            except praw.exceptions.RedditAPIException as exception:
                print(f"reddit_error_handler:\nFunction: {func.__name__}\nError: praw.exceptions.RedditAPIException")
                for subexception in exception.items:
                    if subexception.error_type == 'RATELIMIT':
                        message = subexception.message.replace("Looks like you've been doing that a lot. Take a break for ", "").replace("before trying again.", "")
                        if 'second' in message:
                            time_to_wait = int(message.split(" ")[0]) + 15
                            print(f"reddit_error_handler:\nFunction: {func.__name__}\nWaiting for {time_to_wait} seconds due to rate limit")
                            time.sleep(time_to_wait)
                        elif 'minute' in message:
                            time_to_wait = (int(message.split(" ")[0]) * 60) + 15
                            print(f"reddit_error_handler:\nFunction: {func.__name__}\nWaiting for {time_to_wait} seconds due to rate limit")
                            time.sleep(time_to_wait)
                    else:
                        print(f"reddit_error_handler:\nFunction: {func.__name__}\nDifferent Error: {subexception}")
                time.sleep(retry_delay)
            except Exception as e:
                error_message = f"reddit_error_handler:Function: {func.__name__}\nUnexpected Error: {str(e)}\ncalled with\n Args: {args}\n kwargs: {kwargs}"
                print(error_message)
                print(traceback.format_exc())  # Print the traceback

        # Retry loop
        for i in range(max_retries):
            if attempt < max_retries - 1:
                retry_delay = min(retry_delay * 2, max_retry_delay)  # Exponential backoff
                try:
                    return inner_function(*args, **kwargs)
                except Exception as e:
                    print(f"reddit_error_handler - Function: {func.__name__} - Retry attempt {i+1} failed. Retrying in {retry_delay} seconds...  Error: {str(e)}")
                    time.sleep(retry_delay)
            else:
                print(f"reddit_error_handler - Function: {func.__name__} - Max retries exceeded.")
                raise RuntimeError("Max retries exceeded in reddit_error_handler") from None

    return inner_function


def process_color_input(color):
    # Remove any leading/trailing whitespace and the '#' if present
    color = color.strip().lstrip('#')

    # Check if it's a valid 3 or 6 digit hex code
    if re.match(r'^([0-9A-Fa-f]{3}){1,2}$', color):
        if len(color) == 3:
            # Convert 3-digit to 6-digit
            color = ''.join([c*2 for c in color])
        return f'#{color.upper()}'
    else:
        return None  # Invalid input


#############################################################################################
#############################################################################################
# Generate Menu
def generate_menu(title, options, exit_option):
    menu_str = f"{title}\n\n"

    for i, option in enumerate(options, start=1):
        menu_str += f"{i}) {option}\n"

    menu_str += f"\n0) {exit_option}\n\n"

    return menu_str

# Subreddit Selection
def subreddit_selection(moderator_name, type):
    redditor = r.redditor(moderator_name)
    subreddits = redditor.moderated()

    modsubs_dict = dict()
    mod_subcount = 0
    print()

    for subreddit in subreddits:
        # Skip excluded subreddits
        if subreddit.display_name not in excluded_subreddits:
            mod_subcount += 1
            modsubs_dict[mod_subcount] = subreddit.display_name
            print(f"{mod_subcount}) {subreddit}")

    while True:
        try:
            if type == 'single':
                print()
                subreddit_name = input("Which Subreddit? ")
            elif type == 'multi':
                print(f"{mod_subcount + 12}) All moderated subreddits")
                print()
                subreddit_name = input("Which Subreddit(s)? (comma separated if multiple): ")

            if subreddit_name == '0':
                break

            input_subreddits = [int(x.strip()) for x in subreddit_name.split(",")]

            if mod_subcount + 12 in input_subreddits:
                modsubs_list = list(modsubs_dict.values())
            else:
                modsubs_list = [modsubs_dict[subredditx] for subredditx in input_subreddits]

            print()
            subreddit_string = ' '.join(map(str, modsubs_list))
            return subreddit_string

        except Exception as e:
            print("Error:", e)
            print("Please enter a valid input.")






#############################################################################################
#############################################################################################
# Main Menu
def main_menu():
    reddit_actions = {
        '1': lambda: content_menu(),
        '2': lambda: user_flair_management_menu(),
        '3': lambda: post_flair_management_menu(),
        '4': lambda: user_management_menu(),
        '5': lambda: test_menu(),
    }

    initial_options = [
        "Content Management",
        "User Flair Management",
        "Post Flair Management",
        "User Management",
        "Test Menu",
    ]

    initial_menu_str = generate_menu("Main Menu:", initial_options, "Quit")

    while True:
        print(separation)
        print(initial_menu_str)
        reddit_action = input("What action do you want to do? ")

        if reddit_action in reddit_actions:
            reddit_actions[reddit_action]()
        elif reddit_action == '0':
            sys.exit(0)
        else:
            print(pickvalidoption)





#############################################################################################
#############################################################################################
# test sub selection
def test_sub_selection():
    # Code here
    subreddit_string = subreddit_selection(moderator_name, 'multi')
    print("Selected subreddits:", subreddit_string)


# test menu
def test_menu():
    test_actions = {
        '1': lambda: test_sub_selection(),
    }

    test_options = [
        "Test Subreddit Selection",
    ]

    test_menu_str = generate_menu("Test Menu:", test_options, "Go back")

    while True:
        print(separation)
        print(test_menu_str)
        test_action = input("What do you want to test?: ")

        if test_action in test_actions:
            test_actions[test_action]()
        elif test_action == '0':
            break
        else:
            print(pickvalidoption)





#############################################################################################
#############################################################################################
# Content Menu
def content_menu():
    content_actions = {
        '1': lambda: content_nuke_comments(author, subreddit_string, shadowban),
        '2': lambda: content_nuke_submissions(author, subreddit_string, shadowban),
        '3': lambda: content_nuke_all(author, subreddit_string, shadowban),
        '4': lambda: content_restore_comments_from_file(),
        '5': lambda: content_restore_submissions_from_file(),
        '6': lambda: content_approve_unreported_posts(subreddit_string),
    }

    content_options = [
        "Nuke Comments",
        "Nuke Submissions",
        "Nuke All",
        "Restore Comments from file",
        "Restore Submissions from file",
        "Approve Unmoderated Posts (that do not have any user reports)",
    ]

    content_menu_str = generate_menu("Content Management:", content_options, "Go back")

    while True:
        print(separation)
        print(content_menu_str)
        content_action = input("What action do you want to do? ")

        if content_action in content_actions:
            if content_action in ['1', '2', '3']:
                author = input("For which User? ")
                subreddit_string = subreddit_selection(moderator_name, 'multi')
                shadowban_prompt = input("Shadowban user? (y/n, default n): ").lower()
                shadowban = shadowban_prompt == 'y'
            elif content_action in ['6']:
                subreddit_string = subreddit_selection(moderator_name, 'multi')
            content_actions[content_action]()
        elif content_action == '0':
            break
        else:
            print(pickvalidoption)


# Content Functions
@reddit_error_handler
def content_nuke_comments(author, subreddit_string, shadowban):
    timestr = time.strftime("%Y%m%d-%H%M%S")

    print(f"User: {author}")
    print(f"Selected subreddit(s): {subreddit_string}")
    print()

    content_limit = input("Content Limit? (How much to check, default 500): ")
    c_limit = int(content_limit) if content_limit else 500

    user = r.redditor(author)
    num_found = 0
    line_count = 0
    comment_dict = dict()

    modsubs_list = subreddit_string.split()  # Splitting the subreddit_string into a list

    filename = f'Backup_Nuked_Comments_{author}_{timestr}.csv'
    backup_file_path = os.path.join(backup_directory, filename)

    with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
        fieldnames = ['user', 'comment_id', 'subreddit']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        comment_ids = []
        bar = alive_it(user.comments.new(limit=c_limit), title='Counting...', theme='smooth')

        for comment in bar:
            for sub in modsubs_list:
                if comment.subreddit == sub and comment.banned_by is None:
                    comment_ids.append(comment.id)
                    comment_dict[comment.id] = sub
                    line_count += 1

        bar = alive_it(comment_dict.items(), total=line_count, dual_line=True, title=f'Nuking {line_count} Comments...', theme='smooth')

        for entry in bar:
            writer.writerow({'user': author, 'comment_id': entry[0], 'subreddit': entry[1]})
            bar.text = f"Removing {author}'s Comment ID {entry[0]} from {entry[1]}"
            removecomment = r.comment(entry[0])
            removecomment.mod.remove()

            num_found += 1

        print()
        print(f"{num_found} comments have been removed from {subreddit_string}.")

        if shadowban:
            shadowban_flair_css(author, subreddit_string)


@reddit_error_handler
def content_nuke_submissions(author, subreddit_string, shadowban):
    timestr = time.strftime("%Y%m%d-%H%M%S")

    print(f"User: {author}")
    print(f"Selected subreddits: {subreddit_string}")
    print()

    content_limit = input("Content Limit? (How much to check, default 500): ")
    c_limit = int(content_limit) if content_limit else 500

    user = r.redditor(author)
    num_found = 0
    line_count = 0
    submission_dict = dict()

    modsubs_list = subreddit_string.split()  # Splitting the subreddit_string into a list

    filename = f'Backup_Nuked_Posts_{author}_{timestr}.csv'
    backup_file_path = os.path.join(backup_directory, filename)

    with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
        fieldnames = ['user', 'submission_id', 'subreddit']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        submission_ids = []
        bar = alive_it(user.submissions.new(limit=c_limit), title='Counting...', theme='smooth')

        for submission in bar:
            for sub in modsubs_list:
                if submission.subreddit == sub and submission.banned_by is None:
                    submission_ids.append(submission.id)
                    submission_dict[submission.id] = sub
                    line_count += 1

        bar = alive_it(submission_dict.items(), total=line_count, dual_line=True, title=f'Nuking {line_count} Submissions...', theme='smooth')

        for entry in bar:
            writer.writerow({'user': author, 'submission_id': entry[0], 'subreddit': entry[1]})
            bar.text = f"Removing {author}'s Submission ID {entry[0]} from {entry[1]}"
            removesubmission = r.submission(entry[0])
            removesubmission.mod.remove()
            removesubmission.mod.lock()
            removesubmission.mod.spoiler()

            num_found += 1

        print()
        print(f"{num_found} submissions have been removed from {subreddit_string}.")

        if shadowban:
            shadowban_flair_css(author, subreddit_string)


@reddit_error_handler
def content_nuke_all(author, subreddit_string, shadowban):
    timestr = time.strftime("%Y%m%d-%H%M%S")

    print(f"User: {author}")
    print(f"Selected subreddits: {subreddit_string}")
    print()

    content_limit = input("Content Limit? (How much to check, default 500): ")
    c_limit = int(content_limit) if content_limit else 500

    user = r.redditor(author)
    num_found = 0
    line_count = 0
    comment_dict = dict()
    submission_dict = dict()

    modsubs_list = subreddit_string.split()  # Splitting the subreddit_string into a list

    filename = f'Backup_Nuked_Comments_{author}_{timestr}.csv'
    backup_file_path = os.path.join(backup_directory, filename)

    with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
        fieldnames = ['user', 'comment_id', 'subreddit']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        comment_ids = []
        bar = alive_it(user.comments.new(limit=c_limit), title='Counting...', theme='smooth')

        for comment in bar:
            for sub in modsubs_list:
                if comment.subreddit == sub and comment.banned_by is None:
                    comment_ids.append(comment.id)
                    comment_dict[comment.id] = sub
                    line_count += 1

        bar = alive_it(comment_dict.items(), total=line_count, dual_line=True, title=f'Nuking {line_count} Comments...', theme='smooth')

        for entry in bar:
            writer.writerow({'user': author, 'comment_id': entry[0], 'subreddit': entry[1]})
            bar.text = f"Removing {author}'s Comment ID {entry[0]} from {entry[1]}"
            removecomment = r.comment(entry[0])
            removecomment.mod.remove()

            num_found += 1

        print()
        print(f"{num_found} comments have been removed from {subreddit_string}.")

    num_found = 0
    line_count = 0
    print()

    filename = f'Backup_Nuked_Posts_{author}_{timestr}.csv'
    backup_file_path = os.path.join(backup_directory, filename)

    with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
        fieldnames = ['user', 'submission_id', 'subreddit']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        submission_ids = []
        bar = alive_it(user.submissions.new(limit=c_limit), title='Counting...', theme='smooth')

        for submission in bar:
            for sub in modsubs_list:
                if submission.subreddit == sub and submission.banned_by is None:
                    submission_ids.append(submission.id)
                    submission_dict[submission.id] = sub
                    line_count += 1

        bar = alive_it(submission_dict.items(), total=line_count, dual_line=True, title=f'Nuking {line_count} Submissions...', theme='smooth')

        for entry in bar:
            writer.writerow({'user': author, 'submission_id': entry[0], 'subreddit': entry[1]})
            bar.text = f"Removing {author}'s Submission ID {entry[0]} from {entry[1]}"
            removesubmission = r.submission(entry[0])
            removesubmission.mod.remove()
            removesubmission.mod.lock()
            removesubmission.mod.spoiler()

            num_found += 1

        print()
        print(f"{num_found} submissions have been removed from {subreddit_string}.")

    if shadowban:
        shadowban_flair_css(author, subreddit_string)


@reddit_error_handler
def content_restore_comments_from_file():
    timestr = time.strftime("%Y%m%d-%H%M%S")

    nuked_comment_files = [filename for filename in os.listdir() if "_Nuked_Comments_" in filename]

    print("Nuked comment files:\n")
    for i, filename in enumerate(nuked_comment_files):
        print(f"  {i + 1}) {filename}")
    print("\n0) Go back")

    choice = input("\nSelect an option or manually enter a filename: ")

    if choice == "0":
        return
    elif choice.isdigit() and int(choice) in range(1, len(nuked_comment_files) + 1):
        choice = int(choice)
        restore_filename = nuked_comment_files[choice - 1]
    else:
        restore_filename = choice

    # Rest of the content_restore_comments_from_file function using comment_filename

    print()
    print("Restore Comments from file:")

    log_file_bak = f"RestoreCommentsLog_{timestr}.log"
    log_file = os.path.join(backup_directory, log_file_bak )
    #restore_filename = input("Filename to restore? ")

    restore_action = input(f"Are you sure you want to restore {restore_filename} ? (y/n): ")
    print()

    if restore_action.lower() == 'y':
        num_found = 0
        line_count = 0

        with open(restore_filename, 'r') as fp:
            total_lines = len(fp.readlines())
            total_lines -= 1
            print(f"Total Number of comments to restore: {total_lines}\n")

        with open(restore_filename, mode='r') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            line_count = 0

            bar = alive_it(csv_reader, total=total_lines, dual_line=True, title=f'Restoring {total_lines} Comments...', theme='smooth')

            with open(log_file, "a", encoding="utf-8") as f:
                for row in bar:
                    if line_count == 0:
                        line_count += 1

                    bar.text = f'Restoring Comment ID '+row["comment_id"]

                    approvecomment = r.comment(row["comment_id"])
                    approvecomment.mod.approve()

                    num_found += 1
                    f.write(f'{row["user"]} Restored Comment: {row["comment_id"]} to {row["subreddit"]}\n')

                print()
                print(f"{num_found} Comments have been restored.")
                f.write(f"\n{num_found} Comments have been restored.\n\n")

        print()


@reddit_error_handler
def content_restore_submissions_from_file():
    timestr = time.strftime("%Y%m%d-%H%M%S")

    nuked_submission_files = [filename for filename in os.listdir() if "_Nuked_Posts_" in filename]

    print("Nuked submission files:\n")
    for i, filename in enumerate(nuked_submission_files):
        print(f"  {i + 1}) {filename}")
    print("\n0) Go back")

    choice = input("\nSelect an option or manually enter a filename: ")

    if choice == "0":
        return
    elif choice.isdigit() and int(choice) in range(1, len(nuked_submission_files) + 1):
        choice = int(choice)
        restore_filename = nuked_submission_files[choice - 1]
    else:
        restore_filename = choice

    # Rest of the content_restore_submissions_from_file function using submission_filename

    print()
    print("Restore Submissions from file:")

    log_file_bak = f"RestoreSubmissionsLog_{timestr}.log"
    log_file = os.path.join(backup_directory, log_file_bak )
    #restore_filename = input("Filename to restore? ")

    restore_action = input(f"Are you sure you want to restore {restore_filename} ? (y/n): ")
    print()

    if restore_action.lower() == 'y':
        num_found = 0
        line_count = 0

        with open(restore_filename, 'r') as fp:
            total_lines = len(fp.readlines())
            total_lines -= 1
            print(f"Total Number of submissions to restore: {total_lines}\n")

        with open(restore_filename, mode='r') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            line_count = 0

            bar = alive_it(csv_reader, total=total_lines, dual_line=True, title=f'Restoring {total_lines} Submissions...', theme='smooth')

            with open(log_file, "a", encoding="utf-8") as f:
                for row in bar:
                    if line_count == 0:
                        line_count += 1

                    bar.text = f'Restoring Submission ID {row["submission_id"]}'

                    approvesubmission = r.submission(row["submission_id"])
                    approvesubmission.mod.approve()
                    approvesubmission.mod.unlock()
                    approvesubmission.mod.unspoiler()

                    num_found += 1
                    f.write(f'{row["user"]} Restored Submission: {row["submission_id"]} to {row["subreddit"]}\n')

                print()
                print(f"{num_found} Submissions have been restored.")
                f.write(f"\n{num_found} Submissions have been restored.\n\n")

        print()


@reddit_error_handler
def content_approve_unreported_posts(subreddit_string):
    subreddits = subreddit_string.split()

    num_approved = 0
    subs_count = 0

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)
        subs_count += 1

        retry_subreddit = True

        while retry_subreddit:
            try:
                unmoderated_posts = subreddit.mod.unmoderated(limit=None)

                for post in unmoderated_posts:
                    if not post.num_reports:  # Checking if there are no reports
                        # Convert Unix timestamp to human-readable format
                        post_datetime = datetime.fromtimestamp(post.created_utc).strftime('%Y-%m-%d %H:%M:%S')

                        post.mod.approve()
                        num_approved += 1
                        print(f"Approved post '{post_datetime} {post.title}' (ID: {post.id}) in r/{subreddit_name}")

                retry_subreddit = False  # Exit the while loop after successful completion

            except prawcore.exceptions.RequestException as e:
                print(f"Encountered a request exception: {e}. Retrying...")
                time.sleep(60)  # Wait for 60 seconds before retrying

            except prawcore.exceptions.ResponseException as e:
                print(f"Encountered a response exception: {e} in r/{subreddit_name}.  Waiting 10 seconds and retrying.")
                #user_choice = input("Type '1' to retry the current subreddit, or press Enter to skip to the next subreddit: ").strip().lower()
                #if user_choice != '1':
                #    break  # Exit the while loop and skip to the next subreddit
                time.sleep(10)

            except Exception as e:
                print(f"Encountered an unexpected exception: {e}. Exiting.")
                return  # Exit the function

    print(f"\n\nApproval process completed.")
    print(f"{num_approved} submissions have been approved across {subs_count} subs.")







#############################################################################################
#############################################################################################
# User Flair Management
def user_flair_management_menu():
    flair_management_actions = {
        '1': lambda: find_flair_menu(subreddit_string),
        '2': lambda: replace_flair_menu(subreddit_string),
        '3': lambda: backup_flair_menu(subreddit_string),
        '4': lambda: restore_flair_menu(subreddit_string),
    }

    flair_management_options = [
        "Find Flair",
        "Replace Flair",
        "Backup Flair",
        "Restore Flair",
    ]

    flair_management_menu_str = generate_menu("Flair Management:", flair_management_options, "Go back")

    while True:
        print(separation)
        print(flair_management_menu_str)
        flair_action = input("What do you want to find?: ")

        if flair_action in flair_management_actions:
            if flair_action in ['4']:
                subreddit_string = subreddit_selection(moderator_name, 'single')
            if flair_action in ['1', '2', '3']:
                subreddit_string = subreddit_selection(moderator_name, 'multi')
            flair_management_actions[flair_action]()
        elif flair_action == '0':
            break
        else:
            print(pickvalidoption)





#############################################################################################
#############################################################################################
# Find User Flair Menu
def find_flair_menu(subreddit_string):
    find_flair_actions = {
        '1': lambda: find_flair_text(subreddit_string),
        '2': lambda: find_flair_css(subreddit_string),
        '3': lambda: find_flair_text_css(subreddit_string),
        '4': lambda: find_flair_text_regex(subreddit_string),
        '5': lambda: find_flair_css_regex(subreddit_string),
        '6': lambda: find_flair_text_css_regex(subreddit_string),
    }

    find_flair_options = [
        "Text",
        "CSS",
        "Text and CSS",
        "Text (Regex)",
        "CSS (Regex)",
        "Text (Regex) and CSS (Regex)",
    ]

    find_flair_menu_str = generate_menu("Find Flair:", find_flair_options, "Go back")

    while True:
        print(separation)
        print(find_flair_menu_str)
        flair_action = input("What do you want to find?: ")

        if flair_action in find_flair_actions:
            find_flair_actions[flair_action]()
        elif flair_action == '0':
            break
        else:
            print(pickvalidoption)


# Find Functions
@reddit_error_handler
def find_flair_text(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_text_flair = input("What Text Flair do you want to search? ")
    print()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_FindflairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        num_found = 0

        filename = f'{subreddit_name}_foundflair_{find_text_flair}_{timestr}.csv'
        backup_file_path  = os.path.join(backup_directory, filename)

        with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
            fieldnames = ['user', 'flair_text', 'flair_css_class']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

            writer.writeheader()

            bar = alive_it(subreddit.flair(limit=None), title=f'Searching for Text Flair: "{find_text_flair}"', theme='smooth')

            with open(log_file, "a", encoding="utf-8") as f:
                for flair in bar:
                    if flair['flair_text'] == find_text_flair:
                        user = flair['user'].name
                        original_flair = flair['flair_text'] or ""
                        original_cssflair = flair['flair_css_class'] or ""

                        writer.writerow({'user': user, 'flair_text': original_flair, 'flair_css_class': original_cssflair})

                        num_found += 1

                        print(f"{user:<25s} {'Text Flair: ' + original_flair:<35s} {'CSS Flair: ' + original_cssflair:<30s}")
                        f.write(f"{user} Found Text Flair: {original_flair}  and CSS Flair: {original_cssflair}\n")

                print()
                print(f"{num_found} flairs have been found in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been found in {subreddit_name}.\n\n")


@reddit_error_handler
def find_flair_css(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_css_flair = input("What CSS Flair do you want to search? ")
    print()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_FindflairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        num_found = 0

        filename = f'{subreddit_name}_foundcss_{timestr}.csv'
        backup_file_path  = os.path.join(backup_directory, filename)

        with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
            fieldnames = ['user', 'flair_text', 'flair_css_class']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

            writer.writeheader()

            bar = alive_it(subreddit.flair(limit=None), title=f'Searching for CSS Flair: "{find_css_flair}"', theme='smooth')

            with open(log_file, "a", encoding="utf-8") as f:
                for flair in bar:
                    if flair['flair_css_class'] == find_css_flair:
                        user = flair['user'].name
                        original_flair = flair['flair_text'] or ""
                        original_cssflair = flair['flair_css_class'] or ""

                        writer.writerow({'user': user, 'flair_text': original_flair, 'flair_css_class': original_cssflair})

                        num_found += 1

                        print(f"{user:<25s} {'Text Flair: ' + original_flair:<35s} {'CSS Flair: ' + original_cssflair:<30s}")
                        f.write(f"{user} Found Text Flair: {original_flair}  and CSS Flair: {original_cssflair}\n")

                print()
                print(f"{num_found} flairs have been found in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been found in {subreddit_name}.\n\n")


@reddit_error_handler
def find_flair_text_css(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_text_flair = input("What Text Flair do you want to search? ")
    find_css_flair = input("What CSS Flair do you want to search? ")
    print()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_FindflairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        num_found = 0

        filename = f'{subreddit_name}_foundflair_foundtext_foundcss_{timestr}.csv'
        backup_file_path  = os.path.join(backup_directory, filename)

        with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
            fieldnames = ['user', 'flair_text', 'flair_css_class']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

            writer.writeheader()

            bar = alive_it(subreddit.flair(limit=None), title=f'Searching for Flair, Text: "{find_text_flair}" and CSS: "{find_css_flair}"', theme='smooth')

            with open(log_file, "a", encoding="utf-8") as f:
                for flair in bar:
                    if flair['flair_text'] == find_text_flair and flair['flair_css_class'] == find_css_flair:
                        user = flair['user'].name
                        original_flair = flair['flair_text'] or ""
                        original_cssflair = flair['flair_css_class'] or ""

                        writer.writerow({'user': user, 'flair_text': original_flair, 'flair_css_class': original_cssflair})

                        num_found += 1

                        print(f"{user:<25s} {'Text Flair: ' + original_flair:<35s} {'CSS Flair: ' + original_cssflair:<30s}")
                        f.write(f"{user} Found Text Flair: {original_flair}  and CSS Flair: {original_cssflair}\n")

                print()
                print(f"{num_found} flairs have been found in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been found in {subreddit_name}.\n\n")


@reddit_error_handler
def find_flair_text_regex(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_text_flair = input("What (Regex) Text Flair do you want to search? ")
    print()

    find_text_flair_regex = str(find_text_flair)

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_FindflairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        num_found = 0

        filename = f'{subreddit_name}_foundtext-_regextext_{timestr}.csv'
        backup_file_path  = os.path.join(backup_directory, filename)

        with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
            fieldnames = ['user', 'flair_text', 'flair_css_class']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

            writer.writeheader()

            bar = alive_it(subreddit.flair(limit=None), title=f'Searching for Text Flair "{find_text_flair_regex}"', theme='smooth')

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"Searching for Regex Text Flair: {find_text_flair_regex}\n")

                for flair in bar:
                    isMatch = re.search(find_text_flair_regex, str(flair['flair_text']))

                    if isMatch:
                        user = flair['user'].name
                        original_flair = flair['flair_text'] or ""
                        original_cssflair = flair['flair_css_class'] or ""

                        writer.writerow({'user': user, 'flair_text': original_flair, 'flair_css_class': original_cssflair})

                        num_found += 1

                        print(f"{user:<25s} {'Text Flair: ' + original_flair:<35s} {'CSS Flair: ' + original_cssflair:<30s}")
                        f.write(f"{user} Found Text Flair: {original_flair}  and CSS Flair: {original_cssflair}\n")

                print()
                print(f"{num_found} flairs have been found in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been found in {subreddit_name}.\n\n")


@reddit_error_handler
def find_flair_css_regex(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    print(separation)
    print("Find Flair CSS (Regex):")

    find_css_flair = input("What (Regex) CSS Flair do you want to search? ")
    print()

    find_css_flair_regex = str(find_css_flair)

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_FindflairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        num_found = 0

        filename = f'{subreddit_name}_foundtext-_regexcss_{timestr}.csv'
        backup_file_path  = os.path.join(backup_directory, filename)

        with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
            fieldnames = ['user', 'flair_text', 'flair_css_class']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

            writer.writeheader()

            bar = alive_it(subreddit.flair(limit=None), title=f'Searching for Regex CSS Flair "{find_css_flair_regex}"', theme='smooth')

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"Searching for Regex CSS Flair: {find_css_flair_regex}\n")

                for flair in bar:
                    isMatch = re.search(find_css_flair_regex, str(flair['flair_css_class']))

                    if isMatch:
                        user = flair['user'].name
                        original_flair = flair['flair_text'] or ""
                        original_cssflair = flair['flair_css_class'] or ""

                        writer.writerow({'user': user, 'flair_text': original_flair, 'flair_css_class': original_cssflair})

                        num_found += 1

                        print(f"{user:<25s} {'Text Flair: ' + original_flair:<35s} {'CSS Flair: ' + original_cssflair:<30s}")
                        f.write(f"{user} Found Text Flair: {original_flair}  and CSS Flair: {original_cssflair}\n")

                print()
                print(f"{num_found} flairs have been found in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been found in {subreddit_name}.\n\n")


@reddit_error_handler
def find_flair_text_css_regex(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_text_flair_regex = input("What (Regex) Text Flair do you want to search? (leave blank to return everything) ")
    find_css_flair_regex = input("What (Regex) CSS Flair do you want to search? (leave blank to return everything) ")
    print()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_FindFlairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"Searching for Text Flair: {find_text_flair_regex} AND CSS Flair: {find_css_flair_regex}\n")

            num_found = 0
            line_count = 0

            backupcsvfile = f"{subreddit_name}_backupflair-{timestr}.csv"
            backup_file_path = os.path.join(backup_directory, backupcsvfile)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title=f'Counting and Backing Up from {subreddit_name}...', theme='smooth')

                for flair in bar:

                    if find_text_flair_regex and find_css_flair_regex:
                        isMatch = re.search(find_text_flair_regex, str(flair['flair_text'])) and re.search(find_css_flair_regex, str(flair['flair_css_class']))

                        if isMatch:
                            user = flair['user'].name
                            original_flair = flair['flair_text'] or ""
                            original_cssflair = flair['flair_css_class'] or ""

                            writer.writerow({'user': user, 'flair_text': original_flair, 'flair_css_class': original_cssflair})

                            num_found += 1

                            print(f"{user:<25s} {'Text Flair: ' + original_flair:<35s} {'CSS Flair: ' + original_cssflair:<30s}")
                            f.write(f"{user} Found Text Flair: {original_flair}  and CSS Flair: {original_cssflair}\n")


                print()
                print(f"{num_found} flairs have been found in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been found in {subreddit_name}.\n\n")





#############################################################################################
#############################################################################################
# Replace User Flair Menu
def replace_flair_menu(subreddit_string):
    replace_flair_actions = {
        '1': lambda: replace_flair_text(subreddit_string),
        '2': lambda: replace_flair_css(subreddit_string),
        '3': lambda: replace_flair_text_css(subreddit_string),
        '4': lambda: replace_flair_text_regex(subreddit_string),
        '5': lambda: replace_flair_css_regex(subreddit_string),
        '6': lambda: replace_flair_text_css_with_placeholders(subreddit_string),
        '7': lambda: set_flair_text_from_csv(subreddit_string),
        '8': lambda: set_flair_css_from_csv(subreddit_string)
    }

    replace_flair_options = [
        "Text",
        "CSS",
        "Text and CSS",
        "Text (Regex)",
        "CSS (Regex)",
        "Text (Regex) and CSS (Regex)",
        "Set Text using CSV User List",
        "Set CSS using CSV User List"
    ]

    replace_flair_menu_str = generate_menu("Replace Flair: ", replace_flair_options, "Go back")

    while True:
        print(separation)
        print(replace_flair_menu_str)
        flair_action = input("What do you want to replace?: ")

        if flair_action in replace_flair_actions:
            replace_flair_actions[flair_action]()
        elif flair_action == '0':
            break
        else:
            print(pickvalidoption)


# Replace Functions
@reddit_error_handler
def replace_flair_text(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_text_flair = input("What Text Flair do you want to search? ")
    replace_text_flair = input(f"What do you wish to replace '{find_text_flair}' with? ")
    print()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_ReplaceFlairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"Searching for Text Flair: {find_text_flair}\n")

            num_found = 0
            line_count = 0

            backupcsvfile = f"{subreddit_name}_backupflair-{timestr}.csv"
            backup_file_path  = os.path.join(backup_directory, backupcsvfile)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title=f'Counting and Backing Up from {subreddit_name}...', theme='smooth')

                for flair in bar:
                    flair_text = flair['flair_text']

                    if flair_text == find_text_flair:
                        user = flair['user'].name
                        writer.writerow({'user': user, 'flair_text': flair_text or "", 'flair_css_class': flair['flair_css_class'] or ""})
                        line_count += 1

                print(f"\nBacked Up {line_count} to {backup_file_path}.\n")

            time.sleep(1)

            with open(backup_file_path, mode='r', encoding='utf-8') as csv_file2:
                csv_reader = csv.DictReader(csv_file2)

                bar = alive_it(csv_reader, total=line_count, dual_line=True, title='Replacing...', theme='smooth')

                for row in bar:
                    user = row['user']
                    original_css_flair = row['flair_css_class'] or ""

                    bar.text = f'Replacing {user}\'s Text Flair: "{find_text_flair}" with "{replace_text_flair}"'

                    subreddit.flair.set(user, text=replace_text_flair, css_class=original_css_flair)
                    num_found += 1

                print()
                print(f"{num_found} flairs have been replaced in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been replaced in {subreddit_name}.\n\n")



@reddit_error_handler
def replace_flair_css(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_css_flair = input("What CSS Flair do you want to search? ")
    replace_css_flair = input(f"What do you wish to replace '{find_css_flair}' with? ")
    print()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_ReplaceFlairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"Searching for CSS Flair: {find_css_flair}\n")

            num_found = 0
            line_count = 0

            backupcsvfile = f"{subreddit_name}_backupflair-{timestr}.csv"
            backup_file_path  = os.path.join(backup_directory, backupcsvfile)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title=f'Counting and Backing Up from {subreddit_name}...', theme='smooth')

                for flair in bar:
                    flair_css_class = flair['flair_css_class']

                    if flair_css_class == find_css_flair:
                        user = flair['user'].name
                        writer.writerow({'user': user, 'flair_text': flair['flair_text'] or "", 'flair_css_class': flair_css_class or ""})
                        line_count += 1

                print(f"\nBacked Up {line_count} to {backup_file_path}.\n")

            time.sleep(1)

            with open(backup_file_path, mode='r', encoding='utf-8') as csv_file2:
                csv_reader = csv.DictReader(csv_file2)

                bar = alive_it(csv_reader, total=line_count, dual_line=True, title='Replacing...', theme='smooth')

                for row in bar:
                    user = row['user']
                    original_flair = row['flair_text'] or ""

                    bar.text = f'Replacing {user}\'s CSS Flair: "{find_css_flair}" with "{replace_css_flair}"'

                    subreddit.flair.set(user, text=original_flair, css_class=replace_css_flair)
                    num_found += 1

                print()
                print(f"{num_found} flairs have been replaced in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been replaced in {subreddit_name}.\n\n")



@reddit_error_handler
def replace_flair_text_css(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_text_flair = input("What Text Flair do you want to search? ")
    replace_text_flair = input(f"What do you wish to replace '{find_text_flair}' with? (leave blank to keep the same) ")
    find_css_flair = input("What CSS Flair do you want to search? ")
    replace_css_flair = input(f"What do you wish to replace '{find_css_flair}' with? (leave blank to keep the same) ")
    print()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_ReplaceFlairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"Searching for Text Flair: {find_text_flair} AND CSS Flair: {find_css_flair}\n")

            num_found = 0
            line_count = 0

            backupcsvfile = f"{subreddit_name}_backupflair-{timestr}.csv"
            backup_file_path  = os.path.join(backup_directory, backupcsvfile)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title=f'Counting and Backing Up from {subreddit_name}...', theme='smooth')

                for flair in bar:
                    flair_text = flair['flair_text']
                    flair_css_class = flair['flair_css_class']

                    if flair_text == find_text_flair and flair_css_class == find_css_flair:
                        user = flair['user'].name
                        writer.writerow({'user': user, 'flair_text': flair_text or "", 'flair_css_class': flair_css_class or ""})
                        line_count += 1

                print(f"\nBacked Up {line_count} to {backup_file_path}.\n")

            time.sleep(1)

            with open(backup_file_path, mode='r', encoding='utf-8') as csv_file2:
                csv_reader = csv.DictReader(csv_file2)

                bar = alive_it(csv_reader, total=line_count, dual_line=True, title='Replacing...', theme='smooth')

                for row in bar:
                    user = row['user']
                    original_flair = row['flair_text'] or ""
                    original_cssflair = row['flair_css_class'] or ""

                    update_flair = replace_text_flair or original_flair
                    update_cssflair = replace_css_flair or original_cssflair

                    bar.text = f'Replacing {user}\'s Text Flair: "{original_flair}" with "{update_flair}" and CSS Flair: "{original_cssflair}" with "{update_cssflair}"'

                    subreddit.flair.set(user, text=update_flair, css_class=update_cssflair)
                    num_found += 1

                print()
                print(f"{num_found} flairs have been replaced in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been replaced in {subreddit_name}.\n\n")



@reddit_error_handler
def replace_flair_text_regex(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_text_flair = input("What (Regex) Text Flair do you want to search? ")
    replace_text_flair = input(f"What do you wish to replace {find_text_flair} with? ")
    print()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_ReplaceFlairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            find_text_flair_regex = str(find_text_flair)
            f.write(f"Searching for Regex Text Flair: {find_text_flair_regex}\n")

            num_found = 0
            line_count = 0

            backupcsvfile = f"{subreddit_name}_backupflair-{timestr}.csv"
            backup_file_path  = os.path.join(backup_directory, backupcsvfile)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title=f'Counting and Backing Up from {subreddit_name}...', theme='smooth')

                for flair in bar:
                    flair_text = flair['flair_text'] or ""
                    isMatch = re.search(find_text_flair_regex, flair_text)

                    if isMatch:
                        user = flair['user'].name
                        flair_css_class = flair['flair_css_class'] or ""

                        writer.writerow({'user': user, 'flair_text': flair_text, 'flair_css_class': flair_css_class})
                        line_count += 1

                print(f"\nBacked Up {line_count} to {backup_file_path}.\n")

            time.sleep(1)

            with open(backup_file_path, mode='r', encoding='utf-8') as csv_file2:
                csv_reader = csv.DictReader(csv_file2)

                bar = alive_it(csv_reader, total=line_count, dual_line=True, title='Replacing...', theme='smooth')

                for row in bar:
                    user = row['user']
                    flair_text = row['flair_text'] or ""
                    flair_css_class = row['flair_css_class'] or ""

                    bar.text = f'Replacing {user}\'s Text Flair "{flair_text}" with "{replace_text_flair}"'

                    subreddit.flair.set(user, text=replace_text_flair, css_class=flair_css_class)
                    num_found += 1
                    f.write(str(user) + " Found Text Flair: " + str(flair_text) + " and replaced with: " + str(replace_text_flair) + "\n")

                print()
                print(f"{num_found} flairs have been replaced in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been replaced in {subreddit_name}.\n\n")



@reddit_error_handler
def replace_flair_css_regex(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_css_flair = input("What (Regex) CSS Flair do you want to search? ")
    replace_css_flair = input(f"What do you wish to replace {find_css_flair} with? ")

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_ReplaceFlairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:

            print()

            find_css_flair_regex = str(find_css_flair)
            f.write(f"Searching for Regex CSS Flair: {find_css_flair_regex}\n")

            num_found = 0
            line_count = 0

            backupcsvfile = f"{subreddit_name}_backupflair-{timestr}.csv"
            backup_file_path  = os.path.join(backup_directory, backupcsvfile)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title=f'Counting and Backing Up from {subreddit_name}...', theme='smooth')

                for flair in bar:
                    flair_css_class = flair['flair_css_class'] or ""
                    isMatch = re.search(str(find_css_flair_regex), flair_css_class)

                    if isMatch:
                        user = flair['user'].name
                        flair_text = flair['flair_text'] or ""

                        writer.writerow({'user': user, 'flair_text': flair_text, 'flair_css_class': flair_css_class})
                        line_count += 1

                print(f"\nBacked Up {line_count} to {backup_file_path}.\n")

            time.sleep(1)

            with open(backup_file_path, mode='r', encoding='utf-8') as csv_file2:
                csv_reader = csv.DictReader(csv_file2)

                bar = alive_it(csv_reader, total=line_count, dual_line=True, title='Replacing...', theme='smooth')

                for row in bar:
                    user = row['user']
                    flair_text = row['flair_text'] or ""
                    flair_css_class = row['flair_css_class'] or ""

                    bar.text = f'Replacing {user}\'s CSS Flair: "{flair_css_class}" with "{replace_css_flair}"'

                    subreddit.flair.set(user, text=flair_text, css_class=replace_css_flair)
                    num_found += 1
                    f.write(str(user) + " Found CSS Flair: " + str(flair_css_class) + " and replaced with: " + str(replace_css_flair) + "\n")

                print()
                print(f"{num_found} flairs have been replaced in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been replaced in {subreddit_name}.\n\n")



@reddit_error_handler
def replace_flair_text_css_with_placeholders(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    find_text_flair = input("What (Regex) Text Flair do you want to search? (leave blank to return everything) ")
    replace_text_flair = input("What do you wish to replace '" + str(find_text_flair) + "' with? (use {{text}} as a placeholder for the existing text, or leave blank to leave as is) ")
    find_css_flair = input("What (Regex) CSS Flair do you want to search? (leave blank to return everything) ")
    replace_css_flair = input("What do you wish to replace '" + str(find_css_flair) + "' with? (use {{css}} as a placeholder for the existing CSS class, or leave blank to leave as is) ")
    print()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_ReplaceFlairLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"Searching for Text Flair: {find_text_flair} AND CSS Flair: {find_css_flair}\n")

            num_found = 0
            line_count = 0

            backupcsvfile = f"{subreddit_name}_backupflair-{timestr}.csv"
            backup_file_path = os.path.join(backup_directory, backupcsvfile)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title=f'Counting and Backing Up from {subreddit_name}...', theme='smooth')

                for flair in bar:
                    flair_text = flair['flair_text'] or ""
                    flair_css_class = flair['flair_css_class'] or ""

                    if find_text_flair and find_css_flair:
                        isMatch = re.search(str(find_text_flair), flair_text) and re.search(str(find_css_flair), flair_css_class)
                    elif find_text_flair:
                        isMatch = re.search(str(find_text_flair), flair_text)
                    elif find_css_flair:
                        isMatch = re.search(str(find_css_flair), flair_css_class)
                    else:
                        isMatch = True

                    if isMatch:
                        user = flair['user'].name
                        writer.writerow({'user': user, 'flair_text': flair_text, 'flair_css_class': flair_css_class})
                        line_count += 1

                print(f"\nBacked Up {line_count} to {backup_file_path}.\n")

            time.sleep(1)

            with open(backup_file_path, mode='r', encoding='utf-8') as csv_file2:
                csv_reader = csv.DictReader(csv_file2)

                bar = alive_it(csv_reader, total=line_count, dual_line=True, title='Replacing...', theme='smooth')

                for row in bar:
                    user = row['user']
                    original_flair = row['flair_text'] or ""
                    original_cssflair = row['flair_css_class'] or ""

                    # Replace the placeholders with the original values
                    update_flair = replace_text_flair.replace("{{text}}", original_flair) if replace_text_flair else original_flair
                    update_cssflair = replace_css_flair.replace("{{css}}", original_cssflair) if replace_css_flair else original_cssflair

                    bar.text = f'Replacing {user}\'s Text Flair: "{original_flair}" with "{update_flair}" and CSS Flair: "{original_cssflair}" with "{update_cssflair}"'

                    while True:
                        try:
                            subreddit.flair.set(user, text=update_flair, css_class=update_cssflair)
                            num_found += 1
                            break
                        except TooManyRequests as e:
                            retry_after = int(e.response.headers.get('Retry-After', 10))
                            print(f"\nRate limited. Retrying in {retry_after} seconds...")
                            time.sleep(retry_after)

                print()
                print(f"{num_found} flairs have been replaced in {subreddit_name}.")
                f.write(f"\n{num_found} flairs have been replaced in {subreddit_name}.\n\n")



@reddit_error_handler
def set_flair_text_from_csv(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    filename = input("CSV filename containing user column? ")
    text_flair = input("Text flair to set for all users in the CSV file? ")

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_SetFlairLog_-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            num_found = 0
            line_count = 0

            with open(filename, 'r') as fp:
                total_lines = len(fp.readlines()) - 1  # Subtract header line
                print(f"Total Number of flair to set: {total_lines}\n")

            with open(filename, mode='r') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                bar = alive_it(csv_reader, total=total_lines, dual_line=True, title='Setting...', theme='smooth')

                for row in bar:
                    if line_count == 0:
                        line_count += 1

                    user = row["user"]
                    bar.text = f'Setting {user}\'s Text Flair to "{text_flair}"'

                    # Get the current flair data of the user
                    current_flair = list(subreddit.flair(r.redditor(user)))[0]

                    # Set the flair text from the input while keeping the existing CSS flair intact
                    subreddit.flair.set(user, text=text_flair, css_class=current_flair["flair_css_class"])

                    num_found += 1
                    log_line = f'{user} Set Text Flair: {text_flair}\n'
                    f.write(log_line)

                print(f'\n{num_found} flairs have been set to {text_flair} in {subreddit_name}.')
                f.write(f'\n{num_found} flairs have been set to {text_flair} in {subreddit_name}.\n\n')



@reddit_error_handler
def set_flair_css_from_csv(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    filename = input("CSV filename containing user column? ")
    css_flair = input("CSS flair to set for all users in the CSV file? ")

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_SetFlairLog_-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            num_found = 0
            line_count = 0

            with open(filename, 'r') as fp:
                total_lines = len(fp.readlines()) - 1  # Subtract header line
                print(f"Total Number of flair to set: {total_lines}\n")

            with open(filename, mode='r') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                bar = alive_it(csv_reader, total=total_lines, dual_line=True, title='Setting...', theme='smooth')

                for row in bar:
                    if line_count == 0:
                        line_count += 1

                    user = row["user"]
                    bar.text = f'Setting {user}\'s CSS Flair to "{css_flair}"'

                    # Get the current flair data of the user
                    current_flair = list(subreddit.flair(r.redditor(user)))[0]

                    # Set the flair CSS class from the input while keeping the existing flair text intact
                    subreddit.flair.set(user, text=current_flair["flair_text"], css_class=css_flair)

                    num_found += 1
                    log_line = f'{user} Set CSS Flair: {css_flair}\n'
                    f.write(log_line)

                print(f'\n{num_found} flairs have been set to {css_flair} in {subreddit_name}.')
                f.write(f'\n{num_found} flairs have been set to {css_flair} in {subreddit_name}.\n\n')



@reddit_error_handler
def shadowban_flair_css(author, subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_ShadowBanLog-{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            replace_css_flair = "shadow"
            print()

            # Fetch author's flair
            author_flair = next(subreddit.flair(redditor=author))

            # Back up author's flair
            backupcsvfile = f"{subreddit_name}_{author}_backupflair-{timestr}.csv"
            backup_file_path  = os.path.join(backup_directory, backupcsvfile)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()

                writer.writerow({'user': author, 'flair_text': author_flair['flair_text'] or "", 'flair_css_class': author_flair['flair_css_class'] or ""})

            print(f"\nBacked Up {author}'s Flair to {backup_file_path}.\n")

            time.sleep(1)

            original_flair = author_flair['flair_text'] or ""

            subreddit.flair.set(author, text=original_flair, css_class=replace_css_flair)

            print()
            print(f"{author} has been Shadowbanned with the shadow css flair in {subreddit_name}.")
            f.write(f"\n{author} has been Shadowbanned with the shadow css flair in {subreddit_name}.\n\n")






#############################################################################################
#############################################################################################
# Backup User Flair Menu
def backup_flair_menu(subreddit_string):
    backup_flair_actions = {
        '1': lambda: backup_flair_text(subreddit_string),
        '2': lambda: backup_flair_css(subreddit_string),
        '3': lambda: backup_flair_text_css(subreddit_string),
        '4': lambda: backup_flair_text_regex(subreddit_string),
        '5': lambda: backup_flair_css_regex(subreddit_string),
        '6': lambda: backup_flair_all(subreddit_string),
    }

    backup_flair_options = [
        "Text",
        "CSS",
        "Text and CSS",
        "Text (Regex)",
        "CSS (Regex)",
        "All",
    ]

    backup_flair_menu_str = generate_menu("Backup Flair:", backup_flair_options, "Go back")

    while True:
        print(separation)
        print(backup_flair_menu_str)
        flair_action = input("What do you want to backup?: ")

        if flair_action in backup_flair_actions:
            backup_flair_actions[flair_action]()
        elif flair_action == '0':
            break
        else:
            print(pickvalidoption)


# Backup Functions
@reddit_error_handler
def backup_flair_text(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_BackupFlairLog_{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            find_text_flair = input("What Text Flair do you want to backup? ")
            print()

            num_found = 0

            filename = f'{subreddit_name}_BackupFlairText_{find_text_flair}_{timestr}.csv'
            backup_file_path  = os.path.join(backup_directory, filename)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title='Backing up...', theme='smooth')

                for flair in bar:
                    flair_text = flair['flair_text'] or ""
                    flair_css_class = flair['flair_css_class'] or ""

                    if flair_text == find_text_flair:
                        user = flair['user'].name

                        writer.writerow({'user': user, 'flair_text': flair_text, 'flair_css_class': flair_css_class})
                        num_found += 1

                print(f'\n{num_found} flairs have been backed up from {subreddit_name}.')
                f.write(f'\n{num_found} flairs have been backed up from {subreddit_name}.\n\n')


@reddit_error_handler
def backup_flair_css(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_BackupFlairLog_{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            find_css_flair = input("What CSS Flair do you want to backup? ")
            print()

            num_found = 0

            filename = f'{subreddit_name}_BackupFlairCSS_{find_css_flair}_{timestr}.csv'
            backup_file_path  = os.path.join(backup_directory, filename)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:

                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title='Backing up...', theme='smooth')

                for flair in bar:
                    flair_text = flair['flair_text'] or ""
                    flair_css_class = flair['flair_css_class'] or ""

                    if flair_css_class == find_css_flair:
                        user = flair['user'].name

                        writer.writerow({'user': user, 'flair_text': flair_text, 'flair_css_class': flair_css_class})

                        num_found += 1

                print(f'\n{num_found} flairs have been backed up from {subreddit_name}.')
                f.write(f'\n{num_found} flairs have been backed up from {subreddit_name}.\n\n')


@reddit_error_handler
def backup_flair_text_css(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_BackupFlairLog_{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            find_text_flair = input("What Text Flair do you want to backup? ")
            find_css_flair = input("What CSS Flair do you want to backup? ")
            print()

            num_found = 0

            filename = f'{subreddit_name}_BackupFlairBoth_{find_css_flair}_{find_css_flair}_{timestr}.csv'
            backup_file_path  = os.path.join(backup_directory, filename)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title='Backing up...', theme='smooth')

                for flair in bar:
                    flair_text = flair['flair_text'] or ""
                    flair_css_class = flair['flair_css_class'] or ""

                    if flair_text == find_text_flair and flair_css_class == find_css_flair:
                        user = flair['user'].name

                        writer.writerow({'user': user, 'flair_text': flair_text, 'flair_css_class': flair_css_class})
                        num_found += 1

                print(f'\n{num_found} flairs have been backed up from {subreddit_name}.')
                f.write(f'\n{num_found} flairs have been backed up from {subreddit_name}.\n\n')


@reddit_error_handler
def backup_flair_text_regex(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_BackupFlairLog_{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            find_text_flair = input("What (Regex) Text Flair do you want to find? ")
            print()

            find_text_flair_regex = re.compile(find_text_flair)
            f.write(f"Searching for Regex Text Flair: {find_text_flair}\n")

            num_found = 0

            filename = f'{subreddit_name}_BackupFlairText_regextext_{timestr}.csv'
            backup_file_path  = os.path.join(backup_directory, filename)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title='Backing up...', theme='smooth')

                for flair in bar:
                    flair_text = flair['flair_text'] or ""

                    if find_text_flair_regex.search(flair_text):
                        user = flair['user'].name
                        css_class = flair['flair_css_class'] or ""

                        writer.writerow({'user': user, 'flair_text': flair_text, 'flair_css_class': css_class})
                        num_found += 1

                print(f'\n{num_found} flairs have been backed up from {subreddit_name}.')
                f.write(f'\n{num_found} flairs have been backed up from {subreddit_name}.\n\n')


@reddit_error_handler
def backup_flair_css_regex(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_BackupFlairLog_{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            find_css_flair = input("What (Regex) CSS Flair do you want to find? ")
            print()

            find_css_flair_regex = re.compile(find_css_flair)
            f.write(f"Searching for Regex CSS Flair: {find_css_flair}\n")

            num_found = 0

            filename = f'{subreddit_name}_BackupFlairCSS_regexcss_{timestr}.csv'
            backup_file_path  = os.path.join(backup_directory, filename)

            with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                fieldnames = ['user', 'flair_text', 'flair_css_class']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

                writer.writeheader()

                bar = alive_it(subreddit.flair(limit=None), title='Backing up...', theme='smooth')

                for flair in bar:
                    css_class = flair['flair_css_class'] or ""

                    if find_css_flair_regex.search(css_class):
                        user = flair['user'].name
                        flair_text = flair['flair_text'] or ""

                        writer.writerow({'user': user, 'flair_text': flair_text, 'flair_css_class': css_class})
                        num_found += 1

                print(f'\n{num_found} flairs have been backed up from {subreddit_name}.')
                f.write(f'\n{num_found} flairs have been backed up from {subreddit_name}.\n\n')


@reddit_error_handler
def backup_flair_all(subreddit_string):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddits = subreddit_string.split()

    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)

        log_file_bak = f"{subreddit_name}_BackupFlairLog_{timestr}.log"
        log_file = os.path.join(backup_directory, log_file_bak )

        with open(log_file, "a", encoding="utf-8") as f:
            find_all = input("This will back up all users, are you sure? (y/n) ")
            print()

            if find_all.lower() == 'y':
                for subreddit_name in subreddits:
                    num_found = 0
                    subreddit = r.subreddit(subreddit_name)

                    filename = f'{subreddit_name}_BackupFlair_ALL_{timestr}.csv'
                    backup_file_path  = os.path.join(backup_directory, filename)

                    with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
                        fieldnames = ['subreddit', 'user', 'flair_text', 'flair_css_class']
                        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

                        writer.writeheader()

                        bar = alive_it(subreddit.flair(limit=None), title=f'Backing up r/{subreddit_name}...', theme='smooth')

                        for flair in bar:
                            user = flair['user'].name
                            original_flair = flair['flair_text'] or ""
                            original_cssflair = flair['flair_css_class'] or ""

                            writer.writerow({'subreddit': subreddit_name, 'user': user, 'flair_text': original_flair, 'flair_css_class': original_cssflair})
                            num_found += 1

                    print(f'\n{num_found} flairs have been backed up from {subreddit_name}.')
                    f.write(f'\n{num_found} flairs have been backed up from {subreddit_name}.\n\n')






#############################################################################################
#############################################################################################
# Restore User Flair Menu
def restore_flair_menu(subreddit_string):
    restore_flair_actions = {
        '1': lambda: restore_flair_text_css(subreddit_string),
        '2': lambda: restore_flair_text(subreddit_string),
        '3': lambda: restore_flair_css(subreddit_string),
    }

    restore_flair_options = [
        "Text and CSS",
        "Text",
        "CSS",
    ]

    restore_flair_menu_str = generate_menu("Restore Flair: ", restore_flair_options, "Go back")

    while True:
        print(separation)
        print(restore_flair_menu_str)
        flair_action = input("What do you want to restore?: ")

        if flair_action in restore_flair_actions:
            restore_flair_actions[flair_action]()
        elif flair_action == '0':
            break
        else:
            print(pickvalidoption)


# Restore Functions
@reddit_error_handler
def restore_flair_text_css(subreddit_name):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddit = r.subreddit(subreddit_name)

    log_file_bak = f"{subreddit_name}_RestoreFlairLog_{timestr}.log"
    log_file = os.path.join(backup_directory, log_file_bak )

    with open(log_file, "a", encoding="utf-8") as f:
        restore_filename = input("Filename to restore? ")

        restore_action = input(f"Do you have a BACKUP and are you sure you want to restore both Text_Flair and CSS_Flair from {restore_filename} to {subreddit_name}? (y/n): ")
        print()

        if restore_action.lower() == 'y':
            num_found = 0
            line_count = 0

            with open(restore_filename, 'r') as fp:
                total_lines = len(fp.readlines()) - 1  # Subtract header line
                print(f"Total Number of flair to restore: {total_lines}\n")

            with open(restore_filename, mode='r') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                bar = alive_it(csv_reader, total=total_lines, dual_line=True, title='Restoring...', theme='smooth')

                for row in bar:
                    if line_count == 0:
                        line_count += 1

                    bar.text = f'Restoring {row["user"]}\'s Text Flair to "{row["flair_text"]}" and CSS Flair to "{row["flair_css_class"]}"'

                    try:
                        subreddit.flair.set(row["user"], text=row["flair_text"], css_class=row["flair_css_class"])
                        num_found += 1
                        log_line = f'{row["user"]} Restored Text Flair: {row["flair_text"]} and CSS Flair: {row["flair_css_class"]}\n'
                        f.write(log_line)
                    except praw.exceptions.RedditAPIException as e:
                        # If there's an exception, continue to the next user
                        print(f"Skipping {row['user']} due to error: {e}")
                        f.write(f"Skipping {row['user']} due to error: {e}\n")

                print(f'\n{num_found} flairs have been restored to {subreddit_name}.')
                f.write(f'\n{num_found} flairs have been restored to {subreddit_name}.\n\n')


@reddit_error_handler
def restore_flair_text(subreddit_name):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddit = r.subreddit(subreddit_name)

    log_file_bak = f"{subreddit_name}_RestoreFlairLog_{timestr}.log"
    log_file = os.path.join(backup_directory, log_file_bak )

    with open(log_file, "a", encoding="utf-8") as f:
        restore_filename = input("Filename to restore? ")

        restore_action = input(f"Do you have a BACKUP and are you sure you want to restore Text_Flair from {restore_filename} to {subreddit_name}? (y/n): ")
        print()

        if restore_action.lower() == 'y':
            num_found = 0
            line_count = 0

            with open(restore_filename, 'r') as fp:
                total_lines = len(fp.readlines()) - 1  # Subtract header line
                print(f"Total Number of flair to restore: {total_lines}\n")

            with open(restore_filename, mode='r') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                bar = alive_it(csv_reader, total=total_lines, dual_line=True, title='Restoring...', theme='smooth')

                for row in bar:
                    if line_count == 0:
                        line_count += 1

                    user = row["user"]
                    bar.text = f'Restoring {user}\'s Text Flair to "{row["flair_text"]}"'

                    # Get the current flair data of the user
                    current_flair = list(subreddit.flair(r.redditor(user)))[0]

                    # Update the flair text from the CSV file while keeping the existing CSS flair intact
                    subreddit.flair.set(user, text=row["flair_text"], css_class=current_flair['flair_css_class'])

                    num_found += 1
                    log_line = f'{user} Restored Text Flair: {row["flair_text"]}\n'
                    f.write(log_line)

                print(f'\n{num_found} flairs have been restored to {subreddit_name}.')
                f.write(f'\n{num_found} flairs have been restored to {subreddit_name}.\n\n')


@reddit_error_handler
def restore_flair_css(subreddit_name):
    timestr = time.strftime("%Y%m%d-%H%M%S")
    subreddit = r.subreddit(subreddit_name)

    log_file_bak = f"{subreddit_name}_RestoreFlairLog_{timestr}.log"
    log_file = os.path.join(backup_directory, log_file_bak )

    with open(log_file, "a", encoding="utf-8") as f:
        restore_filename = input("Filename to restore? ")

        restore_action = input(f"Do you have a BACKUP and are you sure you want to restore CSS_Flair from {restore_filename} to {subreddit_name}? (y/n): ")
        print()

        if restore_action.lower() == 'y':
            num_found = 0
            line_count = 0

            with open(restore_filename, 'r') as fp:
                total_lines = len(fp.readlines()) - 1  # Subtract header line
                print(f"Total Number of flair to restore: {total_lines}\n")

            with open(restore_filename, mode='r') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                bar = alive_it(csv_reader, total=total_lines, dual_line=True, title='Restoring...', theme='smooth')

                for row in bar:
                    if line_count == 0:
                        line_count += 1

                    user = row["user"]
                    bar.text = f'Restoring {user}\'s CSS Flair to "{row["flair_css_class"]}"'

                    # Get the current flair data of the user
                    current_flair = list(subreddit.flair(r.redditor(user)))[0]

                    # Update the flair text from the CSV file while keeping the existing CSS flair intact
                    subreddit.flair.set(user, text=current_flair["flair_text"], css_class=row['flair_css_class'])

                    num_found += 1
                    log_line = f'{user} Restored CSS Flair: {row["flair_css_class"]}\n'
                    f.write(log_line)

                print(f'\n{num_found} flairs have been restored to {subreddit_name}.')
                f.write(f'\n{num_found} flairs have been restored to {subreddit_name}.\n\n')





#############################################################################################
#############################################################################################
# Post Flair Management
def post_flair_management_menu():
    post_flair_management_actions = {
        '1': lambda: list_post_flairs(subreddit_string),
        '2': lambda: create_post_flair(subreddit_string),
        '3': lambda: duplicate_post_flair(subreddit_string),
        '4': lambda: edit_post_flair(subreddit_string),
        '5': lambda: delete_post_flair(subreddit_string),
    }

    post_flair_management_options = [
        "List Post Flairs",
        "Create New Post Flair",
        "Duplicate Post Flair",
        "Edit Post Flair",
        "Delete Post Flair",
    ]

    post_flair_management_menu_str = generate_menu("Post Flair Management:", post_flair_management_options, "Go back")

    while True:
        print(separation)
        print(post_flair_management_menu_str)
        post_flair_action = input("What do you want to do?: ")

        if post_flair_action in post_flair_management_actions:
            subreddit_string = subreddit_selection(moderator_name, 'single')
            post_flair_management_actions[post_flair_action]()
        elif post_flair_action == '0':
            break
        else:
            print(pickvalidoption)




@reddit_error_handler
def list_post_flairs(subreddit_string):
    try:
        with CancelOperation():
            subreddit = r.subreddit(subreddit_string)
            post_flairs = subreddit.flair.link_templates

            print(f"\nPost Flairs for r/{subreddit_string}:")
            for flair in post_flairs:
                print(f"ID: {flair['id']}")
                print(f"Text: {flair['text']}")
                print(f"CSS Class: {flair['css_class']}")
                print(f"Mod Only: {flair['mod_only']}")
                print(f"Background Color: {flair['background_color']}")
                print(f"Text Color: {flair['text_color']}")
                print("---")
    except OperationCancelled:
        print("Flair duplication cancelled.")


@reddit_error_handler
def create_post_flair(subreddit_string):
    try:
        with CancelOperation():
            subreddit = r.subreddit(subreddit_string)

            text = input("Enter post flair text: ")
            css_class = input("Enter CSS class (optional): ")
            mod_only = input("Is this post flair mod only? (y/n): ").lower() == 'y'

            while True:
                background_color = process_color_input(input("Enter background color (e.g., FF0000 or #FF0000): "))
                if background_color:
                    break
                print("Invalid color format. Please enter a valid 3 or 6 digit hex code.")

            text_color = input("Enter text color (light/dark): ")

            subreddit.flair.link_templates.add(
                text=text,
                css_class=css_class,
                mod_only=mod_only,
                background_color=background_color,
                text_color=text_color
            )
            print(f"\nPost flair created under {subreddit} successfully!")
            print(f"Background color set to: {background_color}")

            # Fetch the newly created flair
            new_flairs = list(subreddit.flair.link_templates)
            new_flair = next((flair for flair in new_flairs if flair['text'] == text), None)

            if new_flair:
                print(f"\nNew flair UUID: {new_flair['id']}\n")
            else:
                print("\nUnable to retrieve the new flair UUID.\n")
    except OperationCancelled:
        print("Flair duplication cancelled.")


@reddit_error_handler
def duplicate_post_flair(subreddit_string):
    try:
        with CancelOperation():
            subreddit = r.subreddit(subreddit_string)
            post_flairs = list(subreddit.flair.link_templates)

            print("Select a post flair to duplicate:")
            for i, flair in enumerate(post_flairs):
                print(f"{i+1}. {flair['text']}")

            choice = int(input("Enter the number of the post flair to duplicate: ")) - 1
            original_flair = post_flairs[choice]

            new_text = input("Enter new post flair text: ")

            subreddit.flair.link_templates.add(
                text=new_text,
                css_class=original_flair['css_class'],
                mod_only=original_flair['mod_only'],
                background_color=original_flair['background_color'],
                text_color=original_flair['text_color']
            )
            print("\nPost flair duplicated successfully!")

            # Fetch the newly created flair
            new_flairs = list(subreddit.flair.link_templates)
            new_flair = next((flair for flair in new_flairs if flair['text'] == new_text), None)

            if new_flair:
                print(f"\nNew flair UUID: {new_flair['id']}\n")
            else:
                print("\nUnable to retrieve the new flair UUID.\n")

    except OperationCancelled:
        print("Flair duplication cancelled.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")


@reddit_error_handler
def edit_post_flair(subreddit_string):
    try:
        with CancelOperation():
            subreddit = r.subreddit(subreddit_string)
            post_flairs = list(subreddit.flair.link_templates)

            print("Select a post flair to edit:")
            for i, flair in enumerate(post_flairs):
                print(f"{i+1}. {flair['text']}")

            choice = int(input("Enter the number of the post flair to edit: ")) - 1
            flair_to_edit = post_flairs[choice]

            text = input(f"Enter new post flair text (current: {flair_to_edit['text']}): ") or flair_to_edit['text']
            css_class = input(f"Enter new CSS class (current: {flair_to_edit['css_class']}): ") or flair_to_edit['css_class']
            mod_only = input(f"Is this post flair mod only? (y/n) (current: {flair_to_edit['mod_only']}): ").lower() == 'y'

            while True:
                background_color = process_color_input(input(f"Enter new background color (current: {flair_to_edit['background_color']}): ") or flair_to_edit['background_color'])
                if background_color:
                    break
                print("Invalid color format. Please enter a valid 3 or 6 digit hex code.")

            text_color = input(f"Enter new text color (light/dark) (current: {flair_to_edit['text_color']}): ") or flair_to_edit['text_color']

            subreddit.flair.link_templates.update(
                flair_to_edit['id'],
                text=text,
                css_class=css_class,
                mod_only=mod_only,
                background_color=background_color,
                text_color=text_color
            )
            print(f"\nPost flair edited in {subreddit} successfully!")
            print(f"Background color set to: {background_color}")
    except OperationCancelled:
        print("Flair duplication cancelled.")


@reddit_error_handler
def delete_post_flair(subreddit_string):
    try:
        with CancelOperation():
            subreddit = r.subreddit(subreddit_string)
            post_flairs = list(subreddit.flair.link_templates)

            print("Select a post flair to delete:")
            for i, flair in enumerate(post_flairs):
                print(f"{i+1}. {flair['text']}")

            choice = int(input("Enter the number of the post flair to delete: ")) - 1
            flair_to_delete = post_flairs[choice]

            confirm = input(f"Are you sure you want to delete the post flair '{flair_to_delete['text']}'? (y/n): ").lower()
            if confirm == 'y':
                subreddit.flair.link_templates.delete(flair_to_delete['id'])
                print("Post flair deleted successfully!")
            else:
                print("Deletion cancelled.")
    except OperationCancelled:
        print("Flair duplication cancelled.")







#############################################################################################
#############################################################################################
# User Management
def user_management_menu():
    user_management_actions = {
        '1': lambda: backup_approved_users(subreddit_string),
        '2': lambda: restore_approved_users(subreddit_string),
        '3': lambda: wipe_approved_users(subreddit_string),
        '4': lambda: ban_users(subreddit_string),
        '5': lambda: unban_users(subreddit_string),
    }

    user_management_options = [
        "Backup Approved Users",
        "Restore Approved Users",
        "Wipe Approved Users",
        "Ban Users",
        "Unban Users",
    ]

    user_management_menu_str = generate_menu("User Management:", user_management_options, "Go back")

    while True:
        print(separation)
        print(user_management_menu_str)
        user_action = input("What do you want to do?: ")

        if user_action in user_management_actions:
            if user_action in ['1', '2', '3', '4', '5']:
                subreddit_string = subreddit_selection(moderator_name, 'multi')
            user_management_actions[user_action]()
        elif user_action == '0':
            break
        else:
            print(pickvalidoption)


@reddit_error_handler
def backup_approved_users(subreddit_string):
    subreddits = subreddit_string.split()
    timestr = time.strftime("%Y%m%d-%H%M%S")

    filename = f'Backup_Approved_Users_{timestr}.csv'
    backup_file_path  = os.path.join(backup_directory, filename)

    with open(backup_file_path, mode='w', newline='', encoding='utf-8', errors='ignore') as csv_file:
        fieldnames = ['subreddit', 'user']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        backedup_approved_users_count = 0

        #with alive_bar(len(subreddits), title='Backing up approved users') as bar:
        with alive_bar(title='Backing up approved users') as bar:
            for subreddit_name in subreddits:
                subreddit = r.subreddit(subreddit_name)
                for user in subreddit.contributor():
                    writer.writerow({'subreddit': subreddit_name, 'user': user.name})
                    backedup_approved_users_count += 1
                    bar()

    print(f"Backup of {backedup_approved_users_count} approved users completed. Saved to {backup_file_path}.")


@reddit_error_handler
def restore_approved_users(subreddit_string):
    subreddits = set(subreddit_string.split())

    backup_file = input("Enter the name of the CSV file of Approved Users to restore: ")

    # Count rows in the CSV file for the selected subreddits
    row_counts = {subreddit: 0 for subreddit in subreddits}
    with open(backup_file, mode='r', encoding='utf-8') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            if row['subreddit'] in subreddits:
                row_counts[row['subreddit']] += 1

    with open(backup_file, mode='r', encoding='utf-8') as csv_file:
        csv_reader = csv.DictReader(csv_file)

        restored_approved_user_count = 0

        for subreddit_name in subreddits:
            row_count = row_counts[subreddit_name]

            with alive_bar(row_count, title=f'Restoring approved users for r/{subreddit_name}') as bar:
                for row in csv_reader:
                    if row['subreddit'] == subreddit_name:
                        subreddit = r.subreddit(subreddit_name)
                        user = row['user']
                        subreddit.contributor.add(user)
                        restored_approved_user_count += 1
                        bar()
                csv_file.seek(0)  # Reset the CSV file pointer for the next iteration

    print(f"Restoration of {restored_approved_user_count} approved users completed.")


@reddit_error_handler
def wipe_approved_users(subreddit_string):
    subreddits = subreddit_string.split()

    # Count approved users in the subreddits
    user_count = 0
    for subreddit_name in subreddits:
        subreddit = r.subreddit(subreddit_name)
        user_count += len(list(subreddit.contributor()))

    wiped_approved_user_count = 0

    with alive_bar(user_count, title='Wiping approved users') as bar:
        for subreddit_name in subreddits:
            subreddit = r.subreddit(subreddit_name)
            for user in subreddit.contributor():
                subreddit.contributor.remove(user)
                wiped_approved_user_count += 1
                bar()

    print(f"Wiping of {wiped_approved_user_count} approved users completed.")


@reddit_error_handler
def ban_users(subreddit_string):
    subreddits = subreddit_string.split()

    ban_input = input("Enter the name of the CSV file containing users to ban, or a username: ")

    if ban_input.endswith('.csv'):  # It's a CSV file
        # Count rows in the CSV file
        with open(ban_input, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.reader(csv_file)
            row_count = sum(1 for row in csv_reader) - 1  # Subtract 1 for the header

        for subreddit_name in subreddits:
            subreddit = r.subreddit(subreddit_name)

            with open(ban_input, mode='r', encoding='utf-8-sig') as csv_file:
                csv_reader = csv.DictReader(csv_file)

                with alive_bar(row_count, title=f'Banning users in r/{subreddit_name}') as bar:
                    for row in csv_reader:
                        user = row['user']
                        ban_note = row['ban_note']
                        ban_pm = row['ban_pm']
                        subreddit.banned.add(user, ban_reason=ban_note, ban_message=ban_pm)
                        bar()

            print(f'Banning users completed in r/{subreddit_name}.')

    else:  # It's a username
        ban_note = input("Enter the ban note: ")
        ban_pm = input("Enter the ban PM: ")

        for subreddit_name in subreddits:
            subreddit = r.subreddit(subreddit_name)
            subreddit.banned.add(ban_input, ban_reason=ban_note, ban_message=ban_pm)

            print(f'Banned user {ban_input} from r/{subreddit_name}.')


@reddit_error_handler
def unban_users(subreddit_string):
    subreddits = subreddit_string.split()

    unban_input = input("Enter the name of the CSV file containing users to unban, or a username: ")

    if unban_input.endswith('.csv'):  # It's a CSV file
        # Count rows in the CSV file
        with open(unban_input, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.reader(csv_file)
            row_count = sum(1 for row in csv_reader) - 1  # Subtract 1 for the header

        for subreddit_name in subreddits:
            subreddit = r.subreddit(subreddit_name)

            with open(unban_input, mode='r', encoding='utf-8-sig') as csv_file:
                csv_reader = csv.DictReader(csv_file)

                with alive_bar(row_count, title=f'Unbanning users in r/{subreddit_name}') as bar:
                    for row in csv_reader:
                        user = row['user']
                        subreddit.banned.remove(user)
                        bar()

            print(f'Unbanning users completed in r/{subreddit_name}.')

    else:  # It's a username
        for subreddit_name in subreddits:
            subreddit = r.subreddit(subreddit_name)
            subreddit.banned.remove(unban_input)

            print(f'Unbanned user {unban_input} from r/{subreddit_name}.')



#############################################################################################
#############################################################################################

try:
    main_menu()

except KeyboardInterrupt:
    #print("\nKeyboard interrupt detected. Exiting...")
    sys.exit(0)
