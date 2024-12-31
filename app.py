import json
from concurrent.futures import ThreadPoolExecutor
import eventlet

eventlet.monkey_patch()
import time
from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, send, SocketIO
import random
from string import ascii_uppercase
import datetime
import csv
import os
from dotenv import load_dotenv
from openai import AzureOpenAI, api_key

load_dotenv()
eventlet.monkey_patch()
NAME_PREFIX = "HUMAN_____^^^"
THREAD_ARR = ["thread_manager","thread_assistant_1","thread_assistant_2"]
MANAGER_ID = "asst_TGzKqOXlWpBQG7OaxsoidDjV"
ASSISTANT_1_ID = "asst_jXbhf4ZCBVASAjhLxMQFy7mF"
ASSISTANT_2_ID = "asst_IIV9BW5rib0EHo3mtjznCPeA"
def create_thread_ai_assistant():
    #create thread
    client = AzureOpenAI(
        api_key=os.environ['AZURE_OPENAI_API_KEY'],
        api_version="2024-08-01-preview",
        azure_endpoint="https://basgpt.openai.azure.com"
    )

    empty_thread = client.beta.threads.create()
    print(empty_thread)
    return empty_thread.id

def send_msg_ai_assistant(thread_id, assistant_id, msg):
    client = AzureOpenAI(
        api_key=os.environ['AZURE_OPENAI_API_KEY'],
        api_version="2024-08-01-preview",
        azure_endpoint="https://basgpt.openai.azure.com"
    )
    # push msg to thread
    thread_message = client.beta.threads.messages.create(
        thread_id=thread_id,
        role="assistant",
        content=msg,
    )
    # print(thread_message)
    # run
    # 在线程上运行助手
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    # 5. 等待运行完成
    print("等待助手处理请求...")
    print(thread_id, run.id)
    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        print(run.status)
        if run.status == 'completed':
            messages = client.beta.threads.messages.list(
                thread_id=thread_id
            )
            # print(messages)
            return messages.data[0].content[0].text.value
        elif run.status == 'failed':
            print(run.last_error)
            return "next_round"
        time.sleep(1)
def send_msg_to_chatgpt(room):
    client = AzureOpenAI(
        api_key=os.environ['AZURE_OPENAI_API_KEY'],
        api_version="2024-08-01-preview",
        azure_endpoint="https://basgpt.openai.azure.com",
        azure_deployment="EDUAI"
    )
    messages = []
    messages.append({"role": "system", "content": "You are a helpful system, including 2 assistants. There would be more than 1 user in this discussion, "
                                          "when users input discussion information, "
                                          "the 2 assistants should play roles in group chatting. And as talking in a group, do not use 'you', "
                                          "or other words which cannot to specific people. "
                                          "Bob is  an expert on climate change. A student has just mentioned a common misconception about the impact of renewable energy.  Correct this misconception with accurate data and explain why this is a critical issue, making sure to use clear and accessible language, keep each of your messages short."
                                          "Anna is a devil's advocate in a discussion about the economic impacts of climate change.Challenge the group's prevailing assumption with a well-considered counterargument, citing potential economic benefits of non-renewable energy, and ask a probing question to stimulate further discussion.You keep each of your messages short."
                                          "ai assistants should both take part in discussion, but they cannot talk in one round response. when ai assistants response, should start with assistants' name, e.g. Bob: hello or Anna: hello"})
    old_msg = load_each_messages_from_csv(room)
    messages += old_msg
    print("messages: ",messages)
    response = client.chat.completions.create(
        model="gpt-4o",  # model = "deployment_name".
        messages=messages,
        temperature=0.7,
        max_tokens=100
    )
    print("response: ", response.choices[0].message.content)
    if "Bob:" in response.choices[0].message.content:
        content = {
            "message": response.choices[0].message.content.replace("Bob:",""),
            "name": "Bob",
            "timestamp": current_time()
        }
    elif "Anna:" in response.choices[0].message.content:
        content = {
            "message": response.choices[0].message.content.replace("Anna:",""),
            "name": "Anna",
            "timestamp": current_time()
        }
    else:
        content = {
            "message": response.choices[0].message.content,
            "name": response.choices[0].message.role,
            "timestamp": current_time()
        }
    send(content, to=room)
    rooms[room]["messages"].append(content)

    # Save messages to CSV
    save_messages_to_csv(room)

