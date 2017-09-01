# brayerpot: take THAT @britwuzhere
import logging
import sys
import shelve
from slackclient import SlackClient

try:
    from secret import *
except ImportError:
    logging.error("Could not read secret.py")
    sys.exit(1)

# Global variables
BOT_NAME = 'prayerbot'
BOT_ID = None
slack_client = SlackClient(SLACK_API_TOKEN)

def slack_call(api_name, **kwargs):
    global slack_client
    api_call = slack_client.api_call(api_name, **kwargs)
    if api_call.get("ok"):
        return api_call
    else:
        logging.warn("Could not complete api call %s: %s", api_name, api_call)
        raise RuntimeError("slack call %s failed"%(api_name))

def bot_id(force=False):
    """
    Find our bot id on this particular Slack, cached in global `BOT_ID`, will
    only search for it again if `force` is set to `True`.
    """
    global BOT_ID, BOT_NAME

    if BOT_ID is None or force:
        users = slack_call('users.list').get('members')
        for user in users:
            if 'name' in user and user.get('name') == BOT_NAME:
                BOT_ID = user.get('id')
                logging.info("Auto-discovered our BOT_ID as %s", BOT_ID)

        # If we completely failed to find ourselves, freak out
        if BOT_ID is None:
            logging.error("Could not find BOT_ID!  Wigging out!")
            raise RuntimeError("Could not find BOT_ID")

    return BOT_ID

def is_im_to_me(payload):
    """
    Given a payload, look at the channel and see if it's in a DM to me.
    """
    im_list = slack_call('im.list')['ims']
    return any(payload['channel'] == im['id'] for im in im_list)


class DataBase:
    def __init__(self, path):
        self.db = shelve.open(path)
        logging.info("Loaded databse which knows about %d prayer groups"%(len(self.db.keys())))

    def close(self):
        self.db.close()

    def add_user_to_group(self, user, group):
        """
        Add a user to a group, returning the group afterward
        """
        group = group.lower()
        if not group in self.db:
            self.db[group] = [user]
        else:
            if not user in self.db[group]:
                self.db[group] = self.db[group] + [user]
        return self.db[group]

    def remove_user_from_group(self, user, group):
        """
        Remove a user from a group, returning the group afterward. If the group
        did not exist, or the user was the last one in that group, delete the
        group completely.
        """
        group = group.lower()
        if not group in self.db:
            return []
        
        if not user in self.db[group]:
            return self.db[group]
        
        d = self.db[group]
        d.remove(user)

        # If that group is empty now, delete it
        if not d:
            del self.db[group]
            return []

        self.db[group] = d
        return d

    def remove_user_from_all_groups(self, user):
        """
        Remove a user from all groups
        """
        for group in self.db:
            self.remove_user_from_group(user, group)

    def list_groups(self, user):
        """
        List groups for a user
        """
        return [group for group in self.db if user in self.db[group]]

    def list_all_groups(self):
        """
        List all groups
        """
        return [group for group in self.db]

    def get_group(self, group):
        """
        Given a group ID, return the group.  Duh.
        """
        group = group.lower()
        return self.db[group]

db = None
def get_db():
    global db
    if db is None:
        db = DataBase("/var/lib/brayerpot/shelve.db")
    return db


def handle_help(payload):
    """
    Given a `@prayerbot help`, we will send them a direct message explaining
    our raison d'existence.  That one's for you, @yaup
    """

    help_msg = """
Hello There!  My name is `@prayerbot`, and I exist to help organize prayers throughout Living Water.  You can interact with me using the following commands:

-  `help`: Print out this help message.  You just did this, so you probably don't need me to tell you how to do it again.

-  `signup group`: Sign up to be a part of prayer group `<group>`. Example:
> *@prayerbot signup LWGuys*
This will put you into the prayer rotations for the LW guys prayer group, where you will be randomly matched with other guys each week to pray for eachother.

-  `stop group`: The reverse of the above command; if you don't want to do this anymore, this will take you out of a group you previously signed up for.

-  `stop`: If you don't give me a group name, I'll just remove you from all groups you were a part of.

-  `list`: List all groups you're in.

When you are a part of a prayer group, I will randomly pair participants of a group up into prayer buddies once a week on Wednesday nights.
    """

    slack_call(
        "chat.postEphemeral",
        channel=payload['channel'],
        user=payload['user'],
        text=help_msg,
        as_user=True
    )


