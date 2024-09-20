import requests
from datetime import datetime


def send_message(content, webHook, username, type, embed = False, color = "", hour = 0, daily = False):
    icon_list = {
        'plus': "https://as2.ftcdn.net/v2/jpg/02/22/71/79/1000_F_222717975_8TfDJLKSAjUmukqhJFcfrhGaNP9xaePZ.jpg",
        "historic": "https://cdn-icons-png.flaticon.com/512/2961/2961948.png",
    }
    if embed:
        now = datetime.now()
        run_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        color_map = {
            "red": 15158332,     # Red color
            "green": 3066993,    # Green color
            "yellow": 16776960   # Yellow color
        }
        if daily:
            title = f" {username} Daily Update"
        else:
            title = f" {username} Hourly Update on {run_time}"
        message = {
             "embeds": [
                {
                    "title": title,
                    "description": content,
                    "color": color_map.get(color, 16777215)  # Default to white if color not found
                }
            ],
            "username": username,
            "avatar_url": icon_list[type]
        }
        pass
    else:
        message = {
            "content": content,
            "username": username,
            "avatar_url": icon_list[type]
        }
    response = requests.post(webHook, json=message)
    if response.status_code == 204:
        print("Message sent successfully!")
    else:
        print(f"Failed to send message: {response.status_code}")
