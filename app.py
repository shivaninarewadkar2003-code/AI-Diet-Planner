from flask import Flask, render_template, request, jsonify, session, redirect
from database import get_db, init_db
import json
import os
import google.generativeai as genai
import re
import requests
import base64
import io

 
from datetime import datetime,timedelta,date
from werkzeug.utils import secure_filename
from google.generativeai import types
from dotenv import load_dotenv
 
load_dotenv()

# Fitness API Key
GEMINI_API_KEY_FITNESS = os.getenv('GEMINI_API_KEY_FITNESS', '')

app = Flask(__name__)
app.secret_key = 'your-secret-key-12345'

# Initialize database
init_db()

# ============ GEMINI AI CONFIGURATION ============
 
# Main API Key (Meal Planning, Recipes, Replace Meal)
GEMINI_API_KEY_MAIN = os.getenv('GEMINI_API_KEY_MAIN', '')
genai.configure(api_key=GEMINI_API_KEY_MAIN)


def get_model_with_key(api_key, model_name='gemini-2.5-flash-lite'):
    """Get Gemini model with specific API key"""
    if api_key:
        # Save current config
        original_key = genai.api_key
        # Configure with new key
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        # Restore original key
        genai.configure(api_key=original_key)
        return model
    else:
        print(f"⚠️ API key not configured, using main key")
        return genai.GenerativeModel(model_name)

def get_main_model():
    """Model for Meal Planning, Recipes, Replace Meal (uses MAIN key)"""
    return genai.GenerativeModel('gemini-2.5-flash-lite')


# Health News API Key
GEMINI_API_KEY_NEWS = os.getenv('GEMINI_API_KEY_NEWS', '')

def get_news_model():
    """Model for Health News (uses NEWS key)"""
    if GEMINI_API_KEY_NEWS:
        return get_model_with_key(GEMINI_API_KEY_NEWS, 'gemini-2.5-flash-lite')
    print(f"⚠️ News API key not configured, using main key")
    return genai.GenerativeModel('gemini-2.5-flash-lite')

def get_fitness_model():
    """Model for Fitness recommendations (uses FITNESS key)"""
    if GEMINI_API_KEY_FITNESS:
        # Create a new client with fitness key
        import google.generativeai as genai_local
        genai_local.configure(api_key=GEMINI_API_KEY_FITNESS)
        return genai_local.GenerativeModel('gemini-2.5-flash-lite')
    print(f"⚠️ Fitness API key not configured, using main key")
    return genai.GenerativeModel('gemini-2.5-flash-lite')


DATA_DIR = 'data'

# ==================== DATE FORMAT FILTER ====================
@app.template_filter('strftime')
def _jinja2_filter_datetime(date, fmt=None):
    if not fmt:
        fmt = "%A, %B %d, %Y"
    return datetime.now().strftime(fmt)

# ==================== CSV/JSON DATA LOADING ====================
def load_json_data(filename):
    try:
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    all_items = []
                    for v in data.values():
                        if isinstance(v, list):
                            all_items.extend(v)
                    return all_items
        return []
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []

# Load all data from JSON files
MEDICAL_CONDITIONS = load_json_data('medical_conditions.json') or []
ALLERGIES = load_json_data('allergies.json') or ['Nuts', 'Eggs', 'Dairy']
MEDICATIONS = load_json_data('medications.json') or ['Metformin', 'Insulin']
FRUITS = load_json_data('fruits.json') or []
VEGETABLES = load_json_data('vegetables.json') or []

print("\n" + "=" * 60)
print("📦 DATA LOADING SUMMARY")
print("=" * 60)
print(f"🏥 Medical Conditions:  {len(MEDICAL_CONDITIONS)} items")
print(f"⚠️ Allergies:           {len(ALLERGIES)} items")
print(f"💊 Medications:         {len(MEDICATIONS)} items")
print(f"🍎 Fruits:              {len(FRUITS)} items")
print(f"🥬 Vegetables:          {len(VEGETABLES)} items")
print("=" * 60)

# ============ DISEASE-SPECIFIC DIETARY GUIDELINES ============
def get_disease_guidelines(diseases):
    """Return disease-specific dietary guidelines for AI prompt"""
    diseases_lower = diseases.lower()
    
    guidelines = []
    
    # Hypertension
    if 'hypertension' in diseases_lower:
        guidelines.append("""
        ❤️ HYPERTENSION RULES:
        - NO added salt, NO pickles, NO papads, NO processed/packaged foods
        - YES to fresh vegetables, fruits, whole grains, unsalted nuts, low-fat dairy
        - Unsalted cashews, almonds, walnuts are GOOD
        - Homemade food only, no restaurant or ready-to-eat meals
        """)
    
    # Diabetes
    if 'diabetes' in diseases_lower:
        guidelines.append("""
        🩸 DIABETES RULES:
        - LOW glycemic index foods only (NO white rice, white bread, maida, sugar)
        - NO sweet fruits (mango, grapes, banana, chiku, litchi)
        - NO fruit juices, soda, honey, jaggery, sweets
        - YES to millets (ragi, jowar, bajra), brown rice, quinoa, oats
        - YES to leafy greens, broccoli, lean proteins (chicken, fish, eggs, tofu)
        """)
    
    # Kidney Disease
    if 'kidney' in diseases_lower or 'ckd' in diseases_lower:
        guidelines.append("""
        🩺 KIDNEY DISEASE RULES:
        - LOW potassium: NO bananas, oranges, spinach, potatoes, tomatoes, avocados
        - LOW phosphorus: LIMIT dairy, beans, whole grains, brown rice
        - LOW sodium: NO added salt, pickles, papads, processed foods
        - SAFE foods: apples, pears, berries, cabbage, cauliflower, bottle gourd, white rice (small), egg whites only
        """)
    
    # High Cholesterol
    if 'cholesterol' in diseases_lower:
        guidelines.append("""
        🫀 HIGH CHOLESTEROL RULES:
        - LOW saturated fat, NO trans fat, HIGH soluble fiber
        - AVOID fried foods, red meat, full-fat dairy, coconut oil, palm oil
        - YES to oats, barley, fatty fish (salmon, mackerel), nuts (walnuts, almonds), olive oil
        """)
    
    # Obesity
    if 'obesity' in diseases_lower or 'weight loss' in diseases_lower:
        guidelines.append("""
        ⚖️ WEIGHT LOSS RULES:
        - Calorie deficit (500 less than TDEE)
        - HIGH protein (chicken, fish, eggs, tofu, paneer)
        - HIGH fiber (vegetables, fruits, whole grains)
        - AVOID sugary drinks, fried foods, processed snacks, sweets, white bread
        """)
    
    # Heart Disease
    if 'heart' in diseases_lower or 'cardiac' in diseases_lower:
        guidelines.append("""
        💚 HEART DISEASE RULES:
        - Mediterranean diet: olive oil, nuts, fatty fish, whole grains
        - LOW saturated fat, LOW sodium, NO trans fat
        - AVOID red meat, fried foods, full-fat dairy, coconut oil, butter
        - YES to walnuts, almonds, salmon, sardines, oats, legumes
        """)
    
    # PCOD/PCOS
    if 'pcos' in diseases_lower or 'pcod' in diseases_lower:
        guidelines.append("""
        🌸 PCOD/PCOS RULES:
        - LOW glycemic index foods
        - ANTI-inflammatory: berries, fatty fish, turmeric, ginger
        - AVOID sugar, white rice, white bread, processed foods, fried foods
        - YES to lean proteins, whole grains (quinoa, millets, oats), leafy greens
        """)
    
    # Thyroid
    if 'thyroid' in diseases_lower:
        guidelines.append("""
        🦋 THYROID RULES:
        - For HYPOTHYROIDISM: iodine-rich (fish, eggs), selenium-rich (Brazil nuts, eggs)
        - For HYPERTHYROIDISM: LOW iodine (avoid iodized salt, seafood)
        - YES to lean proteins, fruits, vegetables, whole grains
        """)
    
    # Anemia
    if 'anemia' in diseases_lower:
        guidelines.append("""
        🩸 ANEMIA RULES:
        - HIGH iron: red meat, organ meats (liver), poultry, fish, eggs
        - Plant iron: spinach, legumes, beans, lentils, tofu
        - Vitamin C for absorption: citrus fruits, bell peppers, tomatoes
        - AVOID tea/coffee with iron meals
        """)
    
    # Liver Disease / Fatty Liver
    if 'liver' in diseases_lower or 'fatty liver' in diseases_lower:
        guidelines.append("""
        🫁 LIVER DISEASE RULES:
        - LOW fat, LOW calorie, HIGH protein for liver repair
        - NO alcohol COMPLETELY
        - AVOID fried foods, sugar, sweets, sugary drinks, red meat
        - YES to lean proteins (chicken breast, fish, egg whites, tofu)
        - YES to vegetables (leafy greens, cruciferous) - 5+ servings
        """)
    
    # If no specific condition
    if not guidelines:
        guidelines.append("""
        🥗 GENERAL HEALTHY RULES:
        - Balanced meals with protein, complex carbs, healthy fats
        - HIGH in vegetables and fruits (5+ servings per day)
        - AVOID processed foods, excess sugar, trans fats, sugary drinks
        - YES to lean proteins, whole grains, healthy fats
        """)
    
    return "\n".join(guidelines)
# ============ GEMINI AI MEAL PLAN GENERATION ============
def generate_ai_meal_plan(user_profile):
    """
    Generate a disease-specific meal plan using Google Gemini AI
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        age = user_profile.get('age', '30')
        gender = user_profile.get('gender', 'M')
        height = user_profile.get('height_cm', '170')
        weight = user_profile.get('weight_kg', '70')
        bmi = user_profile.get('bmi', '24')
        bmi_category = user_profile.get('bmi_category', 'Healthy Weight')
        tdee = user_profile.get('tdee', '2000')
        diseases = user_profile.get('diseases', 'None') or 'None'
        allergies = user_profile.get('allergies', 'None') or 'None'
        diet_preference = user_profile.get('diet_preference', 'non-vegetarian')
        meal_preference = user_profile.get('meal_preference', '3_meals')
        disliked_foods = user_profile.get('disliked_foods', 'None') or 'None'
        cuisine_preference = user_profile.get('cuisine_preference', 'Indian')
        plan_duration = user_profile.get('plan_duration', 30)
        
        meal_structure = {
            '2_meals': ['brunch', 'dinner'],
            '3_meals': ['breakfast', 'lunch', 'dinner'],
            '4_meals': ['breakfast', 'lunch', 'snack', 'dinner'],
            '5_meals': ['breakfast', 'morning_snack', 'lunch', 'afternoon_snack', 'dinner']
        }
        meals_list = meal_structure.get(meal_preference, ['breakfast', 'lunch', 'dinner'])
        
        disease_guidelines = get_disease_guidelines(diseases)
        
        prompt = f"""You are a certified medical nutrition expert. Create a COMPLETE {plan_duration}-day meal plan for a patient with {diseases}.

PATIENT HEALTH PROFILE:
- Age: {age}, Gender: {gender}
- Height: {height}cm, Weight: {weight}kg
- BMI: {bmi} ({bmi_category})
- Daily Calorie Target: {tdee} kcal
- Medical Conditions: {diseases}
- Allergies: {allergies}
- Diet Preference: {diet_preference}
- Disliked Foods: {disliked_foods}
- Cuisine Preference: {cuisine_preference}
- Meals per day: {', '.join(meals_list)}

{disease_guidelines}

CRITICAL REQUIREMENTS:
1. EVERY single meal MUST be medically appropriate for {diseases}
2. For EACH ingredient, provide a SPECIFIC health benefit related to their condition
3. If an ingredient is contraindicated for {diseases}, DO NOT include it
4. Total daily calories must be within 100 calories of {tdee}
5. Create EXACTLY {plan_duration} days of meals (Day 1 to Day {plan_duration})

Return ONLY valid JSON. NO explanations, NO markdown, ONLY JSON:

{{
  "day1": {{
    "breakfast": {{
      "name": "Specific meal name",
      "description": "Brief description (1 sentence)",
      "calories": 350,
      "ingredients": [
        {{"name": "Ingredient 1", "benefit": "Specific benefit for their condition"}},
        {{"name": "Ingredient 2", "benefit": "Specific benefit for their condition"}}
      ]
    }},
    "lunch": {{...}},
    "dinner": {{...}}
  }},
  "day2": {{...}},
  ...
  "day{plan_duration}": {{...}},
  "meal_tips": "3-4 specific health tips for managing {diseases} through diet"
}}

Generate all {plan_duration} days now. Each day must have {len(meals_list)} meals: {', '.join(meals_list)}"""

        print(f"🤖 Gemini AI generating {plan_duration}-day meal plan for {diseases}...")
        response = model.generate_content(prompt)
        
        json_match = re.search(r'\{[\s\S]*\}', response.text)
        if json_match:
            meal_plan = json.loads(json_match.group())
            print(f"✅ AI successfully generated {len(meal_plan)-1} days of meals")
            return meal_plan
        else:
            print("❌ No JSON found in Gemini response")
            return None
            
    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
        return None

# ==================== PAGE ROUTES ====================
@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/assessment')
def assessment_page():
    if 'user_email' not in session:
        return redirect('/login')
    return render_template('assessment.html')

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, email, name, assessment_completed FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return redirect('/login')
    
    cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user['id'],))
    profile_row = cursor.fetchone()
    
    # Create profile dictionary with all values
    profile = {}
    if profile_row:
        for key in profile_row.keys():
            profile[key] = profile_row[key]
    
    # Force set values if they exist in database but not in profile dict
    if profile_row:
        profile['bmi'] = profile_row['bmi'] if profile_row['bmi'] else 26.7
        profile['tdee'] = profile_row['tdee'] if profile_row['tdee'] else 1550
        profile['bmi_category'] = profile_row['bmi_category'] if profile_row['bmi_category'] else 'Overweight'
        profile['weight_kg'] = profile_row['weight_kg'] if profile_row['weight_kg'] else 70.0
    
    # Calculate target weight
    target_weight = None
    weight_to_go = None
    goal_advice = ""
    
    if profile.get('height_cm') and profile.get('weight_kg'):
        height_m = profile.get('height_cm') / 100
        target_bmi = 22
        target_weight = round(target_bmi * (height_m * height_m), 1)
        current_weight = profile.get('weight_kg')
        weight_to_go = round(abs(current_weight - target_weight), 1)
        
        bmi = profile.get('bmi')
        if bmi:
            if bmi < 18.5:
                goal_advice = "🎯 Focus on nutrient-dense foods to reach a healthy weight."
            elif bmi < 25:
                goal_advice = "🎉 Great job! Maintain your current weight with balanced meals."
            elif bmi < 30:
                goal_advice = "💪 Small calorie deficit will help you reach your goal weight."
            else:
                goal_advice = "🌟 Consult a doctor for a personalized plan to reach your goal."
    
    conn.close()
    
    # Get greeting
    from datetime import datetime
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Morning"
    elif hour < 17:
        greeting = "Afternoon"
    elif hour < 21:
        greeting = "Evening"
    else:
        greeting = "Night"
    
    user_dict = {
        'id': user['id'],
        'email': user['email'],
        'name': user['name'],
        'assessment_completed': user['assessment_completed'],
        'profile': profile
    }
    
    return render_template('dashboard.html', 
                         user=user_dict, 
                         greeting=greeting,
                         target_weight=target_weight,
                         weight_to_go=weight_to_go,
                         goal_advice=goal_advice)
    

@app.route('/meal-planner')
def meal_planner():
    if 'user_email' not in session:
        return redirect('/login')
    
    # Get day parameter from URL (default to current day)
    requested_day = request.args.get('day', None)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, email, name, assessment_completed FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return redirect('/login')
    
    cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user['id'],))
    profile_row = cursor.fetchone()
    profile = dict(profile_row) if profile_row else {}
    
    plan_duration = profile.get('plan_duration', 30)
    current_day = 1
    start_date = profile.get('meal_plan_start_date')
    
    # FIX: Better date calculation
    if start_date:
        try:
            # Parse the start date
            if isinstance(start_date, str):
                # Handle different date formats
                if 'T' in start_date:
                    start_date_str = start_date.split('T')[0]
                else:
                    start_date_str = start_date[:10]
                start = datetime.strptime(start_date_str, '%Y-%m-%d')
            else:
                start = start_date
            
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Ensure start is date-only for comparison
            if hasattr(start, 'hour'):
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Calculate days passed
            days_passed = (today - start).days
            
            # Current day is days_passed + 1 (Day 1 is the start date)
            current_day = days_passed + 1
            
            # Clamp to valid range
            if current_day > plan_duration:
                current_day = plan_duration
            if current_day < 1:
                current_day = 1
                
            print(f"📅 Start date: {start}, Today: {today}, Days passed: {days_passed}, Current day: {current_day}")
            
        except Exception as e:
            print(f"Error calculating day: {e}")
            current_day = 1
    else:
        # No start date - set it to today
        today_date_only = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            UPDATE user_profiles 
            SET meal_plan_start_date = ?
            WHERE user_id = ?
        ''', (today_date_only, user['id']))
        conn.commit()
        current_day = 1
        print(f"📅 Set new start date to: {today_date_only}")
    
    # If a specific day was requested, use it
    display_day = int(requested_day) if requested_day and requested_day.isdigit() else current_day
    
    # Generate meal plan only if user completed assessment and no plan exists
    if user['assessment_completed']:
        ai_meal_plan = profile.get('ai_meal_plan')
        if not ai_meal_plan:
            print(f"🔄 Generating AI meal plan for {plan_duration} days...")
            ai_meal_plan = generate_ai_meal_plan(profile)
            if ai_meal_plan:
                cursor.execute('''
                    UPDATE user_profiles 
                    SET ai_meal_plan = ?, ai_meal_plan_generated = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (json.dumps(ai_meal_plan), user['id']))
                conn.commit()
                print(f"✅ AI meal plan saved for {plan_duration} days!")
        else:
            print(f"📋 Using existing meal plan from database")
    
    conn.close()
    
    user_dict = {
        'id': user['id'],
        'email': user['email'],
        'name': user['name'],
        'assessment_completed': user['assessment_completed'],
        'profile': profile,
        'tdee': profile.get('tdee', 2000),
        'meal_preference': profile.get('meal_preference', '3_meals'),
        'plan_duration': profile.get('plan_duration', 30)
    }
    
    return render_template('meal_planner.html', user=user_dict, current_day=display_day)

@app.route('/profile')
def profile_page():
    if 'user_email' not in session:
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, email, name, phone, created_at FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return redirect('/login')
    
    cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user['id'],))
    profile_row = cursor.fetchone()
    conn.close()
    
    profile = dict(profile_row) if profile_row else {}
    
    default_values = {
        'activity_level': 'Moderate',
        'diet_preference': 'Both',
        'meal_preference': '3_meals',
        'cuisine_preference': 'Indian',
        'tdee': 2000
    }
    
    for key, default in default_values.items():
        if key not in profile or not profile[key]:
            profile[key] = default
    
    user_dict = {
        'id': user['id'],
        'email': user['email'],
        'name': user['name'],
        'phone': user['phone'],
        'created_at': user['created_at'],
        'profile': profile
    }
    
    return render_template('profile.html', user=user_dict)

@app.route('/shopping')
def shopping():
    if 'user_email' not in session:
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, email, name FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return redirect('/login')
    
    user_dict = {'id': user['id'], 'email': user['email'], 'name': user['name']}
    return render_template('shopping.html', user=user_dict)

@app.route('/recipes')
def recipes():
    if 'user_email' not in session:
        return redirect('/login')
    return render_template('recipes.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ==================== API ROUTES ====================
@app.route('/api/register', methods=['POST'])
def register_api():
    try:
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        password = data.get('password')
        
        if not all([name, email, phone, password]):
            return jsonify({'success': False, 'message': 'All fields required'})
        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'})
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Email already registered'})
        
        cursor.execute('''
            INSERT INTO users (email, name, phone, password, assessment_completed)
            VALUES (?, ?, ?, ?, 0)
        ''', (email, name, phone, password))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        session['user_email'] = email
        session['user_id'] = user_id
        
        return jsonify({'success': True, 'redirect': '/assessment'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/login', methods=['POST'])
def login_api():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, email, name, password, assessment_completed FROM users WHERE email = ? OR phone = ?', 
                       (username, username))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        if user['password'] != password:
            return jsonify({'success': False, 'message': 'Incorrect password'})
        
        session['user_email'] = user['email']
        session['user_id'] = user['id']
        
        if user['assessment_completed']:
            return jsonify({'success': True, 'redirect': '/dashboard'})
        else:
            return jsonify({'success': True, 'redirect': '/assessment'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/submit-assessment', methods=['POST'])
def submit_assessment():
    if 'user_email' not in session:
        return redirect('/login')
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return redirect('/login')
        
        user_id = user['id']
        
        age = int(request.form.get('age'))
        gender = request.form.get('gender')
        height_cm = float(request.form.get('height_cm'))
        weight_kg = float(request.form.get('weight_kg'))
        activity_level = request.form.get('activity_level')
        sleep_quality = request.form.get('sleep_quality', 'average')
        diseases = request.form.get('diseases', '')
        allergies = request.form.get('allergies', '')
        medications = request.form.get('medications', '')
        diet_preference = request.form.get('diet_preference', 'both')
        meal_preference = request.form.get('meal_preference', '3_meals')
        disliked_foods = request.form.get('disliked_foods', '')
        cuisine_preference = request.form.get('cuisine_preference', '')
        plan_duration = int(request.form.get('plan_duration', 30))
        preferred_fruits = request.form.get('preferred_fruits', '')
        preferred_vegetables = request.form.get('preferred_vegetables', '')
        available_ingredients = request.form.get('available_ingredients', '')
        
        height_m = height_cm / 100
        bmi = round(weight_kg / (height_m ** 2), 1)
        
        if gender == 'M':
            bmr = round(10 * weight_kg + 6.25 * height_cm - 5 * age + 5)
        else:
            bmr = round(10 * weight_kg + 6.25 * height_cm - 5 * age - 161)
        
        activity_factors = {'sedentary': 1.2, 'light': 1.375, 'moderate': 1.55, 'active': 1.725, 'very_active': 1.9}
        tdee = round(bmr * activity_factors.get(activity_level, 1.2))
        
        if bmi < 18.5:
            bmi_category = 'Underweight'
            goal_advice = "Focus on nutrient-dense foods"
        elif bmi < 25:
            bmi_category = 'Healthy Weight'
            goal_advice = "Great job! Maintain your current weight"
        elif bmi < 30:
            bmi_category = 'Overweight'
            goal_advice = "Small calorie deficit for healthy weight loss"
        else:
            bmi_category = 'Obese'
            goal_advice = "Consult a doctor for personalized plan"
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_profiles (
                user_id, age, gender, height_cm, weight_kg, bmi, bmr, tdee,
                bmi_category, activity_level, sleep_quality, diseases, allergies,
                medications, diet_preference, meal_preference, disliked_foods,
                cuisine_preference, plan_duration, preferred_fruits, preferred_vegetables,
                available_ingredients, goal_advice
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, age, gender, height_cm, weight_kg, bmi, bmr, tdee,
            bmi_category, activity_level, sleep_quality, diseases, allergies,
            medications, diet_preference, meal_preference, disliked_foods,
            cuisine_preference, plan_duration, preferred_fruits, preferred_vegetables,
            available_ingredients, goal_advice
        ))
        
        cursor.execute('UPDATE users SET assessment_completed = 1 WHERE id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        
        return redirect('/dashboard')
        
    except Exception as e:
        print(f"Assessment error: {e}")
        return redirect('/assessment')


# ============ AUTOCOMPLETE ROUTES ============
@app.route('/autocomplete/medical', methods=['GET'])
def autocomplete_medical():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])
    suggestions = [item for item in MEDICAL_CONDITIONS if query in item.lower()]
    return jsonify(suggestions[:15])

@app.route('/autocomplete/allergies', methods=['GET'])
def autocomplete_allergies():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])
    suggestions = [item for item in ALLERGIES if query in item.lower()]
    return jsonify(suggestions[:15])

@app.route('/autocomplete/medications', methods=['GET'])
def autocomplete_medications():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])
    suggestions = [item for item in MEDICATIONS if query in item.lower()]
    return jsonify(suggestions[:15])

@app.route('/autocomplete/fruits', methods=['GET'])
def autocomplete_fruits():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])
    suggestions = [item for item in FRUITS if query in item.lower()]
    return jsonify(suggestions[:15])

@app.route('/autocomplete/vegetables', methods=['GET'])
def autocomplete_vegetables():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])
    suggestions = [item for item in VEGETABLES if query in item.lower()]
    return jsonify(suggestions[:15])

@app.route('/autocomplete/disliked-foods', methods=['GET'])
def autocomplete_disliked_foods():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])
    disliked_foods = ['Bitter gourd', 'Mushroom', 'Spring onion', 'Capsicum', 'Brinjal', 'Okra', 'Tofu', 'Liver', 'Coriander', 'Fenugreek']
    suggestions = [item for item in disliked_foods if query in item.lower()]
    return jsonify(suggestions[:15])

@app.route('/autocomplete/cuisines', methods=['GET'])
def autocomplete_cuisines():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])
    cuisines = ['Indian', 'South Indian', 'North Indian', 'Chinese', 'Italian', 'Mexican', 'Japanese', 'Thai', 'Mediterranean', 'Continental']
    suggestions = [item for item in cuisines if query in item.lower()]
    return jsonify(suggestions[:15])

# ============ AI MEAL PLAN API ENDPOINTS ============
@app.route('/api/get-meal-plan', methods=['GET'])
def api_get_meal_plan():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = None
    try:
        conn = get_db()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        cursor.execute('SELECT ai_meal_plan FROM user_profiles WHERE user_id = ?', (user['id'],))
        row = cursor.fetchone()
        
        if row and row['ai_meal_plan']:
            meal_plan = json.loads(row['ai_meal_plan'])
            return jsonify({'success': True, 'meal_plan': meal_plan})
        
        return jsonify({'success': False, 'message': 'No meal plan found'})
        
    except Exception as e:
        print(f"Error in get_meal_plan: {e}")
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn:
            conn.close()

@app.route('/api/regenerate-meal-plan', methods=['POST'])
def api_regenerate_meal_plan():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, assessment_completed FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user or not user['assessment_completed']:
        conn.close()
        return jsonify({'success': False, 'message': 'Complete assessment first'})
    
    cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user['id'],))
    profile_row = cursor.fetchone()
    profile = dict(profile_row) if profile_row else {}
    
    # Clear old tracking data when regenerating
    cursor.execute('DELETE FROM meal_tracking WHERE user_id = ?', (user['id'],))
    cursor.execute('DELETE FROM user_ranks WHERE user_id = ?', (user['id'],))
    cursor.execute('DELETE FROM weight_tracking WHERE user_id = ?', (user['id'],))
    
    meal_plan = generate_ai_meal_plan(profile)
    
    if meal_plan:
        cursor.execute('''
            UPDATE user_profiles 
            SET ai_meal_plan = ?, ai_meal_plan_generated = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (json.dumps(meal_plan), user['id']))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'meal_plan': meal_plan})
    
    conn.close()
    return jsonify({'success': False, 'message': 'AI generation failed'})

@app.route('/api/save-meal-plan', methods=['POST'])
def save_meal_plan():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    try:
        data = request.get_json()
        meal_plan = data.get('meal_plan')
        
        if not meal_plan:
            return jsonify({'success': False, 'message': 'No meal plan data'})
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': 'User not found'})
        
        cursor.execute('''
            UPDATE user_profiles 
            SET ai_meal_plan = ?, ai_meal_plan_generated = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (json.dumps(meal_plan), user['id']))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Meal plan saved'})
        
    except Exception as e:
        print(f"Error saving meal plan: {e}")
        return jsonify({'success': False, 'message': str(e)})

# ============ REPLACE MEAL ENDPOINT ============
@app.route('/api/replace-meal', methods=['POST'])
def replace_meal():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    data = request.get_json()
    meal_type = data.get('meal_type')
    current_meal_name = data.get('current_meal_name')
    reason = data.get('reason')
    reason_text = data.get('reason_text', 'User wants a different meal')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user['id'],))
    profile_row = cursor.fetchone()
    profile = dict(profile_row) if profile_row else {}
    conn.close()
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        diseases = profile.get('diseases', 'None')
        allergies = profile.get('allergies', 'None')
        diet_preference = profile.get('diet_preference', 'non-vegetarian')
        disliked_foods = profile.get('disliked_foods', 'None')
        cuisine_preference = profile.get('cuisine_preference', 'Indian')
        tdee = profile.get('tdee', 2000)
        
        disease_guidelines = get_disease_guidelines(diseases)
        
        prompt = f"""You are a medical nutrition expert. Suggest ONE replacement {meal_type} meal.