def handle_signup(payload):
    """
    Given a signup command, add the user to groups
    """
    from re import split, IGNORECASE

    try:
        splitted = split("signup", payload['text'], flags=IGNORECASE)
        group = splitted[1].strip().split()[0]

        group_list = get_db().add_user_to_group(payload['user'], group)
        msg = "Great, you've been added to the *%s* prayer group!"%(group)

        if len(group_list) == 1:
            msg += "\nYou're the only one in this group for now; if you meant to join another group, make sure you spelled the group name correctly!"
    except IndexError:
        msg = "You need to give me a group name. Look at `@prayerbot help`"

    slack_call(
        "chat.postEphemeral",
        channel=payload['channel'],
        user=payload['user'],
        text=msg,
        as_user=True
    )

def handle_sign(payload):
    """
    Check to see if someone said `sign up foo`, and make it "just work"
    """
    from re import split, IGNORECASE

    splitted = split("sign up", payload['text'], flags=IGNORECASE)
    if len(splitted) == 1:
        # There was no `sign up` command at all
        return handle_unknown(payload)

    # Otherwise, just mash it up and call `handle_signup` again with our
    # properly munged text
    payload['text'] = 'signup ' + ' sign up '.join(splitted[1:])
    return handle_signup(payload)



def handle_stop(payload):
    """
    Given a stop command, remove the user from groups
    """
    from re import split, IGNORECASE
    db = get_db()
    try:
        splitted = split("stop", payload['text'], flags=IGNORECASE)
        group = splitted[1].strip().split()[0]

        db.remove_user_from_group(payload['user'], group)
        msg = "You have been removed from the *%s* prayer group."%(group)

        group_list = db.list_groups(payload['user'])
        if group_list:
            group_list_str = "*, *".join(group_list)
            msg += " You are still a part of the following prayer groups: *%s*"%(group_list_str)
    except IndexError:
        db.remove_user_from_all_groups(payload['user'])
        msg = "You have been removed from *all* prayer groups"

    slack_call(
        "chat.postEphemeral",
        channel=payload['channel'],
        user=payload['user'],
        text=msg,
        as_user=True
    )

def handle_list(payload):
    """
    Let the user figure out which prayer groups they are a part of.
    """
    group_list = db.list_groups(payload['user'])
    if group_list:
        group_list_str = "*, *".join(group_list)
        msg = "You are a part of the following prayer groups: *%s*"%(group_list_str)
    else:
        msg = "You are not a part of any prayer groups. Use `@prayerbot signup` to join some, or try `@prayerbot help` to learn more!"

    slack_call(
        "chat.postEphemeral",
        channel=payload['channel'],
        user=payload['user'],
        text=msg,
        as_user=True
    )

def handle_unknown(payload):
    slack_call(
        "chat.postEphemeral",
        channel=payload['channel'],
        user=payload['user'],
        text="Sorry, I don't what that means. Try `@prayerbot help`",
        as_user=True
    )

def handle_secret_create_chats(payload):
    name = get_user_first_name(payload['user'])
    logging.info("RED ALERT! SHIELDS TO MAXIMUM! %s knows our secrets!", name)
    create_weekly_group_chats()

def handle_command(command, payload):
    """
    Given a command, fork off into different possible handlers.
    """
    name = get_user_first_name(payload['user'])
    logging.info("Handling command %s from %s", command, name)

    # Map from command name to behavior
    commands = {
        'help': handle_help,
        'signup': handle_signup,
        'sign': handle_sign,
        'stop': handle_stop,
        'list': handle_list,
        'create_chats': handle_secret_create_chats,
    }

    handler = commands.get(command, handle_unknown)
    handler(payload)

def get_user_first_name(user):
    user_obj = slack_call("users.info", user=user)["user"]

    # If they have filled out their profile to have a first name use that,
    # otherwise fall back on their username:
    if "profile" in user_obj and "first_name" in user_obj["profile"]:
        return user_obj["profile"]["first_name"]
    else:
        return user_obj["name"]

