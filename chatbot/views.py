from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import os
import json
import pandas as pd
import sqlite3
import google.generativeai as genai
from django.conf import settings
from django.contrib.auth import authenticate, login, get_user_model


# Path for the Excel file
EXCEL_PATH = os.path.join(settings.BASE_DIR, 'users.xlsx')

# Configure the Gemini API
GEMINI_API_KEY = "AIzaSyAnMlXs16_Otj7LrYboVUxrtSzehYslpf8"
genai.configure(api_key=GEMINI_API_KEY)

# Create the model with generation configuration
generation_config = {
    "temperature": 0.3,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-exp",
    generation_config=generation_config,
)

# Start a chat session
def start_chat_session():
    try:
        return model.start_chat(history=[])
    except Exception as e:
        print(f"Error starting chat session: {e}")
        return None

chat_session = start_chat_session()

# Parse the combined response
def parse_combined_response(response_text):
    lines = response_text.split("\n")
    topic = None
    mcqs = []
    current_question = None
    current_options = []
    answer = None

    for line in lines:
        line = line.strip()  # Clean leading/trailing spaces
        if not line:
            continue  # Skip empty lines

        if line.startswith("Topic:"):
            topic = line.split("Topic:", 1)[1].strip()

        elif line[0].isdigit() and line[1] == ".":
            if current_question:
                mcqs.append({'question': current_question, 'options': current_options, 'answer': answer})
            current_question = line
            current_options = []
            answer = None

        elif line.startswith(("a.", "b.", "c.", "d.")):
            current_options.append(line)

        elif line.startswith("Answer:"):
            answer = line.split("Answer:", 1)[1].strip()

    if current_question:
        mcqs.append({'question': current_question, 'options': current_options, 'answer': answer})

    return topic, mcqs

# Extract topic and generate MCQs
def extract_topic_and_generate_mcqs_with_gemini(query, chat_session, request):
    try:
        prompt = (
            "From the given query, identify the main topic and generate 5 multiple-choice questions on that topic. "
            "Each question should have 4 options, with one correct answer clearly marked. Provide the output in the format:\n"
            "Topic: <identified topic>\n"
            "Questions:\n"
            "1. <Question>\n"
            "   a. Option 1\n"
            "   b. Option 2\n"
            "   c. Option 3\n"
            "   d. Option 4\n"
            "   Answer: <correct option>\n"
            
        )
        response = chat_session.send_message(f"{prompt}\n{query}")
        response_text = response.text.strip()
        topic, mcqs = parse_combined_response(response_text)

        # Store the query and MCQs in the session
        request.session["current_query"] = query
        request.session["mcq_data"] = json.dumps(mcqs)
        request.session["topic"] = topic

        return topic, mcqs
    except Exception as e:
        print(f"Error extracting topic and generating MCQs: {e}")
        return None, []

# Generate feedback
def generate_final_response_with_gemini(score, total, topic, chat_session, request):
    try:
        if score / total >= 0.8:
            prompt = f"Provide a detailed big explanation about the topic '{topic}' for a user with advanced knowledge.dont give the response in bold or any type of style.give all the response in normal format "
        elif score / total >= 0.5:
            prompt = f"Provide an explanation about the topic '{topic}' for a user with intermediate knowledge.dont give the response in bold or any type of style.give all the response in normal format "
        else:
            prompt = f"Provide a short explanation about the topic '{topic}' for a user with basic knowledge.dont give the response in bold or any type of style.give all the response in normal format "

        response = chat_session.send_message(prompt).text.strip()

        # Save the final response and score in the session
        if "history" not in request.session:
            request.session["history"] = []

        request.session["history"].append({
            "query": request.session.get("current_query"),
            "response": response,
            "score": score
        })
        request.session.modified = True

        return response
    except Exception as e:
        print(f"Error generating final response: {e}")
        return "Unable to generate a detailed explanation at this time."

