import json
import os
import signal
import sqlite3
import sys
from colorama import Fore
from flask import Flask, render_template
import threading
import requests
import time

app = Flask(__name__, static_folder='static')

exit_event = threading.Event()

queue_server_url = 'http://localhost:5555'

def get_db_connection():
    conn = None
    try:
        db_path = os.path.abspath(os.getcwd() + "/db/database.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
    return conn

def dequeue_message():
    max_retries = 100
    retries = 0

    while retries < max_retries:
        try:
            response = requests.get(f'{queue_server_url}/dequeue?key=order-service', timeout=1200000)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)
            return response.json()
        except requests.exceptions.Timeout:
            print(f"Timeout error. Retry {retries + 1}/{max_retries}")
        except requests.exceptions.HTTPError:
            print(f"HTTPError. Retry {retries + 1}/{max_retries}")
        except requests.exceptions.RequestException:
            print(f"RequestException. Retry {retries + 1}/{max_retries}")
        except Exception:
            print(f"Exception. Retry {retries + 1}/{max_retries}")

        retries += 1
        # Use exponential backoff with a maximum delay of 32 seconds
        delay = min(2 ** retries, 32)
        time.sleep(delay)

    print(Fore.RED + "Max retries reached. Unable to dequeue message.")
    return None  # Return None to indicate that no message was retrieved

def consumer():
    while True:
        try:
            message = dequeue_message()
            if message:
                print(f'Received message: {message}')

                message_object = message.get('message')

                order_info = json.dumps(message_object)
                order_status = 'PENDING'

                conn = get_db_connection()
                conn.execute('INSERT INTO orders (order_info, status) VALUES (?, ?)',
                            (order_info, order_status))
                conn.commit()
                conn.close()

        except requests.exceptions.RequestException as e:
            print(f"Error: {e}. Retrying...")

@app.route('/')
def index():
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM orders WHERE status = ?', ('PENDING',)).fetchall()
    conn.close()

    orders = [dict(row) for row in rows]

    for order in orders:
        order['order_info'] = json.loads(order['order_info'])

    return render_template('index.html', orders=orders)




thread_return = {'seconds': 0}

consumer_thread = threading.Thread(target=consumer, args=(thread_return,), daemon=True)
consumer_thread.start()

if __name__ == '__main__':
    # Run the Flask app
    app.run(host='localhost', port=5001, debug=True)