USER HEALTH PROFILE:
- Medical Conditions: {diseases}
- Allergies: {allergies}
- Diet Preference: {diet_preference}
- Disliked Foods: {disliked_foods}
- Preferred Cuisine: {cuisine_preference}
- Daily Calorie Target: {tdee} kcal

CURRENT MEAL TO REPLACE: {current_meal_name}
USER'S REASON: {reason_text}

{disease_guidelines}

REQUIREMENTS:
1. Suggest a COMPLETELY DIFFERENT meal from "{current_meal_name}"
2. The meal MUST be medically appropriate for {diseases}
3. Include 2-3 key ingredients with SPECIFIC health benefits for their condition
4. Calories should be between 250-600 for {meal_type}

Return ONLY valid JSON with this structure:
{{
  "name": "Unique meal name (different from current)",
  "description": "Brief description of the meal",
  "calories": 400,
  "reason": "Why this meal is beneficial for their medical condition",
  "ingredients": [
    {{"name": "Ingredient 1", "benefit": "Specific health benefit for their condition"}},
    {{"name": "Ingredient 2", "benefit": "Specific health benefit for their condition"}}
  ]
}}"""

        print(f"🤖 Gemini AI generating replacement for {meal_type}...")
        response = model.generate_content(prompt)
        
        json_match = re.search(r'\{[\s\S]*\}', response.text)
        if json_match:
            replacement = json.loads(json_match.group())
            print(f"✅ Gemini AI replacement: {replacement.get('name')}")
            return jsonify({'success': True, 'replacement': replacement})
        else:
            print("❌ No JSON found in Gemini response")
            return jsonify({'success': False, 'message': 'Could not generate replacement'})
            
    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
        return jsonify({'success': False, 'message': str(e)})

# ============ TRACKING ENDPOINTS ============
@app.route('/api/track-meal', methods=['POST'])
def track_meal():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = None
    try:
        data = request.get_json()
        meal_name = data.get('meal_name')
        calories = data.get('calories', 0)
        completed = data.get('completed', False)
        date = datetime.now().strftime('%Y-%m-%d')
        
        if not meal_name:
            return jsonify({'success': False, 'message': 'Meal name required'})
        
        conn = get_db()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        user_id = user['id']
        
        if completed:
            # Check if already tracked today
            cursor.execute('''
                SELECT id FROM meal_tracking 
                WHERE user_id = ? AND date = ? AND meal_name = ? AND consumed = 1
            ''', (user_id, date, meal_name))
            
            existing = cursor.fetchone()
            
            if existing:
                return jsonify({'success': False, 'already_tracked': True, 'message': 'Meal already tracked today'})
            
            # Insert the meal as completed
            cursor.execute('''
                INSERT INTO meal_tracking (user_id, date, meal_name, calories, consumed)
                VALUES (?, ?, ?, ?, 1)
            ''', (user_id, date, meal_name, calories))
            
            conn.commit()
            
            print(f"✅ Meal tracked: {meal_name} ({calories} cal) for user {user_id} on {date}")
        
        return jsonify({'success': True, 'message': 'Meal tracked successfully'})
        
    except Exception as e:
        print(f"Error in track_meal: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn:
            conn.close()

@app.route('/api/track-water', methods=['POST'])
def track_water():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    try:
        data = request.get_json()
        amount_liters = data.get('amount', 0)
        # Use provided date or current date
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        if amount_liters <= 0:
            return jsonify({'success': False, 'message': 'Invalid amount'})
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': 'User not found'})
        
        user_id = user['id']
        
        # Check if record exists for this date
        cursor.execute('''
            SELECT id, amount_liters FROM water_tracking 
            WHERE user_id = ? AND date = ?
        ''', (user_id, date))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing record
            new_amount = existing['amount_liters'] + amount_liters
            cursor.execute('''
                UPDATE water_tracking 
                SET amount_liters = ?, tracked_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_amount, existing['id']))
        else:
            # Insert new record
            cursor.execute('''
                INSERT INTO water_tracking (user_id, date, amount_liters, tracked_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, date, amount_liters))
        
        conn.commit()
        conn.close()
        
        print(f"Water tracked: {amount_liters}L on {date} for user {user_id}")
        return jsonify({'success': True, 'message': 'Water tracked'})
        
    except Exception as e:
        print(f"Error tracking water: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/update-progress', methods=['POST'])
def update_progress():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    try:
        data = request.get_json()
        points = data.get('points', 0)
        reason = data.get('reason', '')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': 'User not found'})
        
        user_id = user['id']
        
        cursor.execute('''
            INSERT INTO user_ranks (user_id, total_points)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                total_points = total_points + ?
        ''', (user_id, points, points))
        
        cursor.execute('''
            INSERT INTO points_transactions (user_id, points, reason, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, points, reason))
        
        conn.commit()
        
        cursor.execute('SELECT total_points FROM user_ranks WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        total = result['total_points'] if result else 0
        
        conn.close()
        return jsonify({'success': True, 'total_points': total})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/change-password', methods=['POST'])
def change_password():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    try:
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'})
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT password FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user or user['password'] != current_password:
            conn.close()
            return jsonify({'success': False, 'message': 'Current password is incorrect'})
        
        cursor.execute('UPDATE users SET password = ? WHERE email = ?', (new_password, session['user_email']))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/generate-recipe', methods=['POST'])
def generate_recipe():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    data = request.get_json()
    meal_name = data.get('meal_name', '')
    diet_preference = data.get('diet_preference', 'vegetarian')
    cuisine = data.get('cuisine', 'Indian')
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        prompt = f"""Generate a detailed recipe for "{meal_name}".

User Preferences:
- Diet: {diet_preference}
- Cuisine: {cuisine}