# Chat view
def chat(request):
    response = None
    topic = None
    mcqs = []
    user_answers = []
    score = None
    error = None
    ask_new_query = False

    if request.method == 'POST':
        try:
            if 'topic' in request.POST and 'answer_1' in request.POST:
                topic = request.POST.get('topic')
                user_answers = []
                i = 1

                while True:
                    answer_key = f'answer_{i}'
                    if answer_key in request.POST:
                        user_answers.append(request.POST.get(answer_key).strip())
                        i += 1
                    else:
                        break

                mcqs = json.loads(request.session.get('mcq_data', '[]'))
                score = 0
                
                for i, question in enumerate(mcqs):
                    if i < len(user_answers):
                        # Extract just the option letter (a, b, c, or d) from both answers
                        user_option = user_answers[i].split('.')[0].strip().lower()
                        correct_option = question.get('answer', '').split('.')[0].strip().lower()
                        
                        # Compare the options directly
                        if user_option == correct_option:
                            score += 1

                response = generate_final_response_with_gemini(score, len(mcqs), topic, chat_session, request)
                mcqs = []  # Clear MCQs after generating the final response
                ask_new_query = True

            elif 'query' in request.POST:
                user_query = request.POST.get('query')
                topic, mcqs = extract_topic_and_generate_mcqs_with_gemini(user_query, chat_session, request)
                if not topic or not mcqs:
                    error = "The chatbot could not generate questions for your query. Please try again."

        except Exception as e:
            error = f"An unexpected error occurred: {e}"

    return render(request, 'chat.html', {
        'response': response,
        'topic': topic,
        'mcqs': mcqs,
        'user_answers': user_answers,
        'score': score,
        'error': error,
        'ask_new_query': ask_new_query,
    })

@csrf_exempt 
def fetch_links_view(request):
    """
    Django view for handling link fetching.
    Handles both GET (renders the HTML page) and POST (fetches links from Gemini API).
    """
    if request.method == "POST":
        query = request.POST.get("query", "").strip()
        if not query:
            return JsonResponse({"error": "Query is required."}, status=400)

        try:
            # Start a new chat session with the Gemini API
            chat_session = genai.GenerativeModel(
                model_name="gemini-2.0-flash-exp",
                generation_config={
                    "temperature": 0.1,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                    "response_mime_type": "text/plain",
                },
            ).start_chat(history=[])

            # Create a prompt for fetching links
            prompt = (
                "Provide 5 relevant links from the web related to the following query. "
                "Ensure the links are up-to-date and reliable sources, and the first link is a YouTube link. "
                "Format:\n1. <Link>\n2. <Link>\n3. <Link>\n4. <Link>\n5. <Link>\n"
                "Do not provide any explanation or context, just the links."
                "example format:"
                "1.  https://www.youtube.com/watch?v=vKNl4K5-1_w"
                "2.  https://www.britannica.com/topic/Pashtun"
                "3.  https://idsa.in/idsacomments/Pashtuns_Afghanistan_GC_Singh_101011"
                "4.  https://www.worldhistory.org/Pashtuns/"
                "5.  https://minorityrights.org/minorities/pashtuns/"
            )

            # Fetch the response from the Gemini API
            response = chat_session.send_message(f"{prompt}\n{query}")
            print(response.text)
            return JsonResponse({"links": response.text.strip()})

        except Exception as e:
            print(f"Error fetching links: {e}")
            return JsonResponse({"error": "Error fetching links. Please try again later."}, status=500)

    elif request.method == "GET":
        # Render the HTML page for the GET request
        return render(request, "link.html")

    return JsonResponse({"error": "Invalid request method."}, status=405)
# Add to views.py


# Path for the uploads Excel file
UPLOADS_PATH = os.path.join(settings.BASE_DIR, 'uploads.xlsx')

def ensure_uploads_file():
    if not os.path.exists(UPLOADS_PATH):
        df = pd.DataFrame(columns=['subject', 'video_link'])
        df.to_excel(UPLOADS_PATH, index=False)

def get_youtube_video_id(url):
    if 'youtube.com/watch?v=' in url:
        return url.split('v=')[1].split('&')[0]
    elif 'youtu.be/' in url:
        return url.split('.be/')[1].split('?')[0]
    return None