def find_user_id(username):
    username = username.lower()
    users = slack_call("users.list", presence=False)["members"]
    for u in users:
        if u["name"].lower() == username:
            return u["id"]
    return None


def create_group_chat(users):
    """
    Given a list of users, create a group chat with the users
    """
    from datetime import date
    # Remove myself if I'm included here so I don't show up in names, etc...
    if bot_id() in users:
        users.remove(bot_id())

    # Get the user names
    names = [get_user_first_name(u) for u in users]
    names_str = "*, *".join(names[:-1]) + "* and *" + names[-1]
    date_str = date.today().strftime("%m/%d/%Y")

    logging.info("Creating group chat between %s", ", ".join(names))

    group_id = slack_call(
        "mpim.open",
        users=",".join(users + [bot_id()]),
    )["group"]["id"]

    msg = "This is a private group message for *%s* for the week "%(names_str)
    msg += "of %s. Feel free to talk and share prayer requests "%(date_str)
    msg += "freely here. I will bow out now, if you need me, use `@prayerbot` "
    msg += "to get my attention. Have fun! :simple_smile:"

    slack_call(
        "chat.postMessage",
        channel=group_id,
        text=msg,
        as_user=True
    )

last_weekly_chat_creation = None
def weekly_chat_creation_time():
    """
    We will run weekly chat creation at 11:00 pm on Wednesday nights
    """
    import datetime
    global last_weekly_chat_creation
    day_of_week = datetime.date.today().weekday()
    now = datetime.datetime.now()

    # If it's wednesday and it's after 11:
    if day_of_week == 2 and now.time() > datetime.time(23):
        # If we've never done this before, just do it now
        if last_weekly_chat_creation is None:
            last_weekly_chat_creation = now
            return True
        # Otherwise, only do it if the last time we did it was more than 3 days ago
        elif now - last_weekly_chat_creation > datetime.timedelta(days=3):
            last_weekly_chat_creation = now
            return True
    # By default, don't do it
    return False


def create_weekly_group_chats():
    """
    For each group that we know about, group the participants into 2s and 3s.
    """
    from random import shuffle
    db = get_db()

    for group in db.list_all_groups():
        users = db.get_group(group)

        if len(users) == 1:
            logging.warn("Group %s is too lonely, not doing anything", group)
            continue

        # Split `users` up into groups of 2, if we have an uneven number the
        # last group will have 3 people
        shuffle(users)
        user_groupings = [users[2*idx:2*idx+2] for idx in range(len(users)//2)]
        if len(users)%2 != 0:
            user_groupings[-1] += [users[-1]]

        for grouping in user_groupings:
            try:
                create_group_chat(grouping)
            except:
                logging.warn("Could not create group chat for %s", ", ".join(grouping))


def event_loop():
    from time import sleep
    db = get_db()

    if not slack_client.rtm_connect():
        logging.error("Could not connect to RTM firehose!")
        raise RuntimeError("rtm_connect() failed")

    logging.info("All systems operational")

    try:
        # Find <@bot_id> pieces of text:
        at_bot = "<@" + bot_id() + ">"
        while True:
            rtm_data = slack_client.rtm_read()

            # If we received something to process, DEWIT
            if rtm_data:
                for payload in rtm_data:
                    # We pay attention to people saying things like
                    # `@prayerbot <command>` in channels, as well as things
                    # like `<command>` sent in DMs to prayerbot.
                    text = payload.get('text', '')
                    if not text:
                        continue

                    if at_bot in text:
                        command = text.split(at_bot)[1].strip().split()[0].lower()
                        
                        # Only pay attention if there is a command
                        if not command:
                            continue
                        handle_command(command, payload)
                        continue

                    if payload.get('type', '') == 'message':
                        if is_im_to_me(payload):
                            command = text.split()[0].lower()
                            if not command:
                                continue

                            handle_command(command, payload)
            else:
                # Don't burn _all_ the CPUs
                sleep(0.01)

                # Check to see if it's cronjob time....
                if weekly_chat_creation_time():
                    create_weekly_group_chats()

    except KeyboardInterrupt:
        logging.info("Gracefully shutting down...")
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    event_loop()