Return ONLY valid JSON with this structure:
{{
  "name": "{meal_name}",
  "description": "Brief description of the dish",
  "calories": 400,
  "prep_time": "15 min",
  "cook_time": "20 min",
  "difficulty": "Easy",
  "ingredients": [
    "Ingredient 1 with quantity",
    "Ingredient 2 with quantity"
  ],
  "instructions": [
    "Step 1: ...",
    "Step 2: ..."
  ],
  "nutrition": {{
    "protein": "15g",
    "carbs": "45g",
    "fats": "12g",
    "fiber": "8g"
  }},
  "tips": "One helpful cooking tip",
  "youtube_search": "{meal_name} recipe"
}}"""

        response = model.generate_content(prompt)
        json_match = re.search(r'\{[\s\S]*\}', response.text)
        
        if json_match:
            recipe = json.loads(json_match.group())
            return jsonify({'success': True, 'recipe': recipe})
        else:
            return jsonify({'success': False, 'message': 'Failed to generate recipe'})
            
    except Exception as e:
        print(f"Error generating recipe: {e}")
        return jsonify({'success': False, 'message': str(e)})

 

# ============ RECOMMENDATION API ENDPOINTS ============
@app.route('/api/get-daily-recommendation', methods=['GET'])
def get_daily_recommendation():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user['id'],))
    profile_row = cursor.fetchone()
    profile = dict(profile_row) if profile_row else {}
    
    meal_plan = profile.get('ai_meal_plan')
    if not meal_plan:
        conn.close()
        return jsonify({'success': False, 'message': 'No meal plan found'})
    
    try:
        meal_plan_data = json.loads(meal_plan) if isinstance(meal_plan, str) else meal_plan
        
        start_date = profile.get('meal_plan_start_date')
        plan_duration = profile.get('plan_duration', 30)
        current_day = 1
        
        if start_date:
            try:
                start = datetime.fromisoformat(start_date)
                today = datetime.now()
                days_passed = (today - start).days
                current_day = days_passed + 1
                if current_day > plan_duration:
                    current_day = plan_duration
                if current_day < 1:
                    current_day = 1
            except Exception:
                current_day = 1
        
        day_key = f'day{current_day}'
        today_meals = meal_plan_data.get(day_key, {})
        
        if not today_meals:
            conn.close()
            return jsonify({'success': False, 'message': f'No meals found for Day {current_day}'})
        
        meal_config = {
            'breakfast': {'time': '8:00 AM', 'icon': '☀️', 'order': 1, 'name': 'Breakfast'},
            'morning_snack': {'time': '10:30 AM', 'icon': '🍌', 'order': 2, 'name': 'Morning Snack'},
            'lunch': {'time': '1:00 PM', 'icon': '🌤️', 'order': 3, 'name': 'Lunch'},
            'afternoon_snack': {'time': '4:00 PM', 'icon': '🍎', 'order': 4, 'name': 'Afternoon Snack'},
            'snack': {'time': '4:00 PM', 'icon': '🍎', 'order': 4, 'name': 'Snack'},
            'dinner': {'time': '7:00 PM', 'icon': '🌙', 'order': 5, 'name': 'Dinner'},
            'brunch': {'time': '10:30 AM', 'icon': '🍽️', 'order': 2, 'name': 'Brunch'}
        }
        
        all_meals = []
        for meal_type, meal in today_meals.items():
            if meal and isinstance(meal, dict) and meal.get('name'):
                config = meal_config.get(meal_type, {'time': '12:00 PM', 'icon': '🍽️', 'order': 99, 'name': meal_type.capitalize()})
                ingredients = meal.get('ingredients', [])
                if not ingredients:
                    ingredients = [{'name': meal.get('name', 'Healthy meal'), 'benefit': 'Nutritious and good for your health'}]
                
                all_meals.append({
                    'type': meal_type,
                    'display_name': config['name'],
                    'time': config['time'],
                    'icon': config['icon'],
                    'order': config['order'],
                    'name': meal.get('name', 'Unknown'),
                    'description': meal.get('description', 'A healthy meal recommended for you'),
                    'calories': meal.get('calories', 300),
                    'ingredients': ingredients
                })
        
        all_meals.sort(key=lambda x: x['order'])
        
        meal_preference = profile.get('meal_preference', '3_meals')
        meal_counts = {'2_meals': 2, '3_meals': 3, '4_meals': 4, '5_meals': 5}
        total_meals_today = meal_counts.get(meal_preference, 3)
        
        completed_meals = 0
        today_date = datetime.now().strftime('%Y-%m-%d')
        
        conn.close()
        
        return jsonify({
            'success': True,
            'day': current_day,
            'total_meals': total_meals_today,
            'completed_meals': completed_meals,
            'meals': all_meals
        })
        
    except Exception as e:
        conn.close()
        print(f"Error getting daily recommendation: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/get-weekly-meals', methods=['GET'])
def get_weekly_meals():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user['id'],))
    profile_row = cursor.fetchone()
    profile = dict(profile_row) if profile_row else {}
    conn.close()
    
    meal_plan = profile.get('ai_meal_plan')
    if not meal_plan:
        return jsonify({'success': False, 'message': 'No meal plan found'})
    
    try:
        meal_plan_data = json.loads(meal_plan) if isinstance(meal_plan, str) else meal_plan
        
        start_date = profile.get('meal_plan_start_date')
        plan_duration = profile.get('plan_duration', 30)
        current_day = 1
        
        if start_date:
            try:
                start = datetime.fromisoformat(start_date)
                today = datetime.now()
                days_passed = (today - start).days
                current_day = days_passed + 1
                if current_day > plan_duration:
                    current_day = plan_duration
                if current_day < 1:
                    current_day = 1
            except Exception:
                current_day = 1
        
        weekly_meals = []
        for i in range(7):
            day_num = current_day + i
            if day_num > plan_duration:
                break
            
            day_key = f'day{day_num}'
            day_meals = meal_plan_data.get(day_key, {})
            
            if day_meals:
                main_meal = None
                for mt in ['lunch', 'dinner']:
                    if mt in day_meals and day_meals[mt]:
                        main_meal = day_meals[mt]
                        break
                
                if not main_meal:
                    for mt, meal in day_meals.items():
                        if meal and isinstance(meal, dict) and meal.get('name'):
                            main_meal = meal
                            break
                
                if main_meal:
                    weekly_meals.append({
                        'day': day_num,
                        'is_today': i == 0,
                        'meal_name': main_meal.get('name', 'Unknown'),
                        'description': main_meal.get('description', ''),
                        'calories': main_meal.get('calories', 0),
                        'ingredients': main_meal.get('ingredients', [])
                    })
        
        return jsonify({'success': True, 'weekly_meals': weekly_meals, 'current_day': current_day})
        
    except Exception as e:
        print(f"Error getting weekly meals: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/test-daily', methods=['GET'])
def test_daily():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('SELECT ai_meal_plan, meal_plan_start_date, plan_duration, meal_preference FROM user_profiles WHERE user_id = ?', (user['id'],))
    row = cursor.fetchone()
    conn.close()
    
    if not row or not row['ai_meal_plan']:
        return jsonify({'success': False, 'message': 'No meal plan found', 'has_plan': False})
    
    try:
        meal_plan = json.loads(row['ai_meal_plan'])
        return jsonify({
            'success': True,
            'has_plan': True,
            'meal_plan_keys': list(meal_plan.keys())[:10],
            'start_date': row['meal_plan_start_date'],
            'plan_duration': row['plan_duration'],
            'meal_preference': row['meal_preference']
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/get-missing-ingredients', methods=['GET'])
def get_missing_ingredients():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('SELECT ai_meal_plan, available_ingredients FROM user_profiles WHERE user_id = ?', (user['id'],))
    row = cursor.fetchone()
    conn.close()
    
    missing_ingredients = []
    
    if row and row['ai_meal_plan']:
        try:
            meal_plan = json.loads(row['ai_meal_plan']) if isinstance(row['ai_meal_plan'], str) else row['ai_meal_plan']
            home_ingredients = row['available_ingredients'].lower() if row['available_ingredients'] else ''
            
            all_ingredients = {}
            
            for day_key, day_meals in meal_plan.items():
                if day_key.startswith('day'):
                    day_num = day_key.replace('day', '')
                    
                    for meal_type, meal in day_meals.items():
                        if meal and isinstance(meal, dict):
                            if 'ingredients' in meal and meal['ingredients']:
                                for ing in meal['ingredients']:
                                    if isinstance(ing, dict):
                                        ing_name = ing.get('name', '').lower()
                                    else:
                                        ing_name = str(ing).lower()
                                    
                                    if ing_name and ing_name not in home_ingredients:
                                        if ing_name not in all_ingredients:
                                            all_ingredients[ing_name] = {
                                                'name': ing.get('name') if isinstance(ing, dict) else str(ing),
                                                'meal': f'Day {day_num} {meal_type}',
                                                'benefit': ing.get('benefit', 'Essential ingredient') if isinstance(ing, dict) else 'Essential ingredient'
                                            }
                            else:
                                meal_name = meal.get('name', '')
                                words = meal_name.lower().split()
                                common_ingredients = ['rice', 'dal', 'vegetable', 'chicken', 'paneer', 'egg', 'fish', 'quinoa', 'oats', 'millet']
                                for word in words:
                                    if word in common_ingredients and word not in home_ingredients:
                                        if word not in all_ingredients:
                                            all_ingredients[word] = {
                                                'name': word.capitalize(),
                                                'meal': f'Day {day_num} {meal_type}',
                                                'benefit': 'Essential ingredient for this meal'
                                            }
            
            missing_ingredients = list(all_ingredients.values())
            
        except Exception as e:
            print(f"Error parsing meal plan: {e}")
    
    if not missing_ingredients:
        default_ingredients = [
            {'name': 'Rice', 'meal': 'Multiple meals', 'benefit': 'Staple grain for many dishes'},
            {'name': 'Vegetables', 'meal': 'Multiple meals', 'benefit': 'Essential for balanced nutrition'},
            {'name': 'Spices', 'meal': 'Multiple meals', 'benefit': 'Adds flavor and health benefits'}
        ]
        return jsonify({'success': True, 'ingredients': default_ingredients})
    
    return jsonify({'success': True, 'ingredients': missing_ingredients[:20]})

# ============ WEIGHT TRACKING ENDPOINTS ============
@app.route('/api/get-weight-history', methods=['GET'])
def get_weight_history():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    user_id = user['id']
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='weight_tracking'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weight_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                weight_kg REAL NOT NULL,
                recorded_date DATE NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, recorded_date)
            )
        ''')
        conn.commit()
    
    cursor.execute('''
        SELECT recorded_date, weight_kg, notes 
        FROM weight_tracking 
        WHERE user_id = ? 
        ORDER BY recorded_date ASC
    ''', (user_id,))
    
    rows = cursor.fetchall()
    
    weight_history = []
    for row in rows:
        weight_history.append({
            'date': row['recorded_date'],
            'weight': row['weight_kg'],
            'notes': row['notes'] or ''
        })
    
    if not weight_history:
        cursor.execute('SELECT weight_kg FROM user_profiles WHERE user_id = ?', (user_id,))
        profile = cursor.fetchone()
        
        if profile and profile['weight_kg']:
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            weight_history.append({
                'date': today,
                'weight': profile['weight_kg'],
                'notes': 'Initial weight'
            })
            cursor.execute('''
                INSERT OR REPLACE INTO weight_tracking (user_id, weight_kg, recorded_date, notes)
                VALUES (?, ?, ?, ?)
            ''', (user_id, profile['weight_kg'], today, 'Initial weight'))
            conn.commit()
    
    conn.close()
    
    return jsonify({'success': True, 'weight_history': weight_history})

@app.route('/api/update-weight', methods=['POST'])
def update_weight():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    data = request.get_json()
    weight_kg = data.get('weight_kg')
    recorded_date = data.get('recorded_date')
    notes = data.get('notes', '')
    
    if not weight_kg:
        return jsonify({'success': False, 'message': 'Weight is required'})
    
    if not recorded_date:
        from datetime import datetime
        recorded_date = datetime.now().strftime('%Y-%m-%d')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    user_id = user['id']
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='weight_tracking'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weight_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                weight_kg REAL NOT NULL,
                recorded_date DATE NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, recorded_date)
            )
        ''')
        conn.commit()
    
    cursor.execute('''
        INSERT OR REPLACE INTO weight_tracking (user_id, weight_kg, recorded_date, notes)
        VALUES (?, ?, ?, ?)
    ''', (user_id, weight_kg, recorded_date, notes))
    
    cursor.execute('''
        UPDATE user_profiles SET weight_kg = ?
        WHERE user_id = ?
    ''', (weight_kg, user_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Weight updated successfully'})

 

@app.route('/api/advance-day', methods=['POST'])
def advance_day():
    """Advance user's meal plan to next day"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    try:
        data = request.get_json()
        new_day = data.get('new_day')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': 'User not found'})
        
        # Calculate new start date that makes current_day = new_day
        from datetime import timedelta
        today = datetime.now()
        days_to_subtract = new_day - 1
        new_start_date = today - timedelta(days=days_to_subtract)
        
        cursor.execute('''
            UPDATE user_profiles 
            SET meal_plan_start_date = ?
            WHERE user_id = ?
        ''', (new_start_date.isoformat(), user['id']))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'new_day': new_day, 'message': f'Advanced to Day {new_day}'})
        
    except Exception as e:
        print(f"Error advancing day: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/user-journey-stats', methods=['GET'])
def get_user_journey_stats():
    """Get user's lifetime journey stats (total meals, total points)"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    user_id = user['id']
    
    # Count UNIQUE meals (prevent duplicates from counting twice)
    cursor.execute('''
        SELECT COUNT(DISTINCT date || '_' || meal_name) as total 
        FROM meal_tracking 
        WHERE user_id = ? AND consumed = 1
    ''', (user_id,))
    result = cursor.fetchone()
    total_meals = result['total'] if result else 0
    
    # Total points earned
    cursor.execute('SELECT total_points FROM user_ranks WHERE user_id = ?', (user_id,))
    points_row = cursor.fetchone()
    total_points = points_row['total_points'] if points_row else 0
    
    conn.close()
    
    return jsonify({
        'success': True,
        'total_meals': total_meals,
        'total_points': total_points
    })
    
@app.route('/api/weight-prediction', methods=['GET'])
def get_weight_prediction():
    """Calculate weight prediction based on user's progress"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    user_id = user['id']
    
    # Get weight history
    cursor.execute('''
        SELECT recorded_date, weight_kg 
        FROM weight_tracking 
        WHERE user_id = ? 
        ORDER BY recorded_date ASC
    ''', (user_id,))
    
    weights = cursor.fetchall()
    
    # Get user profile
    cursor.execute('SELECT weight_kg, height_cm, age, gender, tdee, bmr FROM user_profiles WHERE user_id = ?', (user_id,))
    profile = cursor.fetchone()
    
    conn.close()
    
    current_weight = profile['weight_kg'] if profile else 70
    height = profile['height_cm'] if profile else 170
    tdee = profile['tdee'] if profile else 2000
    bmr = profile['bmr'] if profile else 1400
    
    # Calculate target weight (BMI 22 - healthy)
    height_m = height / 100
    target_weight = round(22 * (height_m * height_m), 1)
    
    # Calculate ACTUAL weekly rate from user's history (if available)
    weekly_loss_rate = 0.5  # Default healthy rate
    weekly_gain_rate = 0.3   # Default healthy rate
    confidence = "medium"
    
    if weights and len(weights) >= 2:
        # Calculate actual rate from user's data
        oldest_weight = weights[0]['weight_kg']
        oldest_date = datetime.fromisoformat(weights[0]['recorded_date'])
        newest_weight = weights[-1]['weight_kg']
        newest_date = datetime.fromisoformat(weights[-1]['recorded_date'])
        
        days_diff = (newest_date - oldest_date).days
        if days_diff > 0:
            actual_rate = (oldest_weight - newest_weight) / (days_diff / 7)
            if abs(actual_rate) > 0.1:  # Use actual rate if significant
                if actual_rate > 0:
                    weekly_loss_rate = actual_rate
                else:
                    weekly_gain_rate = abs(actual_rate)
                confidence = "high"
    
    # Determine direction
    if current_weight > target_weight:
        kg_to_go = current_weight - target_weight
        weeks_needed = kg_to_go / weekly_loss_rate
        target_date = datetime.now() + timedelta(days=weeks_needed * 7)
        rate = -weekly_loss_rate
        direction = "lose"
    else:
        kg_to_go = target_weight - current_weight
        weeks_needed = kg_to_go / weekly_gain_rate
        target_date = datetime.now() + timedelta(days=weeks_needed * 7)
        rate = weekly_gain_rate
        direction = "gain"
    
    # Generate predictions for key milestones
    predictions = []
    milestone_days = [0, 7, 14, 30, 60, 90, 120, 180]
    
    # Add prediction for target date
    days_to_target = (target_date - datetime.now()).days
    if days_to_target > 0 and days_to_target not in milestone_days:
        milestone_days.append(days_to_target)
    
    milestone_days.sort()
    
    for days in milestone_days:
        pred_date = datetime.now() + timedelta(days=days)
        pred_weight = current_weight + (rate * (days / 7))
        predictions.append({
            'date': pred_date.strftime('%Y-%m-%d'),
            'display_date': pred_date.strftime('%b %d'),
            'weight': round(max(30, min(150, pred_weight)), 1),
            'is_target': days == days_to_target if days_to_target > 0 else False
        })
    
    # Calculate milestones (significant weight points)
    milestones = []
    milestone_weights = [target_weight]
    
    if direction == "lose":
        milestone_weights.append(round(target_weight + 5, 1))
        milestone_weights.append(round(target_weight + 10, 1))
    else:
        milestone_weights.append(round(target_weight - 5, 1))
        milestone_weights.append(round(target_weight - 10, 1))
    
    for mw in milestone_weights:
        if (direction == "lose" and mw < current_weight) or (direction == "gain" and mw > current_weight):
            weeks = abs(mw - current_weight) / (weekly_loss_rate if direction == "lose" else weekly_gain_rate)
            milestone_date = datetime.now() + timedelta(days=weeks * 7)
            milestones.append({
                'weight': round(mw, 1),
                'date': milestone_date.strftime('%b %d'),
                'weeks': round(weeks, 1)
            })
    
    return jsonify({
        'success': True,
        'current_weight': current_weight,
        'target_weight': target_weight,
        'kg_to_go': round(kg_to_go, 1),
        'direction': direction,
        'target_date': target_date.strftime('%b %d'),
        'predictions': predictions,
        'milestones': milestones,
        'weekly_rate': round(abs(rate), 2),
        'confidence': confidence,
        'bmr': bmr,
        'tdee': tdee
    })
    
@app.route('/api/weekly-stats', methods=['GET'])
def get_weekly_stats():
    """Get weekly meal and water stats for charts"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    user_id = user['id']
    
    from datetime import datetime, timedelta
    
    # Get today's date
    today = datetime.now()
    
    # Calculate start of week (Monday)
    start_of_week = today - timedelta(days=today.weekday())
    
    meals_data = [0, 0, 0, 0, 0, 0, 0]
    water_data = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    
    for i in range(7):
        # Calculate date for each day of the week
        current_date = start_of_week + timedelta(days=i)
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Meals completed on this day
        cursor.execute('''
            SELECT COUNT(*) as count FROM meal_tracking 
            WHERE user_id = ? AND date = ? AND consumed = 1
        ''', (user_id, date_str))
        result = cursor.fetchone()
        meals_data[i] = result['count'] if result else 0
        
        # Water intake on this day
        cursor.execute('''
            SELECT amount_liters FROM water_tracking 
            WHERE user_id = ? AND date = ?
        ''', (user_id, date_str))
        water_result = cursor.fetchone()
        water_data[i] = round(water_result['amount_liters'] if water_result else 0, 1)
    
    conn.close()
    
    print(f"Weekly Stats - Water: {water_data}")
    
    return jsonify({
        'success': True,
        'meals': meals_data,
        'water': water_data,
        'days': day_names
    })
    
@app.route('/api/progress-data', methods=['GET'])
def get_progress_data():
    """Get user's progress data including points, rank, transactions"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    user_id = user['id']
    
    # Get user stats
    cursor.execute('''
        SELECT total_points, current_streak, best_streak, total_meals_completed 
        FROM user_ranks WHERE user_id = ?
    ''', (user_id,))
    stats_row = cursor.fetchone()
    
    stats = {
        'total_points': stats_row['total_points'] if stats_row else 0,
        'current_streak': stats_row['current_streak'] if stats_row else 0,
        'best_streak': stats_row['best_streak'] if stats_row else 0,
        'total_meals_completed': stats_row['total_meals_completed'] if stats_row else 0
    }
    
    # Get points transactions
    cursor.execute('''
        SELECT points, reason, created_at FROM points_transactions 
        WHERE user_id = ? ORDER BY created_at DESC LIMIT 20
    ''', (user_id,))
    transactions = cursor.fetchall()
    
    # Get total users count for leaderboard
    cursor.execute('SELECT COUNT(*) as count FROM user_ranks')
    total_users = cursor.fetchone()['count']
    
    # Get user position
    cursor.execute('''
        SELECT COUNT(*) + 1 as position FROM user_ranks 
        WHERE total_points > (SELECT total_points FROM user_ranks WHERE user_id = ?)
    ''', (user_id,))
    position_row = cursor.fetchone()
    user_position = position_row['position'] if position_row else 1
    
    # Get leaderboard (top 5)
    cursor.execute('''
        SELECT u.name, ur.total_points 
        FROM user_ranks ur
        JOIN users u ON ur.user_id = u.id
        ORDER BY ur.total_points DESC LIMIT 5
    ''')
    leaderboard = [{'name': row['name'], 'total_points': row['total_points']} for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'success': True,
        'stats': stats,
        'transactions': [dict(t) for t in transactions],
        'total_users': total_users,
        'user_position': user_position,
        'leaderboard': leaderboard
    })