def videos_view(request):
    ensure_uploads_file()

    if request.method == 'POST':
        subject = request.POST.get('subject')
        video_link = request.POST.get('video_link')

        if subject and video_link:
            try:
                # Validate YouTube URL
                if 'youtube.com/watch?v=' not in video_link and 'youtu.be/' not in video_link:
                    return JsonResponse({'status': 'error', 'message': 'Invalid YouTube URL'})

                df = pd.read_excel(UPLOADS_PATH)
                new_row = pd.DataFrame([[subject, video_link]], columns=['subject', 'video_link'])
                df = pd.concat([df, new_row], ignore_index=True)
                df.to_excel(UPLOADS_PATH, index=False)
                return JsonResponse({'status': 'success'})
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': str(e)})

        return JsonResponse({'status': 'error', 'message': 'Missing required fields'})

    elif request.method == 'DELETE':
        try:
            data = json.loads(request.body)
            video_link = data.get('video_link')

            if video_link:
                df = pd.read_excel(UPLOADS_PATH)
                df = df[df['video_link'] != video_link]
                df.to_excel(UPLOADS_PATH, index=False)
                return JsonResponse({'status': 'success'})
            return JsonResponse({'status': 'error', 'message': 'Video link not provided'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    # Allow all users to view the videos
    df = pd.read_excel(UPLOADS_PATH)
    videos = []
    for _, row in df.iterrows():
        video_id = get_youtube_video_id(row['video_link'])
        if video_id:
            videos.append({
                'subject': row['subject'],
                'video_link': row['video_link'],
                'thumbnail': f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg'
            })

    return render(request, 'videos.html', {'videos': videos})


User = get_user_model()

# Global variable to store the admin login status.
# 1 indicates an admin (superuser) has logged in,
# 0 indicates a normal user.
GLOBAL_ADMIN_LOGIN_STATUS = True

def index(request):
    return render(request, 'index.html')

def login_view(request):
    global GLOBAL_ADMIN_LOGIN_STATUS  # Declare use of the global variable

    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        # --- Attempt to authenticate using Django's built-in auth system ---
        user = None
        try:
            # Look up the auth user by email.
            user_obj = User.objects.get(email=email)
            # Authenticate using the user's username.
            user = authenticate(request, username=user_obj.username, password=password)
        except User.DoesNotExist:
            user = None

        if user is not None:
            login(request, user)
            if user.is_superuser:
                # For an admin (superuser), set the global variable to 1.
                GLOBAL_ADMIN_LOGIN_STATUS = 1
                request.session['is_superuser'] = 1
            else:
                GLOBAL_ADMIN_LOGIN_STATUS = 0
                request.session['is_superuser'] = 0
            return redirect('home')
        
        # --- Fallback: custom table authentication ---
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, email, password 
            FROM users 
            WHERE email = ? AND password = ?
        """, (email, password))
        user_custom = cursor.fetchone()
        conn.close()

        if user_custom:
            # This is a custom user (assumed to be non-admin).
            GLOBAL_ADMIN_LOGIN_STATUS = 0
            request.session['is_superuser'] = 0
            return redirect('home')
        else:
            messages.error(request, "Invalid credentials")
            
    return render(request, 'login.html')

# Register view
def register(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        address = request.POST.get('address')
        phone = request.POST.get('phone')

        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()

        # Create the users table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                address TEXT NOT NULL,
                phone TEXT NOT NULL
            )
        ''')

        # Insert the user into the table
        cursor.execute("INSERT INTO users (full_name, username, email, password, address, phone) VALUES (?, ?, ?, ?, ?, ?)",
                       (full_name, username, email, password, address, phone))
        conn.commit()
        conn.close()

        # Save to Excel
        df = pd.DataFrame([[full_name, username, email, password, address, phone]],
                          columns=['Full Name', 'Username', 'Email', 'Password', 'Address', 'Phone'])
        try:
            existing_df = pd.read_excel(EXCEL_PATH)
            df = pd.concat([existing_df, df], ignore_index=True)
        except FileNotFoundError:
            pass
        df.to_excel(EXCEL_PATH, index=False)

        messages.success(request, "Registration successful")
        return redirect('login')
    return render(request, 'register.html')

# Home view
def home(request):
    return render(request, 'home.html')

# Link view
def link(request):
    return render(request, 'link.html')

# History view
def history_view(request):
    history = request.session.get("history", [])
    return render(request, "history.html", {"history": history})

# Logout view
def logout_view(request):
    global GLOBAL_ADMIN_LOGIN_STATUS  # Declare global variable
    
    # Reset the global variable
    GLOBAL_ADMIN_LOGIN_STATUS = 0  

    # Clear user session
    request.session.flush()

    return redirect('index')
