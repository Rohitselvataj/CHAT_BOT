from django.contrib import admin
from django.urls import path
from chatbot import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register, name='register'),
    path('home/', views.home, name='home'),
    path('chat/', views.chat, name='chat'),
    path("link/", views.fetch_links_view, name="fetch_links"),
    path('history/', views.history_view, name='history'),
    path('logout/', views.logout_view, name='logout'),
    path('videos/', views.videos_view, name='videos'),
    
]