@app.route('/api/redeem-reward', methods=['POST'])
def redeem_reward():
    """Redeem points for rewards"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    data = request.get_json()
    reward_name = data.get('reward_name')
    points_cost = data.get('points_cost')
    
    if not reward_name or not points_cost:
        return jsonify({'success': False, 'message': 'Invalid reward data'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    user_id = user['id']
    
    # Check if user has enough points
    cursor.execute('SELECT total_points FROM user_ranks WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    current_points = result['total_points'] if result else 0
    
    if current_points < points_cost:
        conn.close()
        return jsonify({'success': False, 'message': f'Need {points_cost - current_points} more points!'})
    
    # Deduct points
    cursor.execute('''
        UPDATE user_ranks SET total_points = total_points - ? WHERE user_id = ?
    ''', (points_cost, user_id))
    
    # Record transaction
    cursor.execute('''
        INSERT INTO points_transactions (user_id, points, reason, created_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ''', (user_id, -points_cost, f'Redeemed: {reward_name}'))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': f'Successfully redeemed {reward_name}!'})

@app.route('/help-faq')
def help_faq():
    if 'user_email' not in session:
        return redirect('/login')
    return render_template('help_faq.html')

    
@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    """AI Chatbot for Help & FAQ"""
    if 'user_email' not in session:
        return jsonify({'reply': 'Please log in to use the assistant.'})
    
    data = request.get_json()
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({'reply': 'Please ask me something!'})
    
    try:
        # Use the same model as your meal planner
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        prompt = f"""You are a friendly AI assistant for MealMate AI, a health and meal planning app.

IMPORTANT RULES:
- Keep answers short (2-3 sentences maximum)
- Be helpful and encouraging
- If unsure, say "Let me check that for you"

COMMON QUESTIONS AND ANSWERS:
Q: How do I complete a meal?
A: Go to Meal Planner page, find your meal, and click the "Mark as Completed (+10 pts)" button. You'll earn 10 points instantly!

Q: How do I earn points?
A: Each completed meal gives you 10 points. Complete all 3 meals daily to earn bonus points!

Q: How do I redeem rewards?
A: Go to Shopping section, choose any reward, and click "Redeem" if you have enough points.

Q: How to update my weight?
A: Go to Profile page, update your weight in the form, and click Save Changes.

Q: What is TDEE?
A: TDEE is your daily calorie target. It's calculated from your BMR and activity level during assessment.

Q: How to track water?
A: On the Meal Planner page, use the water tracker card to add 250ml, 500ml, or 1L.

USER QUESTION: {user_message}

