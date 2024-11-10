from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime, timedelta
import dateparser
import pytz

app = Flask(__name__)

def parse_date(date_str):
    """Convert various date strings to YYYY-MM-DD format"""
    parsed_date = dateparser.parse(date_str, settings={'PREFER_DATES_FROM': 'future'})
    if parsed_date:
        return parsed_date.strftime('%Y-%m-%d')
    return None

def check_appointment_conflict(cursor, date, time):
    """Check if there's an existing appointment at the given date and time"""
    cursor.execute('''
        SELECT * FROM appointments 
        WHERE appointment_date = ? 
        AND appointment_time = ?
    ''', (date, time))
    return cursor.fetchone() is not None

@app.route('/new-appointment', methods=['POST'])
def new_appointment():
    try:
        data = request.json
        tool_call = data['message']['tool_calls'][0]
        arguments = tool_call['function']['arguments']
        tool_call_id = tool_call['id']
        
        # Extract data
        name = arguments['name']
        time = arguments['time']
        date_str = arguments['date']
        
        # Convert the parsed date to CST
        cst = pytz.timezone('America/Chicago')
        parsed_date = dateparser.parse(date_str, settings={'PREFER_DATES_FROM': 'future'})
        if parsed_date.tzinfo is None:  # if date has no timezone info
            parsed_date = pytz.utc.localize(parsed_date)
        cst_date = parsed_date.astimezone(cst)
        
        # Format the date and use the provided time
        formatted_date = cst_date.strftime('%Y-%m-%d')
        formatted_time = time

        # Save to database using CST formatted date/time
        appointment = {
            'name': name,
            'date': formatted_date,
            'time': formatted_time,
            'timezone': 'CST'
        }
        
        # Check for conflicts before inserting
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        
        if check_appointment_conflict(c, formatted_date, formatted_time):
            conn.close()
            return jsonify({
                'results': [{
                    'toolCallId': tool_call_id,
                    'result': {
                        'status': 'error',
                        'message': f'An appointment already exists on {formatted_date} at {formatted_time} CST'
                    }
                }]
            }), 409  # HTTP 409 Conflict
        
        # If no conflict, proceed with insertion
        c.execute('''
            INSERT INTO appointments (name, appointment_date, appointment_time, timezone)
            VALUES (?, ?, ?, ?)
        ''', (name, formatted_date, formatted_time, 'CST'))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'results': [{
                'toolCallId': tool_call_id,
                'result': {
                    'status': 'success',
                    'message': 'Appointment created successfully',
                    'appointment': appointment
                }
            }]
        })
        
    except Exception as e:
        return jsonify({
            'results': [{
                'toolCallId': tool_call_id,
                'result': {
                    'error': str(e)
                }
            }]
        }), 500

@app.route('/get-appointment', methods=['POST'])
def get_appointment():
    try:
        data = request.json
        tool_call = data['message']['tool_calls'][0]
        arguments = tool_call['function']['arguments']
        tool_call_id = tool_call['id']
        
        # Extract name from arguments
        name = arguments['name']
        
        # Query database
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        
        c.execute('''
            SELECT appointment_date, appointment_time, timezone 
            FROM appointments 
            WHERE name = ?
            ORDER BY appointment_date, appointment_time
        ''', (name,))
        
        appointments = c.fetchall()
        conn.close()
        
        if not appointments:
            return jsonify({
                'results': [{
                    'toolCallId': tool_call_id,
                    'result': {
                        'status': 'error',
                        'message': f'No appointments found for {name}'
                    }
                }]
            }), 404
        
        # Format appointments
        formatted_appointments = [{
            'name': name,
            'date': apt[0],
            'time': apt[1],
            'timezone': apt[2]
        } for apt in appointments]
        
        return jsonify({
            'results': [{
                'toolCallId': tool_call_id,
                'result': {
                    'status': 'success',
                    'appointments': formatted_appointments
                }
            }]
        })
        
    except Exception as e:
        return jsonify({
            'results': [{
                'toolCallId': tool_call_id,
                'result': {
                    'error': str(e)
                }
            }]
        }), 500

if __name__ == '__main__':
    app.run(debug=True) 