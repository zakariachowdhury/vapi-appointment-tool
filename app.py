from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime, timedelta
import dateparser
import pytz
import holidays

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

def is_business_day(date):
    """Check if date is a business day (not weekend or holiday)"""
    us_holidays = holidays.US()  # US holidays
    return date.weekday() < 5 and date not in us_holidays

def get_business_hours():
    """Return list of business hours in 24hr format"""
    return [f"{hour:02d}:00" for hour in range(9, 17)]  # 9 AM to 5 PM

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
        parsed_date = dateparser.parse(date_str, settings={
            'PREFER_DATES_FROM': 'future',
            'RELATIVE_BASE': datetime.now(cst),
            'TIMEZONE': 'America/Chicago'
        })
        
        if not parsed_date:
            return jsonify({
                'results': [{
                    'toolCallId': tool_call_id,
                    'result': {
                        'status': 'error',
                        'message': f'Unable to parse date: {date_str}'
                    }
                }]
            }), 400
            
        if parsed_date.tzinfo is None:  # if date has no timezone info
            parsed_date = cst.localize(parsed_date)
        else:
            parsed_date = parsed_date.astimezone(cst)
        
        # Check if it's a business day
        if not is_business_day(parsed_date.date()):
            return jsonify({
                'results': [{
                    'toolCallId': tool_call_id,
                    'result': {
                        'status': 'error',
                        'message': f'Cannot schedule appointments on weekends or holidays. {parsed_date.strftime("%Y-%m-%d")} is a {parsed_date.strftime("%A")} and is not a business day.'
                    }
                }]
            }), 400
        
        # Format the date and use the provided time
        formatted_date = parsed_date.strftime('%Y-%m-%d')
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

@app.route('/cancel-appointment', methods=['POST'])
def cancel_appointment():
    try:
        data = request.json
        tool_call = data['message']['tool_calls'][0]
        arguments = tool_call['function']['arguments']
        tool_call_id = tool_call['id']
        
        # Extract data
        name = arguments['name']
        date_str = arguments['date']
        time = arguments['time']
        
        # Parse and convert date to CST
        cst = pytz.timezone('America/Chicago')
        parsed_date = dateparser.parse(date_str, settings={'PREFER_DATES_FROM': 'future'})
        if parsed_date.tzinfo is None:
            parsed_date = pytz.utc.localize(parsed_date)
        cst_date = parsed_date.astimezone(cst)
        formatted_date = cst_date.strftime('%Y-%m-%d')
        
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        
        # Check if appointment exists
        c.execute('''
            SELECT id FROM appointments 
            WHERE name = ? 
            AND appointment_date = ? 
            AND appointment_time = ?
        ''', (name, formatted_date, time))
        
        appointment = c.fetchone()
        
        if not appointment:
            conn.close()
            return jsonify({
                'results': [{
                    'toolCallId': tool_call_id,
                    'result': {
                        'status': 'error',
                        'message': f'No appointment found for {name} on {formatted_date} at {time}'
                    }
                }]
            }), 404
        
        # Delete the appointment
        c.execute('''
            DELETE FROM appointments 
            WHERE name = ? 
            AND appointment_date = ? 
            AND appointment_time = ?
        ''', (name, formatted_date, time))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'results': [{
                'toolCallId': tool_call_id,
                'result': {
                    'status': 'success',
                    'message': f'Appointment canceled successfully for {name} on {formatted_date} at {time}'
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

@app.route('/reschedule-appointment', methods=['POST'])
def reschedule_appointment():
    try:
        data = request.json
        tool_call = data['message']['tool_calls'][0]
        arguments = tool_call['function']['arguments']
        tool_call_id = tool_call['id']
        
        # Extract data
        name = arguments['name']
        new_date_str = arguments['date']
        new_time = arguments['time']
        
        # Find existing appointment
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        
        c.execute('''
            SELECT appointment_date, appointment_time 
            FROM appointments 
            WHERE name = ?
            ORDER BY appointment_date, appointment_time
        ''', (name,))
        
        result = c.fetchone()
        conn.close()
        
        if not result:
            return jsonify({
                'results': [{
                    'toolCallId': tool_call_id,
                    'result': {
                        'status': 'error',
                        'message': f'No appointment found for {name}'
                    }
                }]
            }), 404
            
        old_date = result[0]  # Get the date from the existing appointment
        old_time = result[1]  # Get the time from the existing appointment
        
        # Parse new date to CST
        cst = pytz.timezone('America/Chicago')
        new_date_parsed = dateparser.parse(new_date_str, settings={'PREFER_DATES_FROM': 'future'})
        if new_date_parsed.tzinfo is None:
            new_date_parsed = pytz.utc.localize(new_date_parsed)
        new_date_cst = new_date_parsed.astimezone(cst).strftime('%Y-%m-%d')
        
        # Remove all existing appointments for this user
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute('DELETE FROM appointments WHERE name = ?', (name,))
        conn.commit()
        conn.close()
        
        # Prepare new appointment request
        new_data = {
            'message': {
                'tool_calls': [{
                    'id': tool_call_id,
                    'function': {
                        'arguments': {
                            'name': name,
                            'date': new_date_cst,
                            'time': new_time
                        }
                    }
                }]
            }
        }
        
        # Create new appointment
        with app.test_request_context(json=new_data):
            new_response = new_appointment()
            if new_response[1] if isinstance(new_response, tuple) else 200 >= 400:
                return new_response
        
        return jsonify({
            'results': [{
                'toolCallId': tool_call_id,
                'result': {
                    'status': 'success',
                    'message': 'Appointment rescheduled successfully',
                    'old_appointment': {
                        'date': old_date,
                        'time': old_time,
                        'timezone': 'CST'
                    },
                    'new_appointment': {
                        'name': name,
                        'date': new_date_cst,
                        'time': new_time,
                        'timezone': 'CST'
                    }
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

@app.route('/next-available-slots', methods=['POST'])
def next_available_slots():
    try:
        data = request.json
        tool_call = data['message']['tool_calls'][0]
        tool_call_id = tool_call['id']
        
        # Start from tomorrow
        current_date = datetime.now(pytz.timezone('America/Chicago'))
        check_date = current_date.date() + timedelta(days=1)
        
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        
        # Look for the next business day with at least one available slot
        for _ in range(30):  # Limit search to next 30 days
            if is_business_day(check_date):
                available_slots = []
                
                for hour in get_business_hours():
                    if not check_appointment_conflict(c, check_date.strftime('%Y-%m-%d'), hour):
                        available_slots.append({
                            'date': check_date.strftime('%Y-%m-%d'),
                            'time': hour,
                            'timezone': 'CST'
                        })
                
                # If we found any slots on this day, return them
                if available_slots:
                    conn.close()
                    return jsonify({
                        'results': [{
                            'toolCallId': tool_call_id,
                            'result': {
                                'status': 'success',
                                'date': check_date.strftime('%Y-%m-%d'),
                                'available_slots': available_slots
                            }
                        }]
                    })
            
            check_date += timedelta(days=1)
        
        conn.close()
        return jsonify({
            'results': [{
                'toolCallId': tool_call_id,
                'result': {
                    'status': 'error',
                    'message': 'No available slots found in the next 30 days'
                }
            }]
        }), 404
        
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