ANSWER (short, 2-3 sentences, helpful):"""
        
        response = model.generate_content(prompt)
        reply = response.text.strip()
        
        # If response is empty or too short, provide a fallback
        if not reply or len(reply) < 5:
            reply = get_fallback_response(user_message)
        
        return jsonify({'reply': reply})
        
    except Exception as e:
        print(f"Chatbot error: {e}")
        # Provide a helpful fallback response based on keywords
        fallback_reply = get_fallback_response(user_message)
        return jsonify({'reply': fallback_reply})

def get_fallback_response(question):
    """Fallback responses when Gemini API fails"""
    q = question.lower()
    
    if 'complete' in q and 'meal' in q:
        return "✅ To complete a meal, go to Meal Planner → Click 'Mark as Completed (+10 pts)' on any meal. You'll earn 10 points!"
    
    elif 'point' in q or 'earn' in q:
        return "🎁 You earn 10 points for each completed meal! Complete all 3 daily meals for bonus points."
    
    elif 'redeem' in q or 'reward' in q:
        return "🛒 Go to Shopping section → Choose a reward → Click 'Redeem'. Make sure you have enough points!"
    
    elif 'weight' in q:
        return "⚖️ Update your weight in Profile page. Click 'Update in Profile →' under the Current Weight card."
    
    elif 'water' in q:
        return "💧 Track water on Meal Planner page using the water tracker card. Target is 2.5L per day!"
    
    elif 'tdee' in q or 'calorie' in q:
        return "📊 TDEE is your daily calorie target. It was calculated during your health assessment based on your activity level."
    
    elif 'bmi' in q:
        return "📏 BMI is calculated from your height and weight. Check your Dashboard to see your current BMI."
    
    elif 'meal plan' in q or 'regenerate' in q:
        return "🔄 To regenerate your meal plan, go to Meal Planner and click the 'Regenerate Meal Plan' button."
    
    elif 'streak' in q:
        return "🔥 Your streak counts consecutive days you've completed all meals. Keep going!"
    
    else:
        return "💚 I'm here to help! You can ask me about: completing meals, earning points, redeeming rewards, updating weight, tracking water, or using the meal planner. What would you like to know?"


@app.route('/api/get-todays-missing-ingredients', methods=['GET'])
def get_todays_missing_ingredients():
    """Get missing ingredients for TODAY'S meals only"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    user_id = user['id']
    
    # Get user profile and meal plan
    cursor.execute('SELECT ai_meal_plan, available_ingredients, meal_preference, meal_plan_start_date, plan_duration FROM user_profiles WHERE user_id = ?', (user_id,))
    profile_row = cursor.fetchone()
    
    if not profile_row or not profile_row['ai_meal_plan']:
        conn.close()
        return jsonify({'success': False, 'message': 'No meal plan found'})
    
    # Calculate current day
    from datetime import datetime, timedelta
    start_date = profile_row['meal_plan_start_date']
    plan_duration = profile_row['plan_duration'] or 30
    current_day = 1
    
    if start_date:
        try:
            start = datetime.fromisoformat(start_date)
            today = datetime.now()
            days_passed = (today - start).days
            current_day = days_passed + 1
            if current_day > plan_duration:
                current_day = plan_duration
            if current_day < 1:
                current_day = 1
        except Exception:
            current_day = 1
    
    meal_plan = json.loads(profile_row['ai_meal_plan']) if isinstance(profile_row['ai_meal_plan'], str) else profile_row['ai_meal_plan']
    day_key = f'day{current_day}'
    today_meals = meal_plan.get(day_key, {})
    
    home_ingredients = profile_row['available_ingredients'].lower() if profile_row['available_ingredients'] else ''
    
    # Define common ingredients mapping for meal names
    ingredient_mapping = {
        'upma': ['semolina', 'vegetables', 'cashews'],
        'idli': ['rice', 'urad dal'],
        'dosa': ['rice', 'urad dal'],
        'sambar': ['toor dal', 'vegetables', 'tamarind'],
        'chutney': ['coconut', 'chana dal', 'green chili'],
        'pulao': ['rice', 'vegetables', 'spices'],
        'biryani': ['rice', 'vegetables', 'spices', 'yogurt'],
        'raita': ['yogurt', 'cucumber'],
        'dal tadka': ['toor dal', 'tomato', 'onion', 'garlic', 'ginger', 'spices'],
        'curry': ['onion', 'tomato', 'garlic', 'ginger', 'spices'],
        'bhurji': ['eggs', 'onion', 'tomato', 'spices'],
        'roti': ['wheat flour'],
        'kebabs': ['meat', 'spices', 'onion'],
        'salad': ['cucumber', 'tomato', 'onion'],
        'paneer': ['paneer', 'onion', 'tomato', 'spices'],
        'chicken': ['chicken', 'onion', 'tomato', 'spices', 'ginger', 'garlic'],
        'fish': ['fish', 'turmeric', 'spices'],
        'egg': ['eggs'],
        'spinach': ['spinach'],
        'lentil': ['lentils', 'onion', 'tomato', 'spices'],
        'rice': ['rice'],
        'quinoa': ['quinoa'],
        'oats': ['oats']
    }
    
    all_ingredients = {}
    
    for meal_type, meal in today_meals.items():
        if meal and isinstance(meal, dict) and meal.get('name'):
            meal_name = meal.get('name', '').lower()
            ingredients = []
            
            # Try to get ingredients from meal JSON first
            if 'ingredients' in meal and meal['ingredients']:
                for ing in meal['ingredients']:
                    if isinstance(ing, dict):
                        ing_name = ing.get('name', '')
                    else:
                        ing_name = str(ing)
                    if ing_name:
                        ingredients.append(ing_name.lower())
            
            # If no ingredients in JSON, use mapping based on meal name
            if not ingredients:
                for key, ing_list in ingredient_mapping.items():
                    if key in meal_name:
                        ingredients.extend(ing_list)
                        break
            
            # If still no ingredients, add generic ones based on meal type
            if not ingredients:
                if 'breakfast' in meal_type:
                    ingredients = ['bread', 'eggs', 'milk']
                elif 'lunch' in meal_type:
                    ingredients = ['rice', 'dal', 'vegetables']
                elif 'dinner' in meal_type:
                    ingredients = ['roti', 'vegetables', 'dal']
                else:
                    ingredients = ['vegetables', 'spices', 'oil']
            
            for ing in ingredients:
                ing_clean = ing.strip().lower()
                if ing_clean and ing_clean not in home_ingredients:
                    if ing_clean not in all_ingredients:
                        all_ingredients[ing_clean] = {
                            'name': ing_clean.capitalize(),
                            'meal': f'{meal_type.capitalize()} - {meal.get("name", "Unknown")[:30]}',
                            'benefit': 'Essential ingredient for this meal'
                        }
    
    conn.close()
    
    missing_ingredients = list(all_ingredients.values())
    
    if not missing_ingredients:
        default_ingredients = [
            {'name': 'Fresh Vegetables', 'meal': 'Today\'s meals', 'benefit': 'Essential for balanced nutrition'},
            {'name': 'Spices', 'meal': 'Today\'s meals', 'benefit': 'Adds flavor and health benefits'},
            {'name': 'Cooking Oil', 'meal': 'Today\'s meals', 'benefit': 'Healthy cooking essential'}
        ]
        return jsonify({'success': True, 'ingredients': default_ingredients, 'current_day': current_day})
    
    return jsonify({'success': True, 'ingredients': missing_ingredients[:20], 'current_day': current_day})


 #============ COMPLETED MEALS API ENDPOINTS ============

