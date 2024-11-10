import sqlite3

def init_database():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    
    # Drop existing table if you need to recreate it
    c.execute('DROP TABLE IF EXISTS appointments')
    
    # Create appointments table with timezone column
    c.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            appointment_date DATE NOT NULL,
            appointment_time TIME NOT NULL,
            timezone TEXT DEFAULT 'CST',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_database() 