app = Flask(__name__)
app.config["SECRET_KEY"] = "hjhjsdahhds"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', transports=['websocket', 'polling'])
# socketio = SocketIO(app)

rooms = {}

def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(ascii_uppercase)
        
        if code not in rooms:
            break
    
    return code

def current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_constant_to_csv(room, thread_name, thread_new):
    if room not in rooms:
        return

    file_path = f"{room}_constant.csv"

    # with open(file_path, mode='w', newline='', encoding='utf-8') as file:
    #     writer = csv.writer(file)
    #     writer.writerow([thread_name, thread_new])
    with open(file_path, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)

        # 如果文件是空的，可以先写入标题行
        if file.tell() == 0:
            writer.writerow(['Key','Value'])
        # 追加写入新数据
        writer.writerow([thread_name, thread_new])

def save_messages_to_csv(room):
    if room not in rooms:
        return
    
    file_path = f"{room}_chat.csv"
    
    messages = rooms[room]["messages"]
    
    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(["Name", "Message", "Timestamp"])
        for message in messages:
            writer.writerow([message["name"], message["message"], message["timestamp"]])

def load_constant_from_csv(room):
    data_map = {}
    if room not in rooms:
        return

    file_path = f"{room}_constant.csv"

    # 打开并读取 CSV 文件
    with open(file_path, mode='r', newline='') as file:
        reader = csv.reader(file)
        for row in reader:
            # 假设每一行有两个元素，第一个作为键，第二个作为值
            key = row[0]  # 第一个元素是键
            value = row[1]  # 第二个元素是值
            data_map[key] = value

    return data_map

def load_each_messages_from_csv(room):
    if room not in rooms:
        return
    file_path = f"{room}_chat.csv"

    messages = []
    try:
        with open(file_path, mode='r', encoding='utf-8') as file:
            reader = csv.reader(file)
            # 读取所有行到列表中
            rows = list(reader)

            # 确保文件至少有标题行
            if len(rows) <= 1:
                return []  # 返回空列表，如果没有有效数据
            # 去掉标题行
            data_rows = rows[1:]
            # 倒序检查行
            for row in reversed(data_rows):
                if len(messages) >= 10:
                    break  # 如果已经找到两行且没有 "___"，结束
                if ("has entered the room" or "has left the room") in row[1]:
                    continue
                if NAME_PREFIX in row[0]:
                    messages.insert(0,{"role": "user", "content": row[0].replace(NAME_PREFIX,"")+": "+row[1]})
                else:
                    messages.insert(0,{"role": "assistant", "content": row[0]+": "+row[1]})
            return messages

    except FileNotFoundError:
        print(f"File {file_path} not found.")
        return []
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return []