@app.route('/api/get-completed-meals', methods=['GET'])
def get_completed_meals():
    """Get all completed meals for the logged-in user"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    # Get specific date if provided, otherwise get all
    filter_date = request.args.get('date', None)
    
    conn = None
    try:
        conn = get_db()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        user_id = user['id']
        
        # Build query based on date filter
        if filter_date:
            query = '''
                SELECT meal_name, calories, date, id
                FROM meal_tracking 
                WHERE user_id = ? AND consumed = 1 AND date = ?
                ORDER BY date DESC
            '''
            cursor.execute(query, (user_id, filter_date))
        else:
            query = '''
                SELECT meal_name, calories, date, id
                FROM meal_tracking 
                WHERE user_id = ? AND consumed = 1
                ORDER BY date DESC
            '''
            cursor.execute(query, (user_id,))
        
        rows = cursor.fetchall()
        
        # Create response with meal identifiers
        completed_meals = []
        completed_meals_by_name = {}
        
        for row in rows:
            # Create a unique meal identifier
            meal_clean = row['meal_name'].strip().lower()
            # Remove extra spaces and special characters for matching
            import re
            meal_clean = re.sub(r'[^\w\s]', '', meal_clean)
            meal_clean = ' '.join(meal_clean.split())  # Normalize spaces
            
            meal_info = {
                'id': row['id'],
                'name': row['meal_name'],
                'clean_name': meal_clean,
                'calories': row['calories'],
                'date': row['date']
            }
            completed_meals.append(meal_info)
            
            # Store by clean name for easy lookup
            completed_meals_by_name[meal_clean] = meal_info
        
        print(f"📊 Loaded {len(completed_meals)} completed meals for user {user_id}")
        
        return jsonify({
            'success': True, 
            'completed_meals': completed_meals,
            'completed_meals_by_name': completed_meals_by_name,
            'count': len(completed_meals)
        })
        
    except Exception as e:
        print(f"Error in get_completed_meals: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn:
            conn.close()


@app.route('/api/mark-meal-complete', methods=['POST'])
def mark_meal_complete():
    """Mark a meal as completed"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    try:
        data = request.get_json()
        meal_name = data.get('meal_name')
        calories = data.get('calories', 0)
        meal_date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        meal_id = data.get('meal_id', None)
        
        if not meal_name:
            return jsonify({'success': False, 'message': 'Meal name required'})
        
        conn = get_db()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection failed'})
        
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': 'User not found'})
        
        user_id = user['id']
        
        # Check if already tracked today
        cursor.execute('''
            SELECT id FROM meal_tracking 
            WHERE user_id = ? AND date = ? AND meal_name = ? AND consumed = 1
        ''', (user_id, meal_date, meal_name))
        
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return jsonify({
                'success': False, 
                'already_tracked': True, 
                'message': 'Meal already tracked today'
            })
        
        # Insert the meal as completed
        cursor.execute('''
            INSERT INTO meal_tracking (user_id, date, meal_name, calories, consumed)
            VALUES (?, ?, ?, ?, 1)
        ''', (user_id, meal_date, meal_name, calories))
        
        new_id = cursor.lastrowid
        
        # Update points
        cursor.execute('''
            INSERT INTO user_ranks (user_id, total_points, total_meals_completed)
            VALUES (?, 10, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                total_points = total_points + 10,
                total_meals_completed = total_meals_completed + 1
        ''', (user_id,))
        
        cursor.execute('''
            INSERT INTO points_transactions (user_id, points, reason)
            VALUES (?, 10, ?)
        ''', (user_id, f'Completed: {meal_name}'))
        
        conn.commit()
        
        # Get updated points
        cursor.execute('SELECT total_points FROM user_ranks WHERE user_id = ?', (user_id,))
        points_row = cursor.fetchone()
        total_points = points_row['total_points'] if points_row else 10
        
        conn.close()
        
        # Create clean name for UI matching
        import re
        meal_clean = re.sub(r'[^\w\s]', '', meal_name.lower())
        meal_clean = ' '.join(meal_clean.split())
        
        return jsonify({
            'success': True, 
            'message': 'Meal tracked successfully',
            'total_points': total_points,
            'meal_id': new_id,
            'meal_clean_name': meal_clean
        })
        
    except Exception as e:
        print(f"Error in mark_meal_complete: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/check-meal-status', methods=['GET'])
def check_meal_status():
    """Check if a specific meal is completed"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    meal_name = request.args.get('meal_name')
    meal_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    if not meal_name:
        return jsonify({'success': False, 'message': 'Meal name required'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('''
        SELECT id FROM meal_tracking 
        WHERE user_id = ? AND date = ? AND meal_name = ? AND consumed = 1
    ''', (user['id'], meal_date, meal_name))
    
    completed = cursor.fetchone() is not None
    conn.close()
    
    return jsonify({'success': True, 'completed': completed})


@app.route('/api/update-profile', methods=['POST'])
def update_profile():
    """Update user profile with all fields and recalculate BMI/BMR/TDEE"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    data = request.get_json()
    name = data.get('name')
    phone = data.get('phone')
    age = data.get('age')
    gender = data.get('gender')
    height_cm = data.get('height_cm')
    weight_kg = data.get('weight_kg')
    diseases = data.get('diseases')
    allergies = data.get('allergies')
    medications = data.get('medications')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Update users table
    cursor.execute('UPDATE users SET name = ?, phone = ? WHERE email = ?', (name, phone, session['user_email']))
    
    # Get user_id
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if user and height_cm and weight_kg and age:
        # Calculate BMI
        height_m = float(height_cm) / 100
        bmi = round(float(weight_kg) / (height_m * height_m), 1)
        
        # Calculate BMI Category
        if bmi < 18.5:
            bmi_category = 'Underweight'
        elif bmi < 25:
            bmi_category = 'Healthy Weight'
        elif bmi < 30:
            bmi_category = 'Overweight'
        else:
            bmi_category = 'Obese'
        
        # Calculate BMR (Mifflin-St Jeor Equation)
        if gender == 'M':
            bmr = round(10 * float(weight_kg) + 6.25 * float(height_cm) - 5 * int(age) + 5)
        else:
            bmr = round(10 * float(weight_kg) + 6.25 * float(height_cm) - 5 * int(age) - 161)
        
        # Calculate TDEE (Sedentary activity by default)
        tdee = round(bmr * 1.2)
        
        # Update or insert into user_profiles with all calculated fields
        cursor.execute('''
            INSERT OR REPLACE INTO user_profiles (
                user_id, age, gender, height_cm, weight_kg, bmi, bmi_category, bmr, tdee,
                diseases, allergies, medications
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user['id'], age, gender, height_cm, weight_kg, bmi, bmi_category, bmr, tdee,
              diseases, allergies, medications))
    elif user:
        # Update without recalculating BMI
        cursor.execute('''
            INSERT OR REPLACE INTO user_profiles (
                user_id, age, gender, height_cm, weight_kg, diseases, allergies, medications
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user['id'], age, gender, height_cm, weight_kg, diseases, allergies, medications))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Profile updated successfully'})

@app.route('/api/todays-meal-calories', methods=['GET'])
def get_todays_meal_calories():
    """Get today's meal calories for dashboard"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('SELECT ai_meal_plan, meal_plan_start_date, plan_duration, meal_preference FROM user_profiles WHERE user_id = ?', (user['id'],))
    row = cursor.fetchone()
    
    if not row or not row['ai_meal_plan']:
        conn.close()
        return jsonify({'success': False, 'message': 'No meal plan found'})
    
    # Calculate current day
    from datetime import datetime, timedelta
    start_date = row['meal_plan_start_date']
    plan_duration = row['plan_duration'] or 30
    current_day = 1
    
    if start_date:
        try:
            start = datetime.fromisoformat(start_date) if isinstance(start_date, str) else start_date
            today = datetime.now()
            days_passed = (today - start).days
            current_day = days_passed + 1
            if current_day > plan_duration:
                current_day = plan_duration
            if current_day < 1:
                current_day = 1
        except Exception:
            current_day = 1
    
    meal_plan = json.loads(row['ai_meal_plan']) if isinstance(row['ai_meal_plan'], str) else row['ai_meal_plan']
    day_key = f'day{current_day}'
    today_meals = meal_plan.get(day_key, {})
    
    # Get meal preference to determine meal types
    meal_preference = row['meal_preference'] or '3_meals'
    meal_map = {
        '2_meals': {'breakfast': 'brunch', 'lunch': 'dinner', 'dinner': 'dinner'},
        '3_meals': {'breakfast': 'breakfast', 'lunch': 'lunch', 'dinner': 'dinner'},
        '4_meals': {'breakfast': 'breakfast', 'lunch': 'lunch', 'dinner': 'dinner'},
        '5_meals': {'breakfast': 'breakfast', 'lunch': 'lunch', 'dinner': 'dinner'}
    }
    
    breakfast_cal = 0
    lunch_cal = 0
    dinner_cal = 0
    
    for meal_type, meal in today_meals.items():
        if meal and isinstance(meal, dict):
            if 'breakfast' in meal_type.lower():
                breakfast_cal = meal.get('calories', 0)
            elif 'lunch' in meal_type.lower():
                lunch_cal = meal.get('calories', 0)
            elif 'dinner' in meal_type.lower():
                dinner_cal = meal.get('calories', 0)
    
    conn.close()
    
    return jsonify({
        'success': True,
        'breakfast': breakfast_cal,
        'lunch': lunch_cal,
        'dinner': dinner_cal,
        'day': current_day
    })
@app.route('/api/user-status', methods=['GET'])
def user_status():
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, email, name, assessment_completed FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return jsonify({
            'success': True,
            'user': dict(user)
        })
    else:
        return jsonify({'success': False})
    
@app.route('/api/personalized-news', methods=['GET'])
def personalized_news():
    """Generate personalized health news based on user's health profile using separate API key"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user['id'],))
    profile_row = cursor.fetchone()
    conn.close()
    
    profile = dict(profile_row) if profile_row else {}
    
    # Get user health info
    diseases = profile.get('diseases', 'General Health')
    if not diseases or diseases == '':
        diseases = 'General Health'
    
    age = profile.get('age', '30')
    bmi = profile.get('bmi', '24')
    bmi_category = profile.get('bmi_category', 'Healthy')
    diet_preference = profile.get('diet_preference', 'both')
    
    try:
        # Use SEPARATE API key for news
        model = get_news_model()
        
        prompt = f"""You are a health news curator. Generate 6 personalized health news headlines and summaries for a user with these health characteristics:

USER HEALTH PROFILE:
- Age: {age}
- BMI: {bmi} ({bmi_category})
- Medical Conditions: {diseases}
- Diet Preference: {diet_preference}

REQUIREMENTS:
1. Each news item must be RELEVANT to their medical condition (if any)
2. If they have specific conditions (Diabetes, Hypertension, etc.), focus on news about managing that condition
3. If no conditions, provide general health, nutrition, and wellness news
4. Make headlines engaging and realistic
5. Keep summaries under 120 characters
6. Use credible source names (e.g., Harvard Health, Mayo Clinic, WHO, etc.)

Return ONLY valid JSON with this structure:
{{
  "articles": [
    {{
      "title": "News headline here",
      "description": "Brief 100-120 character summary",
      "source": "Credible Health Source Name"
    }}
  ]
}}

Generate 6 articles. Do not include any markdown or explanations, ONLY the JSON."""

        print(f"🤖 Generating personalized news for conditions: {diseases} using NEWS API key")
        response = model.generate_content(prompt)
        
        json_match = re.search(r'\{[\s\S]*\}', response.text)
        if json_match:
            news_data = json.loads(json_match.group())
            articles = news_data.get('articles', [])
            print(f"✅ Generated {len(articles)} personalized news articles")
            return jsonify({'success': True, 'articles': articles})
        else:
            print("❌ No JSON found, using fallback")
            return jsonify({'success': True, 'articles': get_fallback_news(diseases)})
            
    except Exception as e:
        print(f"❌ News generation error: {e}")
        return jsonify({'success': True, 'articles': get_fallback_news(diseases)})

def get_fallback_news(condition):
    """Return condition-specific fallback news"""
    condition_lower = condition.lower()
    
    if 'diabetes' in condition_lower:
        return [
            {"title": "New Study Shows Millets Can Help Control Blood Sugar", "description": "Research confirms that replacing rice with millets reduces diabetes risk by 30%", "source": "Diabetes India"},
            {"title": "Walking After Meals: The Simple Habit That Lowers Glucose", "description": "Just 10 minutes of walking after eating can significantly reduce blood sugar spikes", "source": "Healthline"},
            {"title": "Intermittent Fasting Shows Promise for Type 2 Diabetes", "description": "Time-restricted eating helps improve insulin sensitivity", "source": "Medical News Today"},
            {"title": "Fiber-Rich Diet Linked to Better Diabetes Management", "description": "High-fiber foods help stabilize blood sugar levels throughout the day", "source": "American Diabetes Association"},
            {"title": "New Insulin Breakthrough: Once-Weekly Injection Shows Promise", "description": "Clinical trials show effectiveness of weekly insulin for type 2 diabetes", "source": "The Lancet"},
            {"title": "Plant-Based Diet May Reduce Diabetes Risk by 50%", "description": "Large-scale study confirms benefits of plant-based eating patterns", "source": "Nutrition Reviews"}
        ]
    elif 'hypertension' in condition_lower or 'high blood pressure' in condition_lower:
        return [
            {"title": "Low-Sodium Diet Benefits: New Research Confirms", "description": "Reducing salt intake lowers blood pressure as effectively as medication", "source": "American Heart Association"},
            {"title": "Beetroot Juice: Natural Way to Lower Blood Pressure", "description": "Daily beetroot consumption shows significant reduction in hypertension", "source": "Nutrition Journal"},
            {"title": "Stress Management Techniques That Lower BP", "description": "Meditation and deep breathing exercises effectively reduce blood pressure", "source": "Harvard Health"},
            {"title": "Potassium-Rich Foods Help Control Hypertension", "description": "Bananas, sweet potatoes, and spinach can naturally lower blood pressure", "source": "Mayo Clinic"},
            {"title": "DASH Diet Ranked Best for Heart Health Again", "description": "Dietary Approaches to Stop Hypertension continues to top rankings", "source": "US News Health"},
            {"title": "Morning vs Evening Exercise for Blood Pressure", "description": "Timing of physical activity may impact BP control effectiveness", "source": "Journal of Hypertension"}
        ]
    elif 'heart' in condition_lower or 'cholesterol' in condition_lower:
        return [
            {"title": "Mediterranean Diet Boosts Heart Health, Study Confirms", "description": "Rich in olive oil and nuts, this diet reduces cardiovascular events", "source": "New England Journal of Medicine"},
            {"title": "Omega-3 Supplements: Benefits for Heart Disease", "description": "Fish oil may reduce triglycerides and inflammation in heart patients", "source": "American College of Cardiology"},
            {"title": "Walnuts: Small Snack, Big Heart Benefits", "description": "Daily handful of walnuts improves cholesterol levels and vessel health", "source": "Circulation Research"},
            {"title": "Air Pollution Linked to Higher Heart Attack Risk", "description": "New study shows correlation between poor air quality and cardiac events", "source": "WHO"},
            {"title": "Plant Sterols: Natural Way to Lower Cholesterol", "description": "Fortified foods with plant sterols can reduce LDL cholesterol by 10%", "source": "European Heart Journal"},
            {"title": "Sleep Apnea Treatment Improves Heart Health", "description": "CPAP therapy shows cardiovascular benefits for heart disease patients", "source": "American Journal of Cardiology"}
        ]
    else:
        return [
            {"title": "Mediterranean Diet Named Best Overall Diet for 2025", "description": "Rich in olive oil, nuts, and fish, this diet tops health rankings again", "source": "US News Health"},
            {"title": "Morning Exercise Better for Weight Loss, Study Finds", "description": "Working out between 7-9 AM shows better results for metabolic health", "source": "Obesity Society"},
            {"title": "Sleep Quality Linked to Better Immune Function", "description": "Getting 7-8 hours of sleep strengthens your body's defense system", "source": "Sleep Research Society"},
            {"title": "Plant-Based Proteins: Benefits Beyond Meat", "description": "Lentils, chickpeas, and tofu provide excellent protein with added fiber benefits", "source": "Nutrition Today"},
            {"title": "Hydration Tips: How Much Water Do You Really Need?", "description": "Individual water needs vary based on activity, climate, and body size", "source": "Mayo Clinic"},
            {"title": "Mindful Eating: The Secret to Better Digestion", "description": "Eating slowly without distractions improves nutrient absorption and satisfaction", "source": "Wellness Journal"}
        ]
        


@app.route('/fitness')
def fitness():
    if 'user_email' not in session:
        return redirect('/login')
    return render_template('fitness.html')

 

@app.route('/api/user-health-profile', methods=['GET'])
def user_health_profile():
    """Get user's health profile for personalized fitness recommendations"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('''
        SELECT age, bmi, bmi_category, diseases, activity_level 
        FROM user_profiles WHERE user_id = ?
    ''', (user['id'],))
    
    profile = cursor.fetchone()
    conn.close()
    
    if profile:
        return jsonify({
            'success': True,
            'age': profile['age'] or 30,
            'bmi': profile['bmi'] or 24,
            'bmi_category': profile['bmi_category'] or 'Normal',
            'diseases': profile['diseases'] or 'None',
            'activity_level': profile['activity_level'] or 'Moderate'
        })
    
    return jsonify({'success': True, 'age': 30, 'bmi': 24, 'bmi_category': 'Normal', 'diseases': 'None', 'activity_level': 'Moderate'})


@app.route('/api/personalized-fitness-plan', methods=['GET'])
def personalized_fitness_plan():
    """Generate AI-powered personalized fitness plan using Gemini"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('''
        SELECT age, gender, height_cm, weight_kg, bmi, bmi_category, 
               diseases, allergies, activity_level, diet_preference, sleep_quality
        FROM user_profiles WHERE user_id = ?
    ''', (user['id'],))
    
    profile = cursor.fetchone()
    conn.close()
    
    age = profile['age'] if profile else 30
    gender = profile['gender'] if profile else 'M'
    bmi = profile['bmi'] if profile else 24
    bmi_category = profile['bmi_category'] if profile else 'Normal'
    diseases = profile['diseases'] if profile and profile['diseases'] else 'None'
    allergies = profile['allergies'] if profile and profile['allergies'] else 'None'
    activity_level = profile['activity_level'] if profile else 'Moderate'
    sleep_quality = profile['sleep_quality'] if profile else 'average'
    
    try:
        # Use the fitness model (separate API key)
        if GEMINI_API_KEY_FITNESS:
            import google.generativeai as genai_fitness
            genai_fitness.configure(api_key=GEMINI_API_KEY_FITNESS)
            model = genai_fitness.GenerativeModel('gemini-2.5-flash-lite')
        else:
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            print("⚠️ Using main API key for fitness")
        
        prompt = f"""You are an expert fitness trainer. Create a personalized fitness plan for a user with:

- Age: {age}
- Gender: {gender}
- BMI: {bmi} ({bmi_category})
- Medical Conditions: {diseases}
- Allergies: {allergies}
- Activity Level: {activity_level}

Return ONLY valid JSON:
{{
  "primary_category": "Yoga/Cardio/Strength/HIIT/Walking/Chair/Stretching",
  "daily_duration": "X minutes",
  "recommendation_reason": "Brief explanation",
  "exercises": [
    {{"name": "Exercise name", "duration": "30 sec or 12 reps", "difficulty": "Beginner/Intermediate/Advanced", "precautions": "Safety tip"}}
  ],
  "warnings": ["Warning 1", "Warning 2"],
  "weekly_schedule": {{
    "monday": "Workout", "tuesday": "Workout", "wednesday": "Rest",
    "thursday": "Workout", "friday": "Workout", "saturday": "Workout", "sunday": "Rest"
  }}
}}"""
        
        response = model.generate_content(prompt)
        json_match = re.search(r'\{[\s\S]*\}', response.text)
        if json_match:
            plan = json.loads(json_match.group())
            print(f"✅ Fitness plan generated: {plan.get('primary_category')}")
            return jsonify({'success': True, 'plan': plan})
        else:
            return jsonify({'success': True, 'plan': get_fitness_fallback(age, diseases)})
            
    except Exception as e:
        print(f"❌ Fitness plan error: {e}")
        return jsonify({'success': True, 'plan': get_fitness_fallback(age, diseases)})

def get_fitness_fallback(age, diseases):
    """Fallback fitness plan if Gemini API fails"""
    diseases_lower = str(diseases).lower()
    
    if age >= 60 or 'heart' in diseases_lower:
        return {
            "primary_category": "Chair Exercises",
            "daily_duration": "15 minutes",
            "recommendation_reason": "Low-impact exercises for safety and mobility",
            "exercises": [
                {"name": "Seated March", "duration": "30 sec", "difficulty": "Beginner", "precautions": "Keep back straight"},
                {"name": "Seated Leg Raise", "duration": "10 reps", "difficulty": "Beginner", "precautions": "Move slowly"},
                {"name": "Seated Arm Circle", "duration": "15 circles", "difficulty": "Beginner", "precautions": "Keep shoulders relaxed"}
            ],
            "warnings": ["Avoid sudden movements", "Stop if you feel pain", "Stay hydrated"],
            "weekly_schedule": {"monday": "Chair", "tuesday": "Walk", "wednesday": "Rest", "thursday": "Chair", "friday": "Stretch", "saturday": "Walk", "sunday": "Rest"}
        }
    elif 'diabetes' in diseases_lower or 'hypertension' in diseases_lower:
        return {
            "primary_category": "Cardio",
            "daily_duration": "25 minutes",
            "recommendation_reason": "Regular exercise helps manage blood pressure and blood sugar",
            "exercises": [
                {"name": "Brisk Walking", "duration": "15 min", "difficulty": "Beginner", "precautions": "Check levels before exercise"},
                {"name": "Bodyweight Squat", "duration": "12 reps", "difficulty": "Beginner", "precautions": "Keep chest up"},
                {"name": "Arm Circles", "duration": "20 circles", "difficulty": "Beginner", "precautions": "Keep shoulders relaxed"}
            ],
            "warnings": ["Monitor blood sugar", "Stay hydrated", "Don't overexert"],
            "weekly_schedule": {"monday": "Cardio", "tuesday": "Walk", "wednesday": "Rest", "thursday": "Cardio", "friday": "Strength", "saturday": "Walk", "sunday": "Rest"}
        }
    else:
        return {
            "primary_category": "Mixed Workouts",
            "daily_duration": "25 minutes",
            "recommendation_reason": "Combination of strength and cardio for overall fitness",
            "exercises": [
                {"name": "Push Ups", "duration": "10 reps", "difficulty": "Intermediate", "precautions": "Keep core tight"},
                {"name": "Bodyweight Squats", "duration": "15 reps", "difficulty": "Beginner", "precautions": "Knees behind toes"},
                {"name": "Plank", "duration": "30 sec", "difficulty": "Beginner", "precautions": "Don't sag hips"}
            ],
            "warnings": ["Warm up first", "Stay hydrated", "Listen to your body"],
            "weekly_schedule": {"monday": "Full Body", "tuesday": "Cardio", "wednesday": "Rest", "thursday": "Upper Body", "friday": "Lower Body", "saturday": "Cardio", "sunday": "Rest"}
        }
        
def get_model_with_key(api_key, model_name='gemini-2.5-flash-lite'):
    """Get Gemini model with specific API key"""
    if api_key:
        # Configure with the specific key
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        # Reconfigure with main key after creating model
        genai.configure(api_key=GEMINI_API_KEY_MAIN)
        return model
    else:
        print(f"⚠️ API key not configured, using main key")
        return genai.GenerativeModel(model_name)

@app.route('/api/log-fitness-activity', methods=['POST'])
def log_fitness_activity():
    """Log user's fitness activity duration"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    data = request.get_json()
    minutes = data.get('minutes', 0)
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    if not minutes or minutes <= 0:
        return jsonify({'success': False, 'message': 'Invalid minutes'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    # Check if already logged today
    cursor.execute('''
        SELECT minutes FROM fitness_logs WHERE user_id = ? AND log_date = ?
    ''', (user['id'], date))
    
    existing = cursor.fetchone()
    
    if existing:
        conn.close()
        return jsonify({'success': False, 'message': 'You already logged workout today! Come back tomorrow.'})
    
    # Insert new log
    cursor.execute('''
        INSERT INTO fitness_logs (user_id, minutes, log_date)
        VALUES (?, ?, ?)
    ''', (user['id'], minutes, date))
    
    # Add points (1 point per 5 minutes)
    points_earned = minutes // 5
    if points_earned > 0:
        cursor.execute('''
            INSERT INTO user_ranks (user_id, total_points)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                total_points = total_points + ?
        ''', (user['id'], points_earned, points_earned))
        
        cursor.execute('''
            INSERT INTO points_transactions (user_id, points, reason)
            VALUES (?, ?, ?)
        ''', (user['id'], points_earned, f'Fitness: {minutes} min workout'))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': f'Logged {minutes} minutes! +{points_earned} points!'})

@app.route('/api/get-fitness-logs', methods=['GET'])
def get_fitness_logs():
    """Get user's total fitness minutes for current week"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    # Get current week's start (Monday)
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_week_str = start_of_week.strftime('%Y-%m-%d')
    
    cursor.execute('''
        SELECT SUM(minutes) as total FROM fitness_logs 
        WHERE user_id = ? AND log_date >= ?
    ''', (user['id'], start_of_week_str))
    
    result = cursor.fetchone()
    conn.close()
    
    total_minutes = result['total'] if result and result['total'] else 0
    
    return jsonify({'success': True, 'total_minutes': total_minutes})

@app.route('/api/get-today-fitness-log', methods=['GET'])
def get_today_fitness_log():
    """Get today's fitness log for the user"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute('''
        SELECT minutes FROM fitness_logs WHERE user_id = ? AND log_date = ?
    ''', (user['id'], today))
    
    result = cursor.fetchone()
    conn.close()
    
    logged_minutes = result['minutes'] if result else 0
    
    return jsonify({'success': True, 'logged_minutes': logged_minutes})

@app.route('/api/get-fitness-log-by-date', methods=['GET'])
def get_fitness_log_by_date():
    """Get fitness minutes for a specific date"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'})
    
    cursor.execute('''
        SELECT minutes FROM fitness_logs 
        WHERE user_id = ? AND log_date = ?
    ''', (user['id'], date))
    
    result = cursor.fetchone()
    conn.close()
    
    return jsonify({
        'success': True,
        'date': date,
        'minutes': result['minutes'] if result else 0
    })
    
@app.route('/settings')
def settings():
    if 'user_email' not in session:
        return redirect('/login')
    return render_template('settings.html')


@app.route('/api/delete-account', methods=['POST'])
def delete_account():
    """Permanently delete user account and all associated data"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (session['user_email'],))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'message': 'User not found'})
        
        user_id = user['id']
        
        # Delete user (ON DELETE CASCADE handles related tables)
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        
        session.clear()
        
        return jsonify({'success': True, 'message': 'Account deleted successfully'})
        
    except Exception as e:
        print(f"Error deleting account: {e}")
        return jsonify({'success': False, 'message': str(e)})
# ==================== RUN APP ====================
if __name__ == '__main__':
    print("=" * 60)
    print("🍽️ MealMate AI Server Started!")
    print("=" * 60)
    print(f"📍 Landing Page: http://127.0.0.1:5000/")
    print(f"📍 Login Page: http://127.0.0.1:5000/login")
    print(f"📍 Register Page: http://127.0.0.1:5000/register")
    print(f"📍 Assessment Page: http://127.0.0.1:5000/assessment")
    print(f"📍 Dashboard Page: http://127.0.0.1:5000/dashboard")
    print(f"📍 Meal Planner Page: http://127.0.0.1:5000/meal-planner")
    print(f"📍 Profile Page: http://127.0.0.1:5000/profile")
    print(f"📍 Recipes Page: http://127.0.0.1:5000/recipes")
    print(f"📍 Shopping Page: http://127.0.0.1:5000/shopping")
    print("=" * 60)
    app.run(debug=False, port=5000, threaded=True)