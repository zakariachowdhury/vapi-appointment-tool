from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime, timedelta
import dateparser

app = Flask(__name__)

def parse_date(date_str):
    """Convert various date strings to YYYY-MM-DD format"""
    parsed_date = dateparser.parse(date_str, settings={'PREFER_DATES_FROM': 'future'})
    if parsed_date:
        return parsed_date.strftime('%Y-%m-%d')
    return None

@app.route('/new-appointment', methods=['POST'])
def new_appointment():
    try:
        data = request.json
        tool_call = data['message']['tool_calls'][0]
        arguments = tool_call['function']['arguments']
        
        # Extract data
        name = arguments['name']
        time = arguments['time']
        date_str = arguments['date']
        
        # Parse the date
        parsed_date = parse_date(date_str)
        if not parsed_date:
            return jsonify({'error': 'Invalid date format'}), 400
        
        # Store in database
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO appointments (name, appointment_date, appointment_time)
            VALUES (?, ?, ?)
        ''', (name, parsed_date, time))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': 'Appointment created successfully',
            'appointment': {
                'name': name,
                'date': parsed_date,
                'time': time
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True) 