# database.py - Permanent SQLite Database Handler

import sqlite3
import os

DATABASE = 'meal_mate.db'

def get_db():
    """Get database connection with proper settings"""
    try:
        # timeout=30 prevents database locked errors
        # check_same_thread=False allows multiple threads to use the connection
        conn = sqlite3.connect(DATABASE, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Database error: {e}")
        return None

def close_db(conn):
    """Safely close database connection"""
    if conn:
        try:
            conn.close()
        except Exception as e:
            print(f"Error closing database: {e}")

def init_db():
    """Initialize database with all tables"""
    conn = get_db()
    if not conn:
        print("Failed to connect to database")
        return
    
    cursor = conn.cursor()
    
    # ============ USERS TABLE ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            assessment_completed INTEGER DEFAULT 0
        )
    ''')
    
    # ============ USER PROFILES TABLE ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            age INTEGER,
            gender TEXT,
            height_cm REAL,
            weight_kg REAL,
            bmi REAL,
            bmr INTEGER,
            tdee INTEGER,
            bmi_category TEXT,
            activity_level TEXT,
            sleep_quality TEXT,
            diseases TEXT,
            allergies TEXT,
            medications TEXT,
            diet_preference TEXT,
            meal_preference TEXT,
            disliked_foods TEXT,
            cuisine_preference TEXT,
            plan_duration INTEGER,
            protein_sources TEXT,
            carb_sources TEXT,
            fat_sources TEXT,
            preferred_fruits TEXT,
            preferred_vegetables TEXT,
            available_ingredients TEXT,
            goal_weight REAL,
            goal_advice TEXT,
            meal_timing TEXT,
            recommendations TEXT,
            ai_meal_plan TEXT,
            ai_meal_plan_generated TIMESTAMP,
            meal_plan_start_date TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # ============ MEAL TRACKING TABLE ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meal_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            meal_name TEXT NOT NULL,
            calories INTEGER DEFAULT 0,
            consumed INTEGER DEFAULT 0,
            tracked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # ============ USER STATS TABLE ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_meals INTEGER DEFAULT 0,
            total_calories INTEGER DEFAULT 0,
            total_water REAL DEFAULT 0,
            best_streak INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0,
            last_meal_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # ============ WATER TRACKING TABLE ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS water_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            amount_liters REAL DEFAULT 0,
            tracked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # ============ USER RANKS TABLE (Points & Streaks) ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_ranks (
            user_id INTEGER PRIMARY KEY,
            total_points INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0,
            total_meals_completed INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # ============ WEIGHT TRACKING TABLE ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weight_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            weight_kg REAL NOT NULL,
            recorded_date DATE NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, recorded_date)
        )
    ''')
    
    # ============ POINTS TRANSACTIONS TABLE ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS points_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            points INTEGER NOT NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
         # ============ FITNESS LOGS TABLE ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fitness_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            minutes INTEGER NOT NULL,
            log_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, log_date)
        )
    ''')
    
    # ============ CREATE INDEXES FOR BETTER PERFORMANCE ============
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_meal_tracking_user_date ON meal_tracking(user_id, date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_water_tracking_user_date ON water_tracking(user_id, date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_weight_tracking_user_date ON weight_tracking(user_id, recorded_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_points_transactions_user ON points_transactions(user_id)')
    
    conn.commit()
    conn.close()
    print("✅ Database tables created successfully!")

# ============ HELPER FUNCTIONS ============

def execute_query(query, params=None, fetch_one=False, fetch_all=False):
    """Execute a query and return results"""
    conn = None
    try:
        conn = get_db()
        if not conn:
            return None
        
        cursor = conn.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        result = None
        if fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        
        conn.commit()
        return result
        
    except Exception as e:
        print(f"Query error: {e}")
        return None
    finally:
        if conn:
            conn.close()

def insert_user(email, name, phone, password):
    """Insert a new user"""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO users (email, name, phone, password, assessment_completed)
            VALUES (?, ?, ?, ?, 0)
        ''', (email, name, phone, password))
        
        user_id = cursor.lastrowid
        conn.commit()
        return user_id
        
    except Exception as e:
        print(f"Error inserting user: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_user_by_email(email):
    """Get user by email"""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        return dict(user) if user else None
        
    except Exception as e:
        print(f"Error getting user: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_user_profile(user_id, profile_data):
    """Update user profile"""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Build dynamic update query
        set_clause = ', '.join([f"{key} = ?" for key in profile_data.keys()])
        values = list(profile_data.values()) + [user_id]
        
        cursor.execute(f'''
            UPDATE user_profiles 
            SET {set_clause}
            WHERE user_id = ?
        ''', values)
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Error updating profile: {e}")
        return False
    finally:
        if conn:
            conn.close()

def delete_user(user_id):
    """Delete a user and all related data (ON DELETE CASCADE will handle related tables)"""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Error deleting user: {e}")
        return False
    finally:
        if conn:
            conn.close()

# ============ INITIALIZE DATABASE ============
if __name__ == '__main__' or not os.path.exists(DATABASE):
    if not os.path.exists(DATABASE):
        init_db()
        print(f"📁 New database created: {DATABASE}")
    else:
        # Always run init_db to ensure all tables exist (safe to run multiple times)
        init_db()
        print(f"📁 Using existing database: {DATABASE}")