def load_each_messages_from_csv_withlabel(room, stop_label):
    if room not in rooms:
        return
    file_path = f"{room}_chat.csv"

    try:
        with open(file_path, mode='r', encoding='utf-8') as file:
            reader = csv.reader(file)
            # 读取所有行到列表中
            rows = list(reader)

            # 确保文件至少有标题行
            if len(rows) <= 1:
                return []  # 返回空列表，如果没有有效数据
            # 去掉标题行
            data_rows = rows[1:]

            send_msg_arr = []
            # 倒序检查行
            for row in reversed(data_rows):

                if stop_label in row[0]:
                    break
                if "has entered the room" in row[1] or "has left the room" in row[1]:
                    continue
                if "Group Manager" in row[0]:
                    continue
                if NAME_PREFIX in row[0]:
                    send_msg_dict = {
                        "name": row[0].replace(NAME_PREFIX,""),
                        "message": row[1]
                    }
                    # print("send_msg_dict,", send_msg_dict)
                    send_msg_arr.append(send_msg_dict)
                    # print("send_msg_arr1",send_msg_arr)
                else:
                    send_msg_dict = {
                        "name": row[0],
                        "message": row[1]
                    }
                    send_msg_arr.append(send_msg_dict)
            print("send_msg_arr2",send_msg_arr)
            send_msg = json.dumps(send_msg_arr)
            return send_msg

    except FileNotFoundError:
        print(f"File {file_path} not found.")
        return []
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return []
@app.route("/", methods=["POST", "GET"])
async def home():
    session.clear()
    if request.method == "POST":
        name = request.form.get("name")
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        if not name:
            return render_template("home.html", error="Please enter a name.", code=code, name=name)

        if join != False and not code:
            return render_template("home.html", error="Please enter a room code.", code=code, name=name)
        
        room = code
        if create != False:
            room = generate_unique_code(4)
            rooms[room] = {"members": 0, "messages": []}

            #创建这个room的thread，3个，对应1 manager+2 assistants
            # socketio.start_background_task(target=create_all_assistant, room=room,thread_name=THREAD_ARR[0])
            # socketio.start_background_task(target=create_all_assistant, room=room, thread_name=THREAD_ARR[1])
            # socketio.start_background_task(target=create_all_assistant, room=room, thread_name=THREAD_ARR[2])
            # await create_all_assistant(room, THREAD_ARR[0])
            # await create_all_assistant(room, THREAD_ARR[1])
            # await create_all_assistant(room, THREAD_ARR[2])
            # executor.submit(create_all_assistant, room=room, thread_name=THREAD_ARR[0])
            # executor.submit(create_all_assistant, room=room, thread_name=THREAD_ARR[1])
            # executor.submit(create_all_assistant, room=room, thread_name=THREAD_ARR[2])
            print(f"start at {time.strftime('%X')}")
            # asyncio.create_task(create_all_assistant(room, THREAD_ARR[0]))
            # print(f"1 at {time.strftime('%X')}")
            # asyncio.create_task(create_all_assistant(room, THREAD_ARR[1]))
            # print(f"2 at {time.strftime('%X')}")
            # asyncio.create_task(create_all_assistant(room, THREAD_ARR[2]))
            # print(f"end at {time.strftime('%X')}")
            start_assistants_sync(room)
            print(f"end at {time.strftime('%X')}")
            # 等待所有任务完成
            # await asyncio.gather(task1, task2, task3)

        elif code not in rooms:
            return render_template("home.html", error="Room does not exist.", code=code, name=name)
        
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room"))

    return render_template("home.html")

def create_all_assistant(room, thread_name):
    thread_new = create_thread_ai_assistant()

    save_constant_to_csv(room, thread_name, thread_new)

def start_assistants_sync(room):
    with ThreadPoolExecutor() as executor:
        executor.submit(create_all_assistant, room, THREAD_ARR[0])
        executor.submit(create_all_assistant, room, THREAD_ARR[1])
        executor.submit(create_all_assistant, room, THREAD_ARR[2])
@app.route("/room")
def room():
    room = session.get("room")
    if room is None or session.get("name") is None or room not in rooms:
        return redirect(url_for("home"))
    filtered_messages = [
        {**msg, "name": msg["name"].replace(NAME_PREFIX, "")}
        for msg in rooms[room]["messages"]
    ]
    return render_template("room.html", code=room, messages=filtered_messages)
    # return render_template("room.html", code=room, messages=rooms[room]["messages"])

@socketio.on("message")
def message(data):
    room = session.get("room")
    if room not in rooms:
        return 

    user_message = data["data"]

    content = {
        "name": session.get("name"),
        "message": user_message,
        "timestamp": current_time()
    }
    send(content, to=room)
    content = {
        "name": session.get("name")+" "+NAME_PREFIX,
        "message": user_message,
        "timestamp": current_time()
    }
    rooms[room]["messages"].append(content)
    
    # Save messages to CSV
    save_messages_to_csv(room)

    # autogen!!!
    # last_two_rows = load_last_two_messages_from_csv(room)
    # count = 0
    # new_user_message = ""
    # for i in range(len(last_two_rows)):
    #     if NAME_PREFIX not in last_two_rows[i][0]:
    #         continue
    #     count = count + 1
    #     new_user_message = new_user_message+ " "+ last_two_rows[i][0].replace(NAME_PREFIX, "")+":"+ last_two_rows[i][1]
    # if count == 2:
    #     print("new_user_message:", new_user_message)
    #     AgentFactory.createAgent(new_user_message)

    # azure openai
    # send_msg_to_chatgpt(room)

    #azure openai assistants
    # send_msg = session.get("name")+":"+user_message
    send_msg_dict = {
        "name": session.get("name"),
        "message": user_message
    }
    send_msg_arr = [send_msg_dict]
    # 将字典转换为 JSON 格式的字符串
    send_msg = json.dumps(send_msg_arr)
    thread_map = load_constant_from_csv(room)
    thread_id_manager = thread_map[THREAD_ARR[0]]
    # send_msg = [{"role": "user", "content": session.get("name")+": "+user_message}]
    thread_assistant_1 = thread_map[THREAD_ARR[1]]
    thread_assistant_2 = thread_map[THREAD_ARR[2]]
    round = 0
    next_speaker = ""
    while True:
        round = round+1
        if round >= 4 :
            next_speaker = session.get("name")
            print("next_speaker: ",next_speaker)
            break
        next_speaker = send_msg_ai_assistant(thread_id_manager, MANAGER_ID, send_msg)
        if "Bob" in next_speaker or "Anna" in next_speaker:
            print("next_speaker: ", next_speaker)
            if "Bob" in next_speaker:
                send_msg = load_each_messages_from_csv_withlabel(room, "Bob")
                print("send_msg to Bob: ", send_msg)
                msg_assist_1 = send_msg_ai_assistant(thread_assistant_1, ASSISTANT_1_ID, send_msg)
                print("msg_assist_1: ", msg_assist_1)
                content = {
                    "message": msg_assist_1,
                    "name": "Bob",
                    "timestamp": current_time()
                }
                # send_msg = "Bob: " + msg_assist_1
                send_msg_dict = {
                    "name": "Bob",
                    "message": msg_assist_1
                }
                send_msg_arr = [send_msg_dict]
                # 将字典转换为 JSON 格式的字符串
                send_msg = json.dumps(send_msg_arr)
                send(content, to=room)
                rooms[room]["messages"].append(content)

                # Save messages to CSV
                save_messages_to_csv(room)
            elif "Anna" in next_speaker:
                send_msg = load_each_messages_from_csv_withlabel(room, "Anna")
                print("send_msg to Anna: ", send_msg)
                msg_assist_2 = send_msg_ai_assistant(thread_assistant_2, ASSISTANT_2_ID, send_msg)
                print("msg_assist_2: ", msg_assist_2)
                content = {
                    "message": msg_assist_2,
                    "name": "Anna",
                    "timestamp": current_time()
                }
                # send_msg = "Anna: " + msg_assist_2
                send_msg_dict = {
                    "name": "Anna",
                    "message": msg_assist_2
                }
                send_msg_arr = [send_msg_dict]
                # 将字典转换为 JSON 格式的字符串
                send_msg = json.dumps(send_msg_arr)
                send(content, to=room)
                rooms[room]["messages"].append(content)

                # Save messages to CSV
                save_messages_to_csv(room)
        elif "next_round" in next_speaker:
            time.sleep(5)
        else:
            print("next_speaker——2: ", next_speaker)
            # todo manager send msg, next is xxx
            break

    content = {
        "message": '%s, please speaking' % next_speaker,
        "name": "Group Manager",
        "timestamp": current_time()
    }
    send(content, to=room)
    rooms[room]["messages"].append(content)

    # Save messages to CSV
    save_messages_to_csv(room)

@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return
    if room not in rooms:
        leave_room(room)
        return

    join_room(room)
    content = {
        "name": name,
        "message": "has entered the room",
        "timestamp": current_time(),
        "type": "enter"
    }
    send(content, to=room)
    rooms[room]["messages"].append(content)
    rooms[room]["members"] += 1
    print(f"{name} joined room {room}")

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            save_messages_to_csv(room)
            del rooms[room]

    content = {
        "name": name,
        "message": "has left the room",
        "timestamp": current_time(),
        "type": "leave"
    }
    send(content, to=room)
    try:
        rooms[room]["messages"].append(content)
    except Exception as e:
        print(f"Error: {e}")
    print(f"{name} has left the room {room}")

if __name__ == "__main__":
    socketio.run(app, debug=True)
    #socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 54322)))



