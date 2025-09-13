from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import requests
import json
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# MongoDB Configuration
MONGODB_URI = "mongodb+srv://hello:Gnana123@voting.8vt5bip.mongodb.net/retryWrites=true&w=majority&appName=voting"
client = MongoClient(MONGODB_URI)
db = client.travel_planner

# Collections
users = db.users
searches = db.searches
places = db.places

# Cohere API Configuration
COHERE_API_KEY = "E9bA5pGNQsybUhv3dTiFNezykyN9kBB9PYJumHBt"  # Replace with your actual API key
COHERE_API_URL = "https://api.cohere.ai/v1/generate"

def get_places_and_hotels(destination):
    """Get places to visit and hotels using Cohere API"""
    try:
        headers = {
            'Authorization': f'Bearer {COHERE_API_KEY}',
            'Content-Type': 'application/json',
        }
        
        prompt = f"""Provide information about {destination} in the following JSON format:
        {{
            "places_to_visit": [
                {{"name": "Place Name", "description": "Brief description", "rating": "4.5", "type": "attraction"}},
                ...
            ],
            "hotels": [
                {{"name": "Hotel Name", "description": "Brief description", "rating": "4.2", "price_range": "$100-200"}},
                ...
            ]
        }}
        
        Provide at least 5 places to visit and 5 hotels for {destination}. Make sure the response is valid JSON only."""
        
        data = {
            'model': 'command',
            'prompt': prompt,
            'max_tokens': 2000,
            'temperature': 0.7
        }
        
        response = requests.post(COHERE_API_URL, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            generated_text = result['generations'][0]['text'].strip()
            
            # Try to extract JSON from the response
            try:
                # Find the JSON part in the response
                start_idx = generated_text.find('{')
                end_idx = generated_text.rfind('}') + 1
                json_str = generated_text[start_idx:end_idx]
                return json.loads(json_str)
            except:
                # Fallback data if JSON parsing fails
                return get_fallback_data(destination)
        else:
            return get_fallback_data(destination)
            
    except Exception as e:
        print(f"Error calling Cohere API: {e}")
        return get_fallback_data(destination)

def get_fallback_data(destination):
    """Fallback data when API fails"""
    return {
        "places_to_visit": [
            {"name": f"{destination} City Center", "description": "Historic downtown area with shops and restaurants", "rating": "4.3", "type": "area"},
            {"name": f"{destination} Museum", "description": "Local history and cultural exhibits", "rating": "4.1", "type": "museum"},
            {"name": f"{destination} Park", "description": "Beautiful green space for relaxation", "rating": "4.4", "type": "park"},
            {"name": f"{destination} Market", "description": "Local market with crafts and food", "rating": "4.2", "type": "market"},
            {"name": f"{destination} Viewpoint", "description": "Scenic overlook of the city", "rating": "4.6", "type": "viewpoint"}
        ],
        "hotels": [
            {"name": f"Grand {destination} Hotel", "description": "Luxury hotel in city center", "rating": "4.5", "price_range": "$150-250"},
            {"name": f"{destination} Plaza", "description": "Modern business hotel", "rating": "4.2", "price_range": "$100-180"},
            {"name": f"Boutique {destination}", "description": "Charming boutique accommodation", "rating": "4.4", "price_range": "$120-200"},
            {"name": f"{destination} Inn", "description": "Comfortable mid-range option", "rating": "4.0", "price_range": "$80-120"},
            {"name": f"Budget Stay {destination}", "description": "Clean and affordable rooms", "rating": "3.8", "price_range": "$50-80"}
        ]
    }

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Check if user already exists
        if users.find_one({"$or": [{"username": username}, {"email": email}]}):
            flash('Username or email already exists!')
            return render_template('register.html')
        
        # Create new user
        hashed_password = generate_password_hash(password)
        user_data = {
            "username": username,
            "email": email,
            "password": hashed_password,
            "created_at": datetime.now()
        }
        
        users.insert_one(user_data)
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = users.find_one({"username": username})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get user's search history
    user_searches = searches.find({"user_id": session['user_id']}).sort("created_at", -1).limit(10)
    return render_template('dashboard.html', searches=list(user_searches))

@app.route('/search', methods=['POST'])
def search():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    destination = request.form['destination'].strip()
    
    if not destination:
        flash('Please enter a destination!')
        return redirect(url_for('dashboard'))
    
    # Get places and hotels data
    data = get_places_and_hotels(destination)
    
    # Save search to database
    search_data = {
        "user_id": session['user_id'],
        "destination": destination,
        "places": data['places_to_visit'],
        "hotels": data['hotels'],
        "created_at": datetime.now()
    }
    
    result = searches.insert_one(search_data)
    search_id = str(result.inserted_id)
    
    return redirect(url_for('search_results', search_id=search_id))

@app.route('/results/<search_id>')
def search_results(search_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        search_data = searches.find_one({"_id": ObjectId(search_id), "user_id": session['user_id']})
        if not search_data:
            flash('Search results not found!')
            return redirect(url_for('dashboard'))
        
        return render_template('results.html', search=search_data)
    except:
        flash('Invalid search ID!')
        return redirect(url_for('dashboard'))

@app.route('/api/search/<search_id>')
def api_search_results(search_id):
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        search_data = searches.find_one({"_id": ObjectId(search_id), "user_id": session['user_id']})
        if not search_data:
            return jsonify({"error": "Search not found"}), 404
        
        # Convert ObjectId to string for JSON serialization
        search_data['_id'] = str(search_data['_id'])
        return jsonify(search_data)
    except:
        return jsonify({"error": "Invalid search ID"}), 400

if __name__ == '__main__':
    app.run(debug